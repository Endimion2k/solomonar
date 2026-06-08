"""Harvester GENERAL de declarații SOE/instituții — atacă cele din inventar_declaratii.json.

Generalizează CFR: pentru fiecare sursă, BFS pe pagină (depth ≤3, același domeniu) și colectează:
- PDF-uri declarații directe (DA-/DI-/avere/interese sau nume-persoană în foldere de declarații)
- fișiere FileBird (POST /wp-json/filebird/v1/get-attachments cu folder ID din data-json)
- urmărește sub-pagini (linkuri 'declaratii-*' / an / regiune)

Scrie _soe_pdfs.json {url: 'NumeEntitate'}. Pas 2: ROMEGA_SRC=soe harvest_reprocess text/ocr.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from romega_core.parse import selector  # noqa: E402

V = os.path.join(ROOT, "data/v1")
FB_EP_PATH = "/wp-json/filebird/v1/get-attachments"
RE_DECL_LINK = re.compile(r"declaratii|integritate|avere|interese", re.I)
RE_PDF_DECL = re.compile(r"(da[-_ ]|di[-_ ]|avere|interes|declarat|^[a-zăâîșț]+[-_ ][a-zăâîșț]+)", re.I)
HDRS = {"User-Agent": "Mozilla/5.0"}


def _get(url, timeout=15):
    try:
        r = requests.get(url, timeout=timeout, headers=HDRS, verify=False)
        r.encoding = "utf-8"
        return r.text if r.status_code == 200 else ""
    except Exception:
        return ""


def _filebird_files(base: str, html: str) -> list[str]:
    """Extrage folder ID-uri din data-json + POST endpoint → URL-uri fișiere."""
    folders = []
    for div in selector(html).css("div.njt-fbdl"):
        dj = div.attrib.get("data-json", "")
        try:
            sf = (json.loads(dj).get("request", {}) or {}).get("selectedFolder", [])
            folders.extend(sf)
        except Exception:
            pass
    urls = []
    for fid in set(folders):
        try:
            r = requests.post(base + FB_EP_PATH, json={"pagination": {"current": 1, "limit": 5000},
                              "search": "", "orderBy": "post_title", "orderType": "ASC",
                              "selectedFolder": [fid]}, timeout=30, headers={**HDRS, "Content-Type": "application/json"})
            for f in r.json().get("files", []) or []:
                u = f.get("url") or f.get("link") or ""
                if u.lower().endswith(".pdf"):
                    urls.append(u)
        except Exception:
            pass
    return urls


def _pdfs_on_page(base: str, html: str) -> list[str]:
    out = []
    for a in selector(html).css("a"):
        h = a.attrib.get("href", "")
        if h.lower().endswith(".pdf"):
            fn = h.rsplit("/", 1)[-1]
            if RE_PDF_DECL.search(fn) and not any(g in h.lower() for g in
                    ("politica", "cookie", "termeni", "corona", "anexa", "formular", "model", "ghid")):
                out.append(urljoin(base, h))
    return out


def harvest_source(src: dict) -> tuple[str, dict]:
    """BFS pe o sursă → {pdf_url: nume_entitate}."""
    start = src["url"]
    name = src["nume"]
    root = f"{urlparse(start).scheme}://{urlparse(start).netloc}"
    visited, queue, pdfs = set(), deque([start]), {}
    while queue and len(visited) < 60:
        url = queue.popleft()
        if url in visited:
            continue
        visited.add(url)
        html = _get(url)
        if not html:
            continue
        for u in _pdfs_on_page(root, html):
            pdfs[u] = name
        for u in _filebird_files(root, html):
            pdfs[u] = name
        # urmează sub-pagini de declarații (același domeniu)
        for a in selector(html).css("a"):
            h = a.attrib.get("href", "")
            full = urljoin(url, h).split("#")[0]
            if (RE_DECL_LINK.search(h) and urlparse(full).netloc == urlparse(start).netloc
                    and full not in visited and len(queue) < 80):
                queue.append(full)
    return name, pdfs


def main(limit: int = 0) -> dict:
    inv = json.load(open(os.path.join(V, "companii/inventar_declaratii.json"), encoding="utf-8"))
    surse = inv["surse"]
    if limit:
        surse = surse[:limit]
    print(f"atac {len(surse)} surse (BFS multi-mecanism)...", flush=True)
    all_pdfs, done = {}, 0
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = [ex.submit(harvest_source, s) for s in surse]
        for f in as_completed(futs):
            done += 1
            try:
                name, pdfs = f.result()
            except Exception:
                continue
            all_pdfs.update(pdfs)
            if pdfs:
                print(f"   [{done}/{len(surse)}] {name[:40]}: +{len(pdfs)} PDF (total={len(all_pdfs)})", flush=True)
    json.dump(all_pdfs, open(os.path.join(V, "declaratii/_soe_pdfs.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"\nPUBLICAT _soe_pdfs.json: {len(all_pdfs)} PDF-uri din {len(surse)} surse", flush=True)
    print("Pas 2: ROMEGA_SRC=soe python -m pipeline.harvest_reprocess text 8", flush=True)
    return {"pdfs": len(all_pdfs), "surse": len(surse)}


if __name__ == "__main__":
    import urllib3
    urllib3.disable_warnings()
    main(limit=int(sys.argv[1]) if len(sys.argv) > 1 else 0)
