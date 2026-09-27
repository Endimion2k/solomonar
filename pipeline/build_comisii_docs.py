"""Textul documentelor PLx din comisii → verdicte (avize/rapoarte) + index de căutare pe proiect.

Documentele sunt arhivate în bronze de harvest_comisii_docs (co_doc). Pași (reluabili):
  text     strat de text (pypdfium2, ~12 ms/doc) pe toate documentele; scanatele sunt marcate.
  ocr      OCR (RapidOCR, GPU) pe scanate — ~70% din documente (expuneri de motive, avize CL,
           forme ale inițiatorului sunt scanate) → ore de GPU.
  publish  (rulează și la finalul pașilor text/ocr):
             comisii/documente_text.json    per document: pagini, OCR, verdict, extras scurt
             comisii/cautare_documente.json per PLx: termenii normalizați din toate documentele
Textul integral rămâne LOCAL (data/build/, gitignored): publicăm doar extrase + index.
PII (CNP, telefoane, CI, IBAN) e mascat cu redact_text ÎNAINTE de orice stocare.
"""

from __future__ import annotations

import collections
import json
import os
import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor, wait
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from connectors.ani.redaction import redact_text  # noqa: E402

V = os.path.join(ROOT, "data/v1/comisii")
CKPT = os.path.join(ROOT, "data/build/comisii_docs_text.jsonl")
OUT_DOCS = os.path.join(V, "documente_text.json")
OUT_SEARCH = os.path.join(V, "cautare_documente.json")

MIN_TEXT_CHARS = 200        # sub atât (fără spații) documentul e considerat scanat
MAX_TEXT_CHARS = 200_000    # plafon pe document în checkpoint (rapoartele cu anexe pot fi uriașe)
# primele pagini conțin decizia/obiectul/motivarea; plafonul 6 = ~55% din pagini (43,6k din 78k)
OCR_MAX_PAGES = int(os.environ.get("SOLOMONAR_DOCS_OCR_PAGES", "6"))
# ordinea OCR după valoare: pozițiile care dau verdicte (Guvern, CL, CES, CSM) întâi, apoi conținutul
OCR_PRIO = ["punct_vedere_guvern", "aviz_consiliu_legislativ", "aviz_ces", "aviz_csm", "aviz_comisie", "raport",
            "raport_suplimentar", "expunere_motive", "forma_initiator", "ordonanta", "sesizare", "alt"]
EXCERPT_CHARS = 280
DF_MAX = 0.5                # termenii prezenți în > 50% din PLx nu ajută căutarea
BATCH = 200

_TR = str.maketrans("ăâîșşțţĂÂÎȘŞȚŢ", "aaisstt" "AAISSTT")
_WORD = re.compile(r"[a-z]{3,}|\d{1,4}/\d{4}")
STOP = set("""ale are aici alin alineatul art articolul asa asupra aceasta aceste acest acesta acestei
acestor acestui acea acel acele catre care cea cei cel cele celor cum cand dar data decat deja din
dintre doar este fie fiind fost iar inca intre isi lor mai sau sale sub sunt sus toate tot totusi
una unei unor unui unde vor prin pentru precum potrivit privind lit pct asemenea astfel""".split())

_DECIZIE = re.compile(r"\b(?:au|a|am) (?:hotarat|decis)\b|\bse propune\b|\bpropun(?:e|em)? (?:plenului|adoptarea|respingerea)"
                      r"|\ba fost avizat (?:favorabil|negativ|nefavorabil)")
# „respingerea amendamentelor” nu e respingerea proiectului
_RESP = r"respinger[a-z]*(?![a-z])(?! (?:a |tuturor )?amendament)"
_RESPING = re.compile(_RESP)
_AVIZ_NEG = re.compile(r"aviz (?:negativ|nefavorabil)|avize(?:aza|ze) (?:negativ|nefavorabil)|avizat (?:negativ|nefavorabil)"
                       r"|avizarea (?:negativa|nefavorabila)|" + _RESP)
_AVIZ_POZ = re.compile(r"aviz (?:favorabil|pozitiv)|avize(?:aza|ze) (?:favorabil|pozitiv)|avizat (?:favorabil|pozitiv)"
                       r"|avizarea (?:favorabila|pozitiva)|adoptar")
_AMEND = re.compile(r"cu amendament")
_FORMA = re.compile(r"in forma (?:initiatorului|prezentata|transmisa|adoptata|propusa)|fara amendament")


def norm(s: str) -> str:
    """Minuscule fără diacritice, spații comprimate — aceeași lungime ca re.sub(r'\\s+', ' ', s)."""
    return re.sub(r"\s+", " ", s).translate(_TR).lower()


