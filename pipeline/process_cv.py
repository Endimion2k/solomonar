"""Procesează CV-urile conducerii (parcurs școlar + profesional). Două forme:

A. CV-PDF (per-persoană): download + text → nume (din filename) + studii + experiență.
B. Bio inline (pagini conducere): fetch HTML → extrage studii/experiență + nume-candidați din pagină.
   Filtrăm la pagini de conducere reale (excludem concurs/anunț = cerințe post, nu CV-uri).

Output: cv.json (PDF, per-persoană) + cv_inline.json (bio pe pagină/entitate).
"""

from __future__ import annotations

import io
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import unquote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from solomonar_core.bronze import BronzeStore  # noqa: E402
from solomonar_core.http import Client  # noqa: E402
from solomonar_core.parse import selector  # noqa: E402

V = os.path.join(ROOT, "data/v1")
bronze = BronzeStore(os.path.join(ROOT, "data", "raw"))
client = Client(bronze=bronze, throttle_seconds=0.08, timeout=20)

RE_EDU = re.compile(r"(studii|educa[țt]i|formare|absolv|facult|universit|licen[țt]|master|"
                    r"doctor|colegiu|liceu|diplom|specializ|academ)", re.I)
RE_EXP = re.compile(r"(experien[țt]|activitate profesional|funct|angajator|perioad|"
                    r"director|manager|[șs]ef |consilier|inginer|economist|\d{4}\s*[-–]\s*\d{4}|"
                    r"\d{4}\s*[-–]\s*prezent)", re.I)
# pagini inline REALE de conducere (nu concurs/cerinte)
RE_COND_URL = re.compile(r"conducer|management|echipa|demnitar|cabinet|membri|secretar|director|"
                         r"guvernanta|consiliul", re.I)
RE_NOISE_URL = re.compile(r"concurs|anunt|post-vacant|posturi|cariera|cariere|selectie|recrut", re.I)
RE_NAME = re.compile(r"\b([A-ZȘȚĂÂÎ][a-zșțăâî]{2,}(?:[- ][A-ZȘȚĂÂÎ][a-zșțăâî]{2,}){1,3})\b")


def _name_from_url(url):
    fn = re.sub(r"\.pdf$", "", unquote(url.rsplit("/", 1)[-1]), flags=re.I)
    s = re.sub(r"[._\-+]+", " ", fn)
    s = re.sub(r"\b(cv|curriculum|vitae|europ?ass?|ro|en|final|actualizat|\d+)\b", " ", s, flags=re.I)
    toks = [t for t in s.split() if len(t) >= 2 and re.match(r"[A-Za-zĂÂÎȘȚăâîșț]", t)]
    return " ".join(toks).upper().strip()[:80]


def _sections(text):
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    edu = [l[:200] for l in lines if RE_EDU.search(l)]
    exp = [l[:200] for l in lines if RE_EXP.search(l)]
    return " | ".join(dict.fromkeys(edu))[:1400], " | ".join(dict.fromkeys(exp))[:1600]


def _proc_pdf(item):
    url, ent = item
    try:
        content, _ = client.fetch(url, "cv_pdf", ".pdf")
        import pdfplumber
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            text = "\n".join((p.extract_text() or "") for p in pdf.pages[:8])
    except Exception:
        return None
    if len(text) < 120:
        return {"nume": _name_from_url(url), "entitate": ent, "url": url, "status": "scanat"}
    edu, exp = _sections(text)
    return {"nume": _name_from_url(url), "entitate": ent, "url": url, "status": "ok",
            "studii": edu, "experienta": exp}


_RE_EDU_STRICT = re.compile(r"(universitat\w*|facultat\w*|absolvit|licen[țt]iat|"
                            r"masterat|master[au]?l? (?:[îiI]n|de|la)|doctor(?:at|and)|"
                            r"diplom[ăa] de|[îi]nv[ăa][țt][ăa]m[âa]nt superior|academia)\s+[A-ZȘȚĂÂÎ\"]", re.I)
