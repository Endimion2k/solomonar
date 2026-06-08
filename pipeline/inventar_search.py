"""Search-pass: găsește paginile de declarații pt. companiile NEgăsite de brand-guess (DuckDuckGo).

Brand-guess a prins ~91/1256 companii (domeniu=brand). Restul au domenii neghicibile (Hidroelectrica
→ hidro.ro) sau publică prin primărie. Aici căutăm '{nume} declaratii de avere' pe DDG → primul
rezultat care arată a pagină de declarații (URL conține declaratii/avere, domeniu ne-presă).

Incremental + reluabil (checkpoint). Throttled (DDG blochează scraping agresiv).
Scrie _inventar_search_found.jsonl → de îmbinat în inventar_declaratii.json.
"""

from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import unquote, urlparse

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V = os.path.join(ROOT, "data/v1")
FOUND = os.path.join(V, "companii/_inventar_search_found.jsonl")
CHECKED = os.path.join(V, "companii/_inventar_search_checked.txt")
HDRS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
_NEWS = ("ziar", "presa", "stiri", "news", "facebook", "wikipedia", "linkedin", "youtube",
         "g4media", "hotnews", "digi24", "libertatea", "adevarul", "profit.ro", "economica",
         "monitoruljuridic", "lege5", "scribd", "scol", "anaf.ro", "listafirme", "mfinante",
         "termene.ro", "risco.ro", "confidas", "topfirme", "data.gov")
_LOCK = threading.Lock()


def _norm(s):
    return " ".join(sorted(re.findall(r"[a-z0-9]{2,}",
            unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower())))


def _ddg(query: str) -> list[str]:
    try:
        r = requests.post("https://html.duckduckgo.com/html/", data={"q": query},
                          headers=HDRS, timeout=15)
        urls = [unquote(u) for u in re.findall(r'uddg=([^&"]+)', r.text)]
        return urls
    except Exception:
        return []


def _pick(urls: list[str]) -> str | None:
    """Primul rezultat care arată a pagină de declarații pe domeniu ne-presă."""
    for u in urls:
        ul = u.lower()
        if not ul.startswith("http"):
            continue
        if any(n in ul for n in _NEWS):
            continue
        if re.search(r"declaratii|declaratie|avere|integritate|interese", ul):
            return u
    return None


def main() -> dict:
    comps = json.load(open(os.path.join(V, "companii/_index.json"), encoding="utf-8"))["data"]
    # companii deja găsite (brand-guess) — sări peste
    found_names = set()
    inv = os.path.join(V, "companii/inventar_declaratii.json")
    if os.path.exists(inv):
        for s in json.load(open(inv, encoding="utf-8")).get("surse", []):
            if s.get("tip") == "companie":
                found_names.add(_norm(s["nume"]))
    checked = set(open(CHECKED, encoding="utf-8").read().splitlines()) if os.path.exists(CHECKED) else set()
    todo = [c for c in comps if c.get("name") and _norm(c["name"]) not in found_names
            and c["name"] not in checked]
    prev = sum(1 for _ in open(FOUND, encoding="utf-8")) if os.path.exists(FOUND) else 0
    print(f"de cautat: {len(todo)} companii (deja gasite brand={len(found_names)}, "
          f"cautate anterior={len(checked)}, gasite-search anterior={prev})", flush=True)

    fh_f = open(FOUND, "a", encoding="utf-8")
    fh_c = open(CHECKED, "a", encoding="utf-8")
    done, hit = 0, 0

    def _work(c):
        time.sleep(0.8)  # throttle DDG
        urls = _ddg(f"{c['name']} declaratii de avere")
        return c, _pick(urls)

    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = [ex.submit(_work, c) for c in todo]
        for f in as_completed(futs):
            c, url = f.result()
            done += 1
            with _LOCK:
                fh_c.write(c["name"] + "\n"); fh_c.flush()
                if url:
                    hit += 1
                    rec = {"nume": c["name"], "cui": c.get("cui"), "tip": "companie",
                           "url": url, "mecanism": "search", "via": "ddg"}
                    fh_f.write(json.dumps(rec, ensure_ascii=False) + "\n"); fh_f.flush()
                    print(f"   ✔ [{prev + hit}] {c['name'][:40]} → {urlparse(url).netloc}", flush=True)
            if done % 100 == 0:
                print(f"   ...{done}/{len(todo)} cautate, +{hit} gasite", flush=True)
    fh_f.close(); fh_c.close()
    print(f"\nGATA search: +{hit} surse noi din {done} cautari", flush=True)
    return {"gasite": hit, "cautate": done}


if __name__ == "__main__":
    main()