_GUV_NEG = re.compile(r"\bnu (?:se )?sustine\b|\bnu sustinem\b")
_GUV_LAT = re.compile(r"latitudinea (?:parlamentului|camerei|forului|legiuitorului)"
                      r"|(?:decizia|optiunea) .{0,60}apartine (?:parlamentului|legiuitorului)")
_GUV_POZ = re.compile(r"\bsustine(?:m)? (?:adoptarea|aceasta|prezenta|initiativa|propunerea|proiectul)")
_EXT_NEG = re.compile(r"\baviz(?:eaza|am|at)? (?:negativ|nefavorabil)|\bnu avizeaza favorabil")
_EXT_POZ = re.compile(r"\baviz(?:eaza|am|at)? favorabil")
SURSA = {"punct_vedere_guvern": "guvern", "aviz_consiliu_legislativ": "cl", "aviz_ces": "ces", "aviz_csm": "csm"}


def doc_kind(tip: str, url: str) -> str:
    """Tipul documentului, rafinat pentru „alt” după numele fișierului cdep.ro (pvg = punct de vedere
    al Guvernului, ces = aviz CES, oug/og = textul ordonanței)."""
    if tip != "alt":
        return tip
    name = url.rsplit("/", 1)[-1].lower()
    if name.startswith("pvg"):
        return "punct_vedere_guvern"
    if name.startswith("ces"):
        return "aviz_ces"
    if re.match(r"o(?:ug)?\d", name):
        return "ordonanta"
    return tip


def _sentence_start(t: str, pos: int) -> int:
    dot = t.rfind(". ", max(0, pos - 200), pos)
    return dot + 2 if dot >= 0 else max(0, pos - 100)


def _extern(kind: str, t: str) -> dict | None:
    """Poziția Guvernului / avizul CL, CES, CSM — documente scurte cu o singură decizie."""
    if kind == "punct_vedere_guvern":
        m = _GUV_NEG.search(t) or _GUV_LAT.search(t) or _GUV_POZ.search(t)
        if not m:
            return None
        v = ("nu_sustine" if _GUV_NEG.match(t, m.start()) else
             "latitudine" if _GUV_LAT.match(t, m.start()) else "sustine")
    else:
        neg, poz = _EXT_NEG.search(t), _EXT_POZ.search(t)
        m = neg if neg and (not poz or neg.start() < poz.start()) else poz
        if not m:
            return None
        v = "negativ" if m is neg else "favorabil"
    out = {"verdict": v, "sursa": SURSA[kind], "decizie_start": _sentence_start(t, m.start())}
    if re.search(r"cu observatii|sub rezerva", t[m.start(): m.start() + 250]):
        out["observatii"] = True
    return out


def verdict(tip: str, t: str) -> dict | None:
    """Decizia din aviz/raport/punct de vedere (text normalizat), cu sursa ei: comisie, raport (comisia
    sesizată în fond), guvern, cl (Consiliul Legislativ), ces, csm. În avizele/rapoartele comisiilor,
    avizele altor instituții citate în text sunt ignorate: căutăm doar în fraza de decizie."""
    if tip in SURSA:
        return _extern(tip, t)
    if not (tip.startswith("aviz_comisie") or tip.startswith("raport")):
        return None
    sursa = "comisie" if tip.startswith("aviz") else "raport"
    for m in _DECIZIE.finditer(t):
        w = t[m.start(): m.start() + 320]
        if "raportului preliminar" in w[:80]:
            continue
        # rădăcini („raport de adoptare”, „adoptarea proiectului”, „soluția ... de respingere”); contează
        # primul cuvânt-cheie din frază — decizia e formulată întâi, detaliile (amendamente respinse) după
        if tip.startswith("aviz"):
            neg, poz, labels = _AVIZ_NEG.search(w), _AVIZ_POZ.search(w), ("negativ", "favorabil")
        else:
            neg, poz, labels = _RESPING.search(w), re.search(r"adoptar|admiter", w), ("respingere", "adoptare")
        v = None
        if neg and (not poz or neg.start() < poz.start()):
            v = labels[0]
        elif poz:
            v = labels[1]
        if v:
            out = {"verdict": v, "sursa": sursa, "decizie_start": m.start()}
            if _AMEND.search(w):
                out["amendamente"] = True
            elif _FORMA.search(w):
                out["amendamente"] = False
            if "unanimitat" in w:
                out["vot"] = "unanimitate"
            elif "majoritat" in w:
                out["vot"] = "majoritate"
            return out
    return None


def _clean(txt: str) -> str:
    return redact_text(re.sub(r"[ \t\r\f\v]+", " ", txt)).strip()[:MAX_TEXT_CHARS]


def _text_layer(path: str) -> tuple[str, int]:
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(path)
    try:
        return "\n".join(pdf[i].get_textpage().get_text_range() for i in range(len(pdf))), len(pdf)
    finally:
        pdf.close()


