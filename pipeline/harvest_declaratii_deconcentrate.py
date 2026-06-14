"""Harvest declarații avere DECONCENTRATE — scară mare (zeci de mii de PDF), memorie-safe + resume.

Capul a fost scos (vezi user): luăm TOATE declarațiile (crawl a găsit ~66.932 PDF pe 121 site-uri,
DSVSA având sute-mii/județ). La scara asta nu putem ține totul în RAM și nici parsa serial:

  1. CRAWL (cu checkpoint) → pdf_to_inst {url: instituție}. Re-rulare = sare crawl-ul.
  2. RESUME: citește URL-urile deja procesate din JSONL → continuă de unde a rămas.
  3. BATCH: pentru fiecare lot de ~600: descarcă paralel (fetch_many, cache bronze pe D:),
     parsează PDF-urile în PARALEL pe procese (pdfplumber e CPU-bound), eliberează memoria.
  4. SCRIERE INCREMENTALĂ în JSONL (rezistă la crash / oprire), + REDACTARE PII (Legea 176/2010).
  5. FINALIZARE: JSONL → declaratii/avere_deconcentrate.json (doar status=ok).

Rulează după ce data/raw e junction către D: (spațiu). Reia cu același cmd dacă e întrerupt.
"""

from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from connectors.ani.declaratii import extract_pdf_text, parse_avere_text  # noqa: E402
from connectors.ani.redaction import find_pii  # noqa: E402
from connectors.institutie.generic import crawl_declaration_pdfs  # noqa: E402
from solomonar_core.bronze import BronzeStore  # noqa: E402
from solomonar_core.http import Client  # noqa: E402
from solomonar_core.names import strip_diacritics  # noqa: E402

V = os.path.join(ROOT, "data/v1")
CKPT = os.path.join(V, "declaratii/_decon_pdfs.json")       # checkpoint listă PDF (post-crawl)
JSONL = os.path.join(V, "declaratii/_avere_decon.jsonl")    # progres incremental (resume)
OUT = os.path.join(V, "declaratii/avere_deconcentrate.json")
BATCH = 600
PARSE_WORKERS = max(2, (os.cpu_count() or 4) - 1)


def _institutions() -> list[dict]:
    src = json.load(open(os.path.join(V, "institutii/deconcentrate_real.json"), encoding="utf-8"))
    out = []
    for i in src["institutii"]:
        secs = i.get("sections") or {}
        start = secs.get("declaratii") or secs.get("integritate")
        if not start:
            continue
        sid = strip_diacritics(f"{i['service']}_{i['county']}").lower().replace(" ", "")
        out.append({"id": sid, "name": f"{i['service']} {i['county']}",
                    "host": urlparse(i["url"]).netloc, "start": start})
    return out


