"""Anul declarațiilor SCANATE, citit prin OCR din „Data completării” de pe ultimele pagini.

Declarațiile scanate au fost deja trecute prin OCR la colectare (agregate de avere, entități), dar
textul nu s-a păstrat, deci data completării lipsește. Aici se face OCR doar pe ultimele pagini ale
PDF-urilor scanate care nu au niciun an (nici în numele fișierului, nici în cale).

Rezultat: data/build/declaratii_an_ocr.jsonl, un rând per PDF: {url, an_document | null, pagini_ocr}.
`build_declaratii_detaliu` îl folosește cu `an_sursa = "document_ocr"`.

    python -m pipeline.ocr_an_declaratii            # toate cele fără an
    python -m pipeline.ocr_an_declaratii 60         # doar primele 60 (probă)

Reluabil. `SOLOMONAR_OCR_WORKERS` = procese (implicit 2, vezi benchmark-ul din connectors/ani/declaratii.py).
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from pipeline.extract_declaratii_tabele import OUT as DETALIU, RAW, V, _manifest  # noqa: E402

OUT = os.path.join(ROOT, "data", "build", "declaratii_an_ocr.jsonl")
PRIMUL_AN = 2008                    # ca în build_declaratii_detaliu: formularele Legii 176/2010
MAX_PAGINI = 2                      # data completării e la sfârșit; a doua pagină din coadă = plasă de siguranță
DPI = 200
MAX_PX = 2400                       # latura lungă maximă, ca scanele uriașe să nu depășească memoria GPU
FLUSH_LA = 50
# OCR-ul rupe diacriticele și pune spații/virgule în dată: „Data completarii: 12 .06, 2019”
_RE_DATA_OCR = re.compile(r"complet\w{0,6}[\s\S]{0,80}?(\d{1,2})\s?[.\-/,: ]\s?(\d{1,2})\s?[.\-/,: ]\s?(20\d{2})(?!\d)",
                          re.I)


def an_din_text_ocr(text: str, an_curent: int) -> int | None:
    """Anul din data completării într-un text OCR; None dacă nu e o dată plauzibilă.

    Regexul e mai îngăduitor decât cel pentru PDF-urile cu text, așa că ziua și luna se verifică.
    """
    gasite = [(int(z), int(l), int(a)) for z, l, a in _RE_DATA_OCR.findall(text or "")]
    gasite = [g for g in gasite if 1 <= g[0] <= 31 and 1 <= g[1] <= 12 and PRIMUL_AN <= g[2] <= an_curent]
    return gasite[-1][2] if gasite else None


def _ocr_pagina(doc, i: int) -> str:
    import pymupdf as fitz
    import numpy as np

    from connectors.ani.declaratii import _ocr_engine

    page = doc[i]
    zoom = min(DPI / 72.0, MAX_PX / (max(page.rect.width, page.rect.height) or 1.0))
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    if pix.n == 4:
        img = img[:, :, :3]
    res, _ = _ocr_engine()(img, use_cls=False)
    return "\n".join(r[1] for r in res) if res else ""


def _lucru(arg: tuple) -> dict:
    url, path, an_curent = arg
    import pymupdf as fitz

    rec = {"url": url, "an_document": None, "pagini_ocr": 0}
    try:
        with fitz.open(path) as doc:
            for i in range(len(doc) - 1, max(len(doc) - 1 - MAX_PAGINI, -1), -1):
                rec["pagini_ocr"] += 1
                an = an_din_text_ocr(_ocr_pagina(doc, i), an_curent)
                if an:
                    rec["an_document"] = an
                    break
    except Exception as e:  # PDF corupt sau memorie GPU: rămâne fără an, se vede în statistică
        rec["eroare"] = f"{type(e).__name__}: {str(e)[:80]}"
    return rec


def _citeste_jsonl(path: str) -> dict:
    out = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                out[r.get("url")] = r
    return out


def de_facut() -> list[str]:
    """URL-urile PDF-urilor scanate ale căror declarații publicate nu au niciun an."""
    scanate = {u for u, r in _citeste_jsonl(DETALIU).items() if not r.get("strat_text")}
    out, vazute = [], set()
    for path in sorted(glob.glob(os.path.join(V, "*.json"))):
        if os.path.basename(path).split("_")[0] not in ("avere", "interese"):
            continue
        with open(path, encoding="utf-8") as fh:
            recs = json.load(fh).get("declaratii") or []
        for r in recs:
            url = r.get("pdf_url")
            if url in scanate and url not in vazute and (r.get("an") is None or r.get("an_sursa") == "document_ocr"):
                vazute.add(url)
                out.append(url)
    return out


def main(limita: int | None = None) -> dict:
    an_curent = datetime.now(timezone.utc).year
    facute = set(_citeste_jsonl(OUT))
    manifest = _manifest()
    todo = [(u, os.path.join(RAW, manifest[u].replace("\\", os.sep)), an_curent)
            for u in de_facut() if u not in facute and u in manifest]
    if limita:
        todo = todo[:limita]
    procese = int(os.environ.get("SOLOMONAR_OCR_WORKERS", "2"))
    print(f"[ocr-an] de procesat={len(todo)} | deja={len(facute)} | {procese} procese, max {MAX_PAGINI} pagini/doc",
          flush=True)
    stat = {"procesate": 0, "cu_an": 0, "erori": 0}
    t0 = time.time()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "a", encoding="utf-8") as out, ProcessPoolExecutor(max_workers=procese) as pool:
        for rec in pool.map(_lucru, todo, chunksize=2):
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            stat["procesate"] += 1
            stat["cu_an"] += rec["an_document"] is not None
            stat["erori"] += "eroare" in rec
            if stat["procesate"] % FLUSH_LA == 0:
                out.flush()
                ritm = stat["procesate"] / max(time.time() - t0, 1) * 60
                print(f"   {stat['procesate']}/{len(todo)} {stat} | {ritm:.0f}/min "
                      f"ETA={(len(todo) - stat['procesate']) / max(ritm, 1e-9) / 60:.1f}h", flush=True)
    print(f"OCR AN declarații: {stat}", flush=True)
    return stat


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else None)
