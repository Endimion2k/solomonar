"""Procesează CV-urile conducerii — extrage parcursul școlar (studii) și profesional (experiență).

Input: _cv_pdfs.json (168 CV-PDF din harvest_cv). Download + text (pdfplumber) → extrage:
- nume (din filename), entitate
- STUDII (context în jurul: studii/educație/facultate/universitate/licență/master/doctorat)
- EXPERIENȚĂ (context: experiență/activitate profesională/funcția/perioada/angajator)
CV-uri scanate (text <120 ch) → marcate (OCR ulterior). Output cv.json.
"""

from __future__ import annotations

import io
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from romega_core.bronze import BronzeStore  # noqa: E402
from romega_core.http import Client  # noqa: E402

V = os.path.join(ROOT, "data/v1")
bronze = BronzeStore(os.path.join(ROOT, "data", "raw"))
client = Client(bronze=bronze, throttle_seconds=0.1, timeout=20)

RE_EDU = re.compile(r"(studii|educa[țt]i|formare|absolv|facult|universit|licen[țt]|master|"
                    r"doctor|colegiu|liceu|diplom|specializ)", re.I)
RE_EXP = re.compile(r"(experien[țt]|activitate profesional|funct|angajator|perioad|"
                    r"director|manager|sef|consilier|inginer|economist|\d{4}\s*[-–]\s*\d{4}|"
                    r"\d{4}\s*[-–]\s*prezent)", re.I)


def _name_from_url(url: str) -> str:
    from urllib.parse import unquote
    fn = unquote(url.rsplit("/", 1)[-1])
    fn = re.sub(r"\.pdf$", "", fn, flags=re.I)
    s = re.sub(r"[._\-+]+", " ", fn)
    s = re.sub(r"\b(cv|curriculum|vitae|europ?ass?|ro|en|final|\d+)\b", " ", s, flags=re.I)
    toks = [t for t in s.split() if len(t) >= 2 and re.match(r"[A-Za-zĂÂÎȘȚăâîșț]", t)]
    return " ".join(toks).upper().strip()[:80]


def _extract_text(pdf_bytes: bytes) -> str:
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            return "\n".join((p.extract_text() or "") for p in pdf.pages[:8])
    except Exception:
        return ""


def _sections(text: str) -> tuple[str, str]:
    """Extrage blocuri de studii + experiență (linii care conțin sau urmează keyword-uri)."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    edu, exp = [], []
    for i, l in enumerate(lines):
        if RE_EDU.search(l):
            edu.append(l[:200])
        if RE_EXP.search(l):
            exp.append(l[:200])
    return (" | ".join(dict.fromkeys(edu))[:1200], " | ".join(dict.fromkeys(exp))[:1500])


def _process(item):
    url, ent = item
    try:
        content, _ = client.fetch(url, "cv_pdf", ".pdf")
        text = _extract_text(content)
    except Exception:
        return None
    if len(text) < 120:
        return {"nume": _name_from_url(url), "entitate": ent, "url": url, "status": "scanat"}
    edu, exp = _sections(text)
    return {"nume": _name_from_url(url), "entitate": ent, "url": url, "status": "ok",
            "studii": edu, "experienta": exp, "text_len": len(text)}


def main() -> dict:
    pdfs = list(json.load(open(os.path.join(V, "declaratii/_cv_pdfs.json"), encoding="utf-8")).items())
    print(f"procesez {len(pdfs)} CV-PDF...", flush=True)
    out, ok, scan = [], 0, 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = [ex.submit(_process, it) for it in pdfs]
        for f in as_completed(futs):
            r = f.result()
            if not r:
                continue
            out.append(r)
            if r["status"] == "ok":
                ok += 1
            else:
                scan += 1
    out.sort(key=lambda x: (x["entitate"], x["nume"]))
    json.dump({"total": len(out), "cu_text": ok, "scanate": scan, "cv": out},
              open(os.path.join(V, "companii/cv.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    cu_studii = sum(1 for r in out if r.get("studii"))
    cu_exp = sum(1 for r in out if r.get("experienta"))
    print(f"PUBLICAT cv.json: {len(out)} CV-uri ({ok} text, {scan} scanate) | "
          f"cu studii={cu_studii} cu experienta={cu_exp}", flush=True)
    return {"total": len(out), "ok": ok}


if __name__ == "__main__":
    import urllib3
    urllib3.disable_warnings()
    main()