def _crawl_all(client) -> dict:
    """Construiește {pdf_url: instituție}; salvează checkpoint ca re-rularea să nu re-crawl-uiască."""
    if os.path.exists(CKPT):
        d = json.load(open(CKPT, encoding="utf-8"))
        print(f"[crawl] checkpoint încărcat: {len(d)} PDF (sar peste crawl)", flush=True)
        return d
    insts = _institutions()
    print(f"[crawl] {len(insts)} servicii cu secțiune declarații/integritate", flush=True)
    pdf_to_inst: dict[str, str] = {}
    for it in insts:
        try:
            urls = crawl_declaration_pdfs(client, it["start"], "decd_" + it["id"],
                                          it["host"], max_depth=3, max_pdfs=5000)
        except Exception as e:
            print(f"   ! crawl eșuat {it['name']}: {type(e).__name__}", flush=True)
            urls = []
        for u in urls:
            pdf_to_inst.setdefault(u, it["name"])
        if urls:
            print(f"   {it['name']:22} {len(urls)} PDF", flush=True)
    json.dump(pdf_to_inst, open(CKPT, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"[crawl] TOTAL {len(pdf_to_inst)} PDF — checkpoint salvat", flush=True)
    return pdf_to_inst


def _parse_pdf(task: tuple) -> tuple:
    """Worker (proces separat): citește PDF de pe disc, redactează PII, parsează averea."""
    url, path, inst = task
    try:
        with open(path, "rb") as f:
            txt = extract_pdf_text(f.read())
    except Exception:
        return (url, "fail", None)
    if find_pii(txt):
        return (url, "pii", None)
    av = parse_avere_text(txt)
    signal = av.terenuri_count + av.cladiri_count + av.conturi_total_ron + av.venituri_anuale_ron
    if not av.text_extracted or signal == 0:
        return (url, "empty", None)
    return (url, "ok", {
        "institutie": inst, "pdf_url": url, "terenuri": av.terenuri_count, "cladiri": av.cladiri_count,
        "conturi_ron": round(av.conturi_total_ron), "venituri_ron": round(av.venituri_anuale_ron),
        "datorii_ron": round(av.datorii_total_ron), "auto": av.auto_count})


def _load_processed() -> set:
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


def main() -> dict:
    bronze = BronzeStore(os.path.join(ROOT, "data", "raw"))
    client = Client(bronze=bronze, throttle_seconds=0.3, timeout=20)

    pdf_to_inst = _crawl_all(client)
    processed = _load_processed()
    remaining = [u for u in pdf_to_inst if u not in processed]
    print(f"[parse] total={len(pdf_to_inst)} deja_procesate={len(processed)} ramase={len(remaining)} "
          f"| {PARSE_WORKERS} procese, batch={BATCH}", flush=True)

    kept = sum(1 for _ in ()) or 0  # va fi recalculat la final din JSONL
    done = len(processed)
    with ProcessPoolExecutor(max_workers=PARSE_WORKERS) as pool, \
            open(JSONL, "a", encoding="utf-8") as jf:
        for bi, batch in enumerate(_chunks(remaining, BATCH), 1):
            fetched = client.fetch_many([(u, "decd_pdf", ".pdf") for u in batch], workers=12)
            tasks, lines = [], []
            for u in batch:
                if fetched.get(u):
                    art = bronze.artifact_for_url(u)
                    if art:
                        tasks.append((u, str(bronze.root / art.path), pdf_to_inst[u]))
                        continue
                lines.append({"pdf_url": u, "status": "fail"})
            del fetched  # eliberează ~BATCH*300KB din RAM
            for url, status, rec in pool.map(_parse_pdf, tasks, chunksize=10):
                line = {"pdf_url": url, "status": status}
                if rec:
                    line.update(rec)
                lines.append(line)
            for ln in lines:
                jf.write(json.dumps(ln, ensure_ascii=False) + "\n")
            jf.flush()
            done += len(batch)
            ok = sum(1 for ln in lines if ln["status"] == "ok")
            print(f"   batch {bi}: +{len(batch)} ({ok} ok) | total procesate={done}/{len(pdf_to_inst)} "
                  f"| cache={bronze.count()}", flush=True)

    # finalizare: JSONL -> JSON (doar declaratii ok, dedup pe pdf_url)
    seen, decls, pii, empty, fail = set(), [], 0, 0, 0
    with open(JSONL, encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except Exception:
                continue
            st = r.get("status")
            if st == "pii":
                pii += 1
            elif st == "empty":
                empty += 1
            elif st == "fail":
                fail += 1
            elif st == "ok" and r["pdf_url"] not in seen:
                seen.add(r["pdf_url"])
                decls.append({k: r[k] for k in ("institutie", "pdf_url", "terenuri", "cladiri",
                                                "conturi_ron", "venituri_ron", "datorii_ron", "auto")})
    json.dump({"generated_at": datetime.now(timezone.utc).isoformat(),
               "sursa": "servicii deconcentrate (DSVSA/DSP/ITM/ISJ/DGASPC/OCPI), Legea 176/2010, fara CAPTCHA",
               "total": len(decls), "pii_blocate": pii, "goale_sau_interese": empty, "esuate": fail,
               "declaratii": decls},
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"PUBLICAT avere_deconcentrate.json: {len(decls)} declaratii | {pii} PII | {empty} goale | "
          f"{fail} esuate | cache={bronze.count()}", flush=True)
    return {"declaratii": len(decls), "pii": pii, "empty": empty, "fail": fail}


if __name__ == "__main__":
    main()
