"""Textul moțiunilor: OCR pe PDF-urile arhivate (aproape toate sunt scanate) → parlament/motiuni_text.json.

Textul integral se păstrează local în data/build/motiuni_text.jsonl (reluabil: o moțiune deja
citită nu se mai procesează). Se publică textul curățat și redactat de date personale, per moțiune.
Paginile cu listele de semnături (scris de mână) dau text slab; semnatarii nominali vin separat,
din pagina moțiunii (vezi harvest_motiuni).

    python -m pipeline.build_motiuni_text
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from connectors.ani.redaction import redact_text  # noqa: E402

V = os.path.join(ROOT, "data", "v1", "parlament")
RAW = os.path.join(ROOT, "data", "raw")
CACHE = os.path.join(ROOT, "data", "build", "motiuni_text.jsonl")
MAX_PAGINI = int(os.environ.get("SOLOMONAR_MOTIUNI_OCR_PAGES", "40"))
MIN_TEXT = 500            # sub atât, stratul de text lipsește și e nevoie de OCR


def _manifest_pdf() -> dict:
    out = {}
    with open(os.path.join(RAW, "manifest.jsonl"), encoding="utf-8") as fh:
        for line in fh:
            if '"mot_pdf"' not in line:
                continue
            try:
                m = json.loads(line)
            except ValueError:
                continue
            out[m["url"]] = m["path"]
    return out


def _curat(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def citeste_pdf(path: str) -> dict:
    """Textul unui PDF de moțiune: stratul de text dacă există, altfel OCR."""
    import pymupdf

    from connectors.ani.declaratii import extract_pdf_text_ocr

    with open(path, "rb") as fh:
        pdf = fh.read()
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        pagini = len(doc)
        text = "\n".join(p.get_text() for p in doc)
    ocr = len(text.strip()) < MIN_TEXT
    if ocr:
        text = extract_pdf_text_ocr(pdf, max_pages=MAX_PAGINI)
    return {"pagini": pagini, "ocr": ocr, "text": _curat(redact_text(text))}


def main() -> dict:
    with open(os.path.join(V, "motiuni.json"), encoding="utf-8") as fh:
        motiuni = json.load(fh)["motiuni"]
    cache = {}
    if os.path.exists(CACHE):
        with open(CACHE, encoding="utf-8") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                cache[r["pdf_url"]] = r
    manifest = _manifest_pdf()
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    noi = fara_pdf = 0
    with open(CACHE, "a", encoding="utf-8") as out:
        for i, m in enumerate(motiuni, 1):
            url = m.get("pdf_url")
            if not url or url in cache:
                continue
            if url not in manifest:
                fara_pdf += 1
                continue
            try:
                rez = citeste_pdf(os.path.join(RAW, manifest[url].replace("\\", os.sep)))
            except Exception as e:  # un PDF corupt nu oprește restul
                print(f"   ! {m.get('idm')}: {type(e).__name__} {str(e)[:80]}", flush=True)
                continue
            cache[url] = {"pdf_url": url, **rez}
            out.write(json.dumps(cache[url], ensure_ascii=False) + "\n")
            out.flush()
            noi += 1
            if noi % 10 == 0:
                print(f"   {noi} moțiuni citite ({i}/{len(motiuni)})", flush=True)
    randuri = []
    for m in motiuni:
        c = cache.get(m.get("pdf_url"))
        if c and c.get("text"):
            randuri.append({"idm": m["idm"], "leg": m["leg"], "cam": m["cam"], "pagini": c["pagini"],
                            "ocr": c["ocr"], "trunchiat": c["ocr"] and c["pagini"] > MAX_PAGINI, "text": c["text"]})
    with open(os.path.join(V, "motiuni_text.json"), "w", encoding="utf-8") as fh:
        json.dump({"generated_at": datetime.now(timezone.utc).isoformat(), "total": len(randuri),
                   "nota": "Text citit automat (OCR) din PDF-urile scanate; poate conține erori de "
                           "recunoaștere. Documentul original e la pdf_url, în motiuni.json.",
                   "motiuni": randuri}, fh, ensure_ascii=False, indent=1)
    print(f"PUBLICAT motiuni_text.json: {len(randuri)} moțiuni cu text | citite acum: {noi} | "
          f"fără PDF local: {fara_pdf}", flush=True)
    return {"cu_text": len(randuri), "noi": noi}


if __name__ == "__main__":
    main()
