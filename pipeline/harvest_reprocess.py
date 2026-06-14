"""Reprocesare COMPLETĂ a declarațiilor deconcentrate: OCR pe scanate + avere ȘI interese.

Peste setul de ~66.932 PDF (checkpoint din harvest_declaratii_deconcentrate):
  1. text via pdfplumber; dacă e SCANAT (<100 ch) → OCR (RapidOCR, română/latină).
  2. clasifică documentul (avere / interese / combinat).
  3. parsează partea de AVERE (agregate) și/sau partea de INTERESE (5 secțiuni, entități).
  4. REDACTARE PII (Legea 176/2010); scriere incrementală JSONL (resume); batch + procese paralele.
  5. finalizare → avere_deconcentrate.json (acum INCL. scanate OCR) + interese_deconcentrate.json.

Reia cu același cmd dacă e întrerupt. Pentru OCR la scară: rulează ore (vezi benchmark).
"""

from __future__ import annotations

import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, wait
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from connectors.ani.declaratii import (  # noqa: E402
    classify_declaration, extract_pdf_text, extract_pdf_text_ocr,
    parse_avere_ocr, parse_avere_text, parse_interese_text,
)
from connectors.ani.redaction import find_pii  # noqa: E402
from solomonar_core.bronze import BronzeStore  # noqa: E402
from solomonar_core.http import Client  # noqa: E402

V = os.path.join(ROOT, "data/v1")
# SOLOMONAR_SRC selectează sursa (deconcentrate=implicit, sau ministere/anpm/parlament...) →
# refolosim ACELAȘI pipeline (uncapped + OCR + avere&interese) pe orice listă de PDF-uri.
SRC = os.environ.get("SOLOMONAR_SRC", "")
if SRC:
    CKPT = os.environ.get("SOLOMONAR_CKPT", os.path.join(V, f"declaratii/_{SRC}_pdfs.json"))
    JSONL = os.path.join(V, f"declaratii/_{SRC}_reproc.jsonl")
    OUT_AV = os.path.join(V, f"declaratii/avere_{SRC}.json")
    OUT_IT = os.path.join(V, f"declaratii/interese_{SRC}.json")
else:  # implicit = deconcentrate (păstrează căile rulării curente pentru resume)
    CKPT = os.path.join(V, "declaratii/_decon_pdfs.json")
    JSONL = os.path.join(V, "declaratii/_reproc.jsonl")
    OUT_AV = os.path.join(V, "declaratii/avere_deconcentrate.json")
    OUT_IT = os.path.join(V, "declaratii/interese_deconcentrate.json")
BATCH = int(os.environ.get("SOLOMONAR_BATCH", "400"))


def _detect_workers() -> int:
    """GPU prezent (wheel-uri CUDA) → puține procese (GPU = bottleneck comun, 8GB VRAM).
    Fără GPU → ~1 proces/core (OCR e 1-thread/proces, vezi _ocr_engine)."""
    try:
        import nvidia  # noqa: F401
        return int(os.environ.get("SOLOMONAR_OCR_WORKERS", "4"))
    except Exception:
        return max(2, min(14, (os.cpu_count() or 4) - 2))


WORKERS = _detect_workers()


