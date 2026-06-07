"""Colectează TOATE declarațiile de avere+interese de pe cfr.ro (toți angajații, 2020→prezent).

cfr.ro folosește pluginul FileBird: paginile declarații conțin un <div class="njt-fbdl"
data-json="..."> cu folder ID-ul; datele vin prin POST la /wp-json/filebird/v1/get-attachments
(fără nonce). Structură: an → central + 8 regionale → fișiere DA-*/DI-* în /wp-content/uploads/.

Pas 1 (acest script): BFS pe paginile declarații → extrage folder ID-uri → POST endpoint →
toate URL-urile PDF → scrie _cfr_pdfs.json {url: instituție}.
Pas 2: `ROMEGA_SRC=cfr python -m pipeline.harvest_reprocess text/ocr` → download+parse+OCR+nume.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import deque
from urllib.parse import urljoin

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from romega_core.parse import selector  # noqa: E402

V = os.path.join(ROOT, "data/v1/declaratii")
EP = "https://cfr.ro/wp-json/filebird/v1/get-attachments"
SEEDS = ["https://cfr.ro/declaratii-de-avere/", "https://cfr.ro/declaratii-de-interese/"]
RE_DECL = re.compile(r"cfr\.ro/declaratii-de-(avere|interese)", re.I)
HDRS = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"}


def _fetch_html(url: str) -> str:
    r = requests.get(url, timeout=25, headers={"User-Agent": "Mozilla/5.0"})
    r.encoding = "utf-8"
    return r.text if r.status_code == 200 else ""


def _folder_ids(html: str) -> list[str]:
    """Extrage selectedFolder din data-json al div-urilor njt-fbdl."""
    ids = []
    for div in selector(html).css("div.njt-fbdl"):
        dj = div.attrib.get("data-json", "")
        if not dj:
            continue
        try:
            cfg = json.loads(dj)
            sf = (cfg.get("request", {}) or {}).get("selectedFolder", [])
            ids.extend(sf)
        except Exception:
            pass
    return ids


def _files_for_folder(folder_id: str) -> list[dict]:
    body = {"pagination": {"current": 1, "limit": 5000}, "search": "",
            "orderBy": "post_title", "orderType": "ASC", "selectedFolder": [folder_id]}
    try:
        r = requests.post(EP, json=body, timeout=40, headers=HDRS)
        d = r.json()
    except Exception:
        return []
    return d.get("files", []) or []


def _label(url: str, page: str) -> str:
    """Etichetă instituție: CFR SA + regiune + an (din slug pagină + path upload)."""
    slug = page.rstrip("/").rsplit("/", 1)[-1]
    reg = re.sub(r"declaratii-de-(avere|interese)-?(si-interese-)?", "", slug).strip("-") or "central"
    ym = re.search(r"/uploads/(\d{4})/", url)
    an = ym.group(1) if ym else ""
    return f"CFR SA - {reg} {an}".strip()


def main() -> dict:
    os.makedirs(V, exist_ok=True)
    visited, queue = set(), deque(SEEDS)
    pages_with_folders, all_folders = [], {}
    # BFS: descoperă toate paginile declarații + folder ID-urile lor
    while queue:
        url = queue.popleft()
        if url in visited or len(visited) > 200:
            continue
        visited.add(url)
        html = _fetch_html(url)
        if not html:
            continue
        fids = _folder_ids(html)
        for fid in fids:
            all_folders.setdefault(fid, url)
        if fids:
            pages_with_folders.append((url, fids))
        # urmează linkuri declarații noi
        for a in selector(html).css("a"):
            h = a.attrib.get("href", "")
            full = urljoin(url, h)
            if RE_DECL.search(full) and full.split("#")[0].rstrip("/") not in visited:
                queue.append(full.split("#")[0])
    print(f"pagini declarații={len(visited)} | foldere FileBird unice={len(all_folders)}", flush=True)

    # interoghează fiecare folder → fișiere PDF
    pdf_to_inst, n_da, n_di = {}, 0, 0
    for fid, page in all_folders.items():
        files = _files_for_folder(fid)
        for f in files:
            u = f.get("url") or f.get("link") or ""
            if not u.lower().endswith(".pdf"):
                continue
            fn = u.rsplit("/", 1)[-1].upper()
            # doar 2020+
            ym = re.search(r"/uploads/(\d{4})/", u)
            if ym and int(ym.group(1)) < 2020:
                continue
            pdf_to_inst[u] = _label(u, page)
            if fn.startswith("DA") or "AVERE" in fn:
                n_da += 1
            elif fn.startswith("DI") or "INTERES" in fn:
                n_di += 1
        print(f"   folder {fid[:14]}… ({page.rsplit('/',1)[-1][:30]}): {len(files)} fișiere | total={len(pdf_to_inst)}", flush=True)

    json.dump(pdf_to_inst, open(os.path.join(V, "_cfr_pdfs.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"\nPUBLICAT _cfr_pdfs.json: {len(pdf_to_inst)} PDF-uri (DA~{n_da} DI~{n_di})", flush=True)
    print("Pas 2: ROMEGA_SRC=cfr python -m pipeline.harvest_reprocess text 8", flush=True)
    return {"pdfs": len(pdf_to_inst), "folders": len(all_folders)}


if __name__ == "__main__":
    main()
