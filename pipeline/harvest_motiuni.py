"""Harvest moțiuni parlamentare CDep (simple + de cenzură), toate legislaturile → SOLOMONAR.

Pe cdep.ro moțiunile-s în liste separate pe tip: motiuni2015.lista?cam=2 (simple Camera
Deputaților) și cam=0 (de cenzură, ambele camere). Userul vedea doar cele 6 simple (curente) —
cenzura e listă distinctă. Aici le luăm pe TOATE (cam 0+2 × legislaturi) cu detalii + PDF.

Fișă: detalii?leg={leg}&cam={cam}&idm={idm} → titlu, dată înregistrare, rezultat, voturi, PDF.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from urllib.parse import urljoin

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from solomonar_core.bronze import BronzeStore  # noqa: E402
from solomonar_core.http import Client  # noqa: E402
from solomonar_core.parse import selector  # noqa: E402

V = os.path.join(ROOT, "data/v1/parlament")
BASE = "https://www.cdep.ro/ords/pls/parlam/"
LEGS = [2024, 2020, 2016, 2012, 2008, 2004, 2000]
CAMS = {0: "cenzura", 2: "simpla_cdep"}


def _lista_motiuni(client, cam, leg):
    url = f"{BASE}motiuni2015.lista?cam={cam}&leg={leg}"
    try:
        content, _ = client.fetch(url, "mot_lista", ".html")
    except Exception:
        return []
    t = content.decode("utf-8", "ignore") if isinstance(content, bytes) else content
    out = []
    for a in selector(t).css("a"):
        h = a.attrib.get("href", "")
        m = re.search(r"detalii\?leg=(\d+)&cam=(\d+)&idm=(\d+)", h)
        if m:
            titlu = " ".join(a.css("::text").getall()).strip()
            out.append({"idm": int(m.group(3)), "leg": int(m.group(1)), "cam": int(m.group(2)),
                        "titlu": titlu[:200], "url": urljoin(BASE, h)})
    return out


def _detalii(client, mot):
    try:
        content, _ = client.fetch(mot["url"], "mot_det", ".html")
    except Exception:
        return mot
    t = content.decode("utf-8", "ignore") if isinstance(content, bytes) else content
    body = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t))
    if not mot.get("titlu"):
        mt = re.search(r"Titlu\s*:?\s*([^|]{6,180}?)\s*(Data|Tip|Ini[tţ]iator)", body)
        mot["titlu"] = mt.group(1).strip()[:200] if mt else ""
    md = re.search(r"(\d{2}\.\d{2}\.\d{4})", body)
    mot["data"] = md.group(1) if md else None
    mr = re.search(r"(Adoptat[ăa]|Respins[ăa]|Dezbatere|Retras[ăa])", body, re.I)
    mot["rezultat"] = mr.group(1).capitalize() if mr else None
    vp = re.search(r"pentru mo[tţ]iune\D{0,8}(\d+)", body, re.I)
    vc = re.search(r"[iî]mpotriv\w*\D{0,8}(\d+)", body, re.I)
    mot["voturi_pentru"] = int(vp.group(1)) if vp else None
    mot["voturi_contra"] = int(vc.group(1)) if vc else None
    pdfs = [urljoin(mot["url"], a.attrib.get("href", "")) for a in selector(t).css("a")
            if a.attrib.get("href", "").lower().endswith(".pdf")]
    mot["pdf_url"] = pdfs[0] if pdfs else None
    return mot


def main() -> dict:
    os.makedirs(V, exist_ok=True)
    bronze = BronzeStore(os.path.join(ROOT, "data", "raw"))
    client = Client(bronze=bronze, throttle_seconds=0.3, timeout=20)
    motiuni = []
    for cam, tip in CAMS.items():
        for leg in LEGS:
            rows = _lista_motiuni(client, cam, leg)
            for r in rows:
                r["tip"] = tip
                motiuni.append(_detalii(client, r))
            if rows:
                print(f"   cam={cam} ({tip}) leg={leg}: {len(rows)} moțiuni", flush=True)
    # descarcă PDF-urile moțiunilor
    pdfs = [m["pdf_url"] for m in motiuni if m.get("pdf_url")]
    dl = client.fetch_many([(u, "mot_pdf", ".pdf") for u in pdfs], workers=6) if pdfs else {}
    arh = sum(1 for v in dl.values() if v)
    by_tip = {}
    for m in motiuni:
        by_tip[m["tip"]] = by_tip.get(m["tip"], 0) + 1
    json.dump({"generated_at": datetime.now(timezone.utc).isoformat(), "total": len(motiuni),
               "pe_tip": by_tip, "pdf_arhivate": arh, "motiuni": motiuni},
              open(os.path.join(V, "motiuni.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"PUBLICAT motiuni.json: {len(motiuni)} ({by_tip}) | PDF arhivate={arh}", flush=True)
    return {"total": len(motiuni), "pe_tip": by_tip}


if __name__ == "__main__":
    main()