def _process(task: tuple) -> dict:
    """Worker (proces): text-sau-OCR → clasifică → parsează avere + interese. Returnează dict mic.

    mode 'text' = pass CPU rapid: sare PDF-urile scanate (le amână pt. pass-ul GPU).
    mode 'ocr'/'auto' = OCR pe scanate (GPU dacă disponibil).
    """
    url, path, inst, mode = task
    try:
        data = open(path, "rb").read()
    except Exception:
        return {"pdf_url": url, "status": "fail"}
    try:
        txt = extract_pdf_text(data)
    except Exception:
        txt = ""
    ocr = False
    if len(txt.strip()) < 100:                       # scanat / fără strat text
        if mode == "text":
            return {"pdf_url": url, "defer": True}    # amânat pt. pass-ul OCR (nu se scrie)
        try:
            txt = extract_pdf_text_ocr(data)
            ocr = True
        except Exception:
            return {"pdf_url": url, "status": "ocr_fail", "ocr": True}
    if len(txt.strip()) < 50:
        return {"pdf_url": url, "status": "empty", "ocr": ocr}
    if find_pii(txt):
        return {"pdf_url": url, "status": "pii", "ocr": ocr}

    kinds = classify_declaration(txt)
    rec = {"pdf_url": url, "status": "empty", "ocr": ocr}
    if "avere" in kinds:
        av = parse_avere_ocr(txt) if ocr else parse_avere_text(txt)  # OCR-tolerant pe scanate
        if av.text_extracted and (av.terenuri_count + av.cladiri_count
                                  + av.conturi_total_ron + av.venituri_anuale_ron) > 0:
            rec["av"] = {"institutie": inst, "pdf_url": url, "ocr": ocr,
                         "terenuri": av.terenuri_count, "cladiri": av.cladiri_count,
                         "conturi_ron": round(av.conturi_total_ron),
                         "venituri_ron": round(av.venituri_anuale_ron),
                         "datorii_ron": round(av.datorii_total_ron), "auto": av.auto_count}
    if "interese" in kinds:
        it = parse_interese_text(txt)
        if it.text_extracted and it.has_any:
            rec["it"] = {"institutie": inst, "pdf_url": url, "ocr": ocr,
                         "actionariat": it.actionariat_count, "conducere": it.conducere_firme_count,
                         "prof_sindicat": it.prof_sindicat_count, "partid": it.partid_count,
                         "contracte": it.contracte_count,
                         "valoare_actiuni_ron": round(it.valoare_actiuni_ron),
                         "valoare_contracte_ron": round(it.valoare_contracte_ron),
                         "entitati": it.entitati}
    if "av" in rec or "it" in rec:
        rec["status"] = "ok"
    return rec


def _load_done() -> set:
    done = set()
    if os.path.exists(JSONL):
        with open(JSONL, encoding="utf-8") as f:
            for line in f:
                try:
                    done.add(json.loads(line)["pdf_url"])
                except Exception:
                    continue
    return done


