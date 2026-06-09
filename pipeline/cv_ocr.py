"""OCR pe CV-urile scanate (status='scanat' în cv.json) — extrage studii/experiență din imagini.

Refolosește engine-ul GPU (extract_pdf_text_ocr din connectors.ani.declaratii) + parserul de
secțiuni din process_cv. ProcessPool(2) ca la declarații. Actualizează cv.json in-place.
"""

from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

V = os.path.join(ROOT, "data/v1")


def _ocr_one(url: str):
    sys.path.insert(0, ROOT)
    from connectors.ani.declaratii import extract_pdf_text_ocr
    from pipeline.process_cv import _sections, client
    try:
        content, _ = client.fetch(url, "cv_pdf", ".pdf")
        text = extract_pdf_text_ocr(content, dpi=200, max_pages=10, max_px=2400)
    except Exception:
        return url, None
    if len(text or "") < 120:
        return url, None
    edu, exp = _sections(text)
    return url, {"studii": edu, "experienta": exp}


def main(workers: int = 2) -> dict:
    cv = json.load(open(os.path.join(V, "companii/cv.json"), encoding="utf-8"))
    scan = [r for r in cv["cv"] if r.get("status") == "scanat"]
    print(f"OCR pe {len(scan)} CV-uri scanate ({workers} workers)...", flush=True)
    by_url = {r["url"]: r for r in cv["cv"]}
    ok = 0
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_ocr_one, r["url"]): r["url"] for r in scan}
        for i, f in enumerate(as_completed(futs), 1):
            url, res = f.result()
            if res and (res["studii"] or res["experienta"]):
                r = by_url[url]
                r["status"] = "ok_ocr"; r["studii"] = res["studii"]; r["experienta"] = res["experienta"]
                ok += 1
            if i % 25 == 0:
                print(f"   {i}/{len(scan)} OCR-izate, {ok} cu date", flush=True)
    cv["cu_text"] = sum(1 for r in cv["cv"] if r.get("studii") or r.get("experienta"))
    cv["scanate"] = sum(1 for r in cv["cv"] if r.get("status") == "scanat")
    cv["ocr_izate"] = ok
    json.dump(cv, open(os.path.join(V, "companii/cv.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"PUBLICAT cv.json: +{ok} CV OCR-izate cu studii/experiență | total cu date={cv['cu_text']}", flush=True)
    return {"ocr": ok}


if __name__ == "__main__":
    import urllib3
    urllib3.disable_warnings()
    main(workers=int(sys.argv[1]) if len(sys.argv) > 1 else 2)