def _ocr_one(task: tuple) -> dict:
    url, path = task
    from connectors.ani.declaratii import extract_pdf_text_ocr
    try:
        txt = extract_pdf_text_ocr(open(path, "rb").read(), max_pages=OCR_MAX_PAGES)
    except Exception:
        return {"url": url, "status": "ocr_fail"}
    txt = _clean(txt)
    if len(re.sub(r"\s", "", txt)) < 50:
        return {"url": url, "status": "gol", "ocr": True}
    return {"url": url, "status": "ok", "ocr": True, "text": txt}


# ---------------------------------------------------------------- checkpoint
def _docs() -> tuple[list, dict]:
    plx = json.load(open(os.path.join(V, "plx.json"), encoding="utf-8"))["plx"]
    meta = {}
    for p in plx:
        for d in p["documente"]:
            meta.setdefault(d["url"], {"idp": str(p["idp"]), "tip": d["tip"], "kind": doc_kind(d["tip"], d["url"]),
                                       "an": int(p.get("an") or 0)})
    return plx, meta


def _latest() -> dict:
    last = {}
    if os.path.exists(CKPT):
        with open(CKPT, encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if last.get(r["url"], {}).get("status") == "ok" and r.get("status") != "ok":
                    continue          # o reluare eșuată nu șterge un text bun
                last[r["url"]] = {**last.get(r["url"], {}), **r}
    return last


def _bronze():
    from solomonar_core.bronze import BronzeStore
    return BronzeStore(os.path.join(ROOT, "data", "raw"))


def run_text() -> dict:
    bronze = _bronze()
    _, meta = _docs()
    last = _latest()
    # documentele încă nedescărcate se reiau (harvest_comisii_docs le poate fi arhivat între timp)
    todo = [u for u in meta if u not in last or last[u].get("status") == "nedescarcat"]
    print(f"[text] documente={len(meta)} deja={len(last)} de procesat={len(todo)}", flush=True)
    c = collections.Counter()
    os.makedirs(os.path.dirname(CKPT), exist_ok=True)
    with open(CKPT, "a", encoding="utf-8") as f:
        for i, u in enumerate(todo, 1):
            art = bronze.artifact_for_url(u)
            if not art:
                rec = {"url": u, "status": "nedescarcat"}
            else:
                try:
                    txt, pages = _text_layer(str(bronze.root / art.path))
                except Exception:
                    txt, pages = "", 0
                if len(re.sub(r"\s", "", txt)) >= MIN_TEXT_CHARS:
                    rec = {"url": u, "status": "ok", "ocr": False, "pagini": pages, "text": _clean(txt)}
                else:
                    rec = {"url": u, "status": "scanat", "pagini": pages}
            c[rec["status"]] += 1
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            if i % 2000 == 0:
                print(f"   {i}/{len(todo)} {dict(c)}", flush=True)
    print(f"[text] {dict(c)}", flush=True)
    return dict(c)


def run_ocr(workers: int | None = None, limit: int | None = None) -> dict:
    bronze = _bronze()
    _, meta = _docs()
    last = _latest()
    rank = {k: i for i, k in enumerate(OCR_PRIO)}
    todo = sorted((u for u, r in last.items() if r.get("status") == "scanat" and u in meta),
                  key=lambda u: (rank.get(meta[u]["kind"], len(rank)), -meta[u]["an"]))  # recente întâi
    if limit:
        todo = todo[:limit]
    workers = workers or int(os.environ.get("SOLOMONAR_OCR_WORKERS", "2"))
    print(f"[ocr] scanate de procesat={len(todo)} | {workers} procese, max {OCR_MAX_PAGES} pagini/doc", flush=True)
    c = collections.Counter()
    t0, done_n = time.time(), 0
    pool = ProcessPoolExecutor(max_workers=workers)
    with open(CKPT, "a", encoding="utf-8") as f:
        for bi in range(0, len(todo), BATCH):
            batch = todo[bi: bi + BATCH]
            tasks = [(u, str(bronze.root / bronze.artifact_for_url(u).path)) for u in batch]
            futs = {pool.submit(_ocr_one, t): t for t in tasks}
            fin, pending = wait(futs, timeout=int(os.environ.get("SOLOMONAR_BATCH_TIMEOUT", "3600")))
            recs = []
            for fu in fin:
                try:
                    recs.append(fu.result())
                except Exception:
                    recs.append({"url": futs[fu][0], "status": "ocr_fail"})
            recs += [{"url": futs[fu][0], "status": "timeout"} for fu in pending if fu.running()]
            if pending:     # ucide workerii agățați; nepornitele se reiau la următoarea rulare
                for p in list(getattr(pool, "_processes", {}).values()):
                    try:
                        p.terminate()
                    except Exception:
                        pass
                pool.shutdown(wait=False, cancel_futures=True)
                pool = ProcessPoolExecutor(max_workers=workers)
            for r in recs:
                c[r["status"]] += 1
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
            f.flush()
            done_n += len(recs)
            rate = done_n / max(time.time() - t0, 1)
            print(f"   {done_n}/{len(todo)} {dict(c)} | {rate * 60:.0f}/min "
                  f"ETA={(len(todo) - done_n) / max(rate, 1e-9) / 3600:.1f}h", flush=True)
    pool.shutdown(wait=False)
    return dict(c)


# ---------------------------------------------------------------- publicare
def _excerpt(text: str, v: dict | None) -> str:
    flat = re.sub(r"\s+", " ", text)
    start = v["decizie_start"] if v else 0
    return flat[start: start + EXCERPT_CHARS].strip()


def search_terms(texts: list[str]) -> collections.Counter:
    c = collections.Counter()
    for t in texts:
        c.update(w for w in _WORD.findall(norm(t)) if w not in STOP)
    return c


def publish() -> dict:
    plx, meta = _docs()
    last = _latest()
    docs, per_plx, clean_plx = {}, collections.defaultdict(collections.Counter), collections.defaultdict(set)
    c = collections.Counter()
    for u, m in meta.items():
        r = last.get(u)
        if not r:
            c["neprocesat"] += 1
            continue
        c[r.get("status")] += 1
        if r.get("status") != "ok":
            docs[u] = {"s": r.get("status"), **({"p": r["pagini"]} if r.get("pagini") else {})}
            continue
        text = r["text"]
        v = verdict(m["kind"], norm(text))
        rec = {"s": "ok", "x": _excerpt(text, v)}
        if r.get("pagini"):
            rec["p"] = r["pagini"]
        if r.get("ocr"):
            rec["o"] = 1
        if m["kind"] != m["tip"]:
            rec["k"] = m["kind"]
        if v:
            rec["v"] = {k: v[k] for k in ("verdict", "sursa", "amendamente", "vot", "observatii") if k in v}
        docs[u] = rec
        terms = search_terms([text])
        per_plx[m["idp"]].update(terms)
        if not r.get("ocr"):
            clean_plx[m["idp"]].update(terms)
    for p in plx:                                    # titlul intră și el în index
        per_plx[str(p["idp"])].update(search_terms([p.get("titlu") or ""]))
        clean_plx[str(p["idp"])].update(search_terms([p.get("titlu") or ""]))
    df = collections.Counter(w for cnt in per_plx.values() for w in cnt)
    n = max(len(per_plx), 1)
    termeni = {}
    for idp, cnt in per_plx.items():
        # zgomotul OCR e aproape mereu unic: un termen care apare într-un singur PLx rămâne doar dacă
        # vine din text nativ sau se repetă în dosar
        keep = [w for w, k in cnt.items() if df[w] / n <= DF_MAX
                and (df[w] > 1 or k > 1 or w in clean_plx[idp])]
        termeni[idp] = " ".join(sorted(keep))
    now = datetime.now(timezone.utc).isoformat()
    n_v = collections.Counter(f"{d['v']['sursa']}:{d['v']['verdict']}" for d in docs.values() if d.get("v"))
    json.dump({"generated_at": now, "sursa": "documentele PLx arhivate (cdep.ro), text nativ + OCR",
               "nota": "Extrase scurte; textul integral e pe cdep.ro. Verdictul e decizia comisiei din "
                       "fraza de decizie a avizului/raportului (extras automat).",
               "total": len(meta), "stare": dict(c), "verdicte": dict(n_v), "documente": docs},
              open(OUT_DOCS, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    json.dump({"generated_at": now, "total_plx": len(termeni),
               "nota": "Termeni normalizați (minuscule, fără diacritice) din titlul și documentele fiecărui PLx.",
               "termeni": termeni},
              open(OUT_SEARCH, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(f"PUBLICAT documente_text.json: {dict(c)} | verdicte {dict(n_v)} | "
          f"cautare_documente.json: {len(termeni)} PLx, "
          f"{sum(len(t.split()) for t in termeni.values())} termeni", flush=True)
    return {"stare": dict(c), "verdicte": dict(n_v)}


if __name__ == "__main__":
    # uz: python -m pipeline.build_comisii_docs [text|ocr|publish] [workers] [limit]
    cmd = sys.argv[1] if len(sys.argv) > 1 else "text"
    if cmd == "text":
        run_text()
    elif cmd == "ocr":
        run_ocr(int(sys.argv[2]) if len(sys.argv) > 2 else None, int(sys.argv[3]) if len(sys.argv) > 3 else None)
    publish()