def _chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def main(mode: str = "auto", workers: int | None = None, limit: int | None = None) -> dict:
    workers = workers or WORKERS
    bronze = BronzeStore(os.path.join(ROOT, "data", "raw"))
    dl_client = Client(bronze=bronze, throttle_seconds=0.2,
                       timeout=int(os.environ.get("SOLOMONAR_DL_TIMEOUT", "12")))
    pdf_to_inst = json.load(open(CKPT, encoding="utf-8"))
    done = _load_done()
    remaining = [u for u in pdf_to_inst if u not in done]
    if limit:
        remaining = remaining[:limit]
    print(f"[reproc mode={mode}] total={len(pdf_to_inst)} done={len(done)} ramase={len(remaining)} "
          f"| {workers} procese, batch={BATCH}", flush=True)

    n_done = len(done)
    deferred = 0
    t0 = time.time()
    proc_this_run = 0
    timeouts = 0
    batch_timeout = int(os.environ.get("SOLOMONAR_BATCH_TIMEOUT", "1800"))  # un PDF agățat > atât → skip
    pool = ProcessPoolExecutor(max_workers=workers)
    with open(JSONL, "a", encoding="utf-8") as jf:
        for bi, batch in enumerate(_chunks(remaining, BATCH), 1):
            # descarcă PDF-urile încă necache-uite (surse fără crawl prealabil, ex. parlament)
            missing = [u for u in batch if not bronze.has_url(u)]
            if missing:
                dl_client.fetch_many([(u, "src_pdf", ".pdf") for u in missing], workers=8)
            tasks, miss = [], []
            for u in batch:
                art = bronze.artifact_for_url(u)
                if art:
                    tasks.append((u, str(bronze.root / art.path), pdf_to_inst[u], mode))
                else:
                    miss.append({"pdf_url": u, "status": "fail"})
            # submit + așteaptă cu timeout; un task agățat NU mai blochează tot runul
            futs = {pool.submit(_process, t): t for t in tasks}
            done_f, not_done = wait(futs, timeout=batch_timeout)
            recs = list(miss)
            for f in done_f:
                try:
                    recs.append(f.result())
                except Exception:
                    recs.append({"pdf_url": futs[f][0], "status": "fail"})
            hung = [f for f in not_done if f.running()]   # chiar agățate (vs nepornite)
            for f in hung:
                recs.append({"pdf_url": futs[f][0], "status": "timeout"})  # skip permanent (1 PDF stricat)
            if not_done:  # ucide workerii (inclusiv agățați) + pool nou; nepornitele se reiau la resume
                timeouts += len(hung)
                for p in list(getattr(pool, "_processes", {}).values()):
                    try:
                        p.terminate()
                    except Exception:
                        pass
                pool.shutdown(wait=False, cancel_futures=True)
                pool = ProcessPoolExecutor(max_workers=workers)
            written = [r for r in recs if not r.get("defer")]   # amânatele NU se scriu (rămân pt. OCR)
            for r in written:
                jf.write(json.dumps(r, ensure_ascii=False) + "\n")
            jf.flush()
            deferred += sum(1 for r in recs if r.get("defer"))
            n_done += len(written)
            proc_this_run += len(done_f) + len(miss) + len(hung)
            nav = sum(1 for r in recs if r.get("av"))
            nit = sum(1 for r in recs if r.get("it"))
            nocr = sum(1 for r in recs if r.get("ocr"))
            el = time.time() - t0
            rate = proc_this_run / el if el > 0 else 0
            eta_h = (max(0, len(remaining) - proc_this_run) / rate / 3600) if rate > 0 else 0
            tflag = f" TIMEOUT={len(hung)}" if hung else ""
            print(f"   batch {bi}: scrise={len(written)} amanate={sum(1 for r in recs if r.get('defer'))} "
                  f"(av={nav} it={nit} ocr={nocr}){tflag} | done={n_done} | {rate*60:.0f}/min "
                  f"ETA={eta_h:.1f}h", flush=True)
    pool.shutdown(wait=False)
    _finalize()
    return {"done": n_done, "deferred": deferred, "timeouts": timeouts}


def _finalize() -> None:
    seen_av, seen_it, av, it = set(), set(), [], []
    stats = {"pii": 0, "empty": 0, "fail": 0, "ocr_fail": 0, "ocr_used": 0}
    with open(JSONL, encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except Exception:
                continue
            stats["ocr_used"] += 1 if r.get("ocr") else 0
            st = r.get("status")
            if st in stats:
                stats[st] += 1
            if r.get("av") and r["av"]["pdf_url"] not in seen_av:
                seen_av.add(r["av"]["pdf_url"]); av.append(r["av"])
            if r.get("it") and r["it"]["pdf_url"] not in seen_it:
                seen_it.add(r["it"]["pdf_url"]); it.append(r["it"])
    now = datetime.now(timezone.utc).isoformat()
    json.dump({"generated_at": now, "sursa": "servicii deconcentrate, text+OCR, Legea 176/2010",
               "total": len(av), "ocr_in_corpus": stats["ocr_used"], "pii_blocate": stats["pii"],
               "declaratii": av}, open(OUT_AV, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    json.dump({"generated_at": now, "sursa": "servicii deconcentrate, declaratii de INTERESE, text+OCR",
               "total": len(it), "declaratii": it},
              open(OUT_IT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"PUBLICAT: avere={len(av)} interese={len(it)} | OCR folosit={stats['ocr_used']} "
          f"PII={stats['pii']} empty={stats['empty']} fail={stats['fail']+stats['ocr_fail']}", flush=True)


if __name__ == "__main__":
    # uz: python -m pipeline.harvest_reprocess [mode] [workers] [limit]
    #   mode=text  → pass CPU rapid (sare scanatele); mode=ocr → OCR pe scanate (GPU)
    _mode = sys.argv[1] if len(sys.argv) > 1 else "auto"
    _workers = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2] != "-" else None
    _limit = int(sys.argv[3]) if len(sys.argv) > 3 else None
    main(mode=_mode, workers=_workers, limit=_limit)