_RE_EXP_STRICT = re.compile(r"(\d{4}\s*[-–]\s*(?:\d{4}|prezent)|perioad[ăa]\s*:?\s*\d|"
                            r"func[țt]ia\s*:?\s*[A-ZȘȚĂÂÎ]|director (?:general|executiv|adjunct))", re.I)


def _proc_inline(item):
    url, ent = item
    if RE_NOISE_URL.search(url) or not RE_COND_URL.search(url):
        return None  # filtrăm concurs/cariere (cerințe post, nu CV)
    try:
        content, _ = client.fetch(url, "cv_inl", ".html", use_cache=True)
        t = content.decode("utf-8", "ignore") if isinstance(content, bytes) else content
    except Exception:
        return None
    # scoate script/style/nav/header/footer (sursa de zgomot: meniuri + JS)
    t2 = re.sub(r"(?is)<(script|style|nav|header|footer)[^>]*>.*?</\1>", " ", t)
    body = re.sub(r"[ \t]+", " ", re.sub(r"<[^>]+>", "\n", t2))
    lines = [l.strip() for l in body.splitlines() if l.strip() and len(l.strip()) > 15]
    # markeri STRICȚI (instituție/an reali, nu cuvinte de meniu)
    edu = [l[:220] for l in lines if _RE_EDU_STRICT.search(l)]
    exp = [l[:220] for l in lines if _RE_EXP_STRICT.search(l)]
    if not edu and not exp:
        return None
    sel = selector(t2)
    heads = " ".join(" ".join(e.css("::text").getall()) for e in sel.css("h1,h2,h3,h4"))
    bad = re.compile(r"meniu|harta|map|strateg|raport|urbanism|cetateni|registratura|primari|consiliu", re.I)
    names = [n for n in dict.fromkeys(RE_NAME.findall(heads)) if not bad.search(n)][:8]
    return {"entitate": ent, "url": url, "nume_candidati": names,
            "studii": " | ".join(dict.fromkeys(edu))[:1400],
            "experienta": " | ".join(dict.fromkeys(exp))[:1600]}


def main() -> dict:
    pdfs = list(json.load(open(os.path.join(V, "declaratii/_cv_pdfs.json"), encoding="utf-8")).items())
    inl = list(json.load(open(os.path.join(V, "declaratii/_cv_inline.json"), encoding="utf-8")).items()) \
        if os.path.exists(os.path.join(V, "declaratii/_cv_inline.json")) else []
    print(f"procesez {len(pdfs)} CV-PDF + {len(inl)} pagini inline...", flush=True)

    out_pdf, out_inl = [], []
    with ThreadPoolExecutor(max_workers=8) as ex:
        for r in ex.map(_proc_pdf, pdfs):
            if r:
                out_pdf.append(r)
    with ThreadPoolExecutor(max_workers=8) as ex:
        for r in ex.map(_proc_inline, inl):
            if r:
                out_inl.append(r)

    out_pdf.sort(key=lambda x: (x["entitate"], x["nume"]))
    ok = sum(1 for r in out_pdf if r["status"] == "ok")
    scan = sum(1 for r in out_pdf if r["status"] == "scanat")
    json.dump({"total": len(out_pdf), "cu_text": ok, "scanate": scan, "cv": out_pdf},
              open(os.path.join(V, "companii/cv.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    out_inl.sort(key=lambda x: x["entitate"])
    json.dump({"total": len(out_inl), "bio": out_inl},
              open(os.path.join(V, "companii/cv_inline.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"PUBLICAT cv.json: {len(out_pdf)} CV-PDF ({ok} text, {scan} scanate) | "
          f"cv_inline.json: {len(out_inl)} bio-uri conducere (din {len(inl)} pagini)", flush=True)
    return {"pdf": len(out_pdf), "inline": len(out_inl)}


if __name__ == "__main__":
    import urllib3
    urllib3.disable_warnings()
    main()
