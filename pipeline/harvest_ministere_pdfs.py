"""Checkpoint PDF pentru MINISTERE + AGENȚII — crawl UNCAPPED al secțiunilor de declarații.

Vechiul harvest_declaratii_deep rula cu cap=150 + fără OCR + doar avere. Aici re-crawl-uim
uncapped (max_pdfs=5000, depth 3) toate secțiunile de declarații din sectiuni.json + agentii_
sectiuni.json și salvăm lista de PDF-uri → _ministere_pdfs.json, care apoi e dat lui
harvest_reprocess (ROMEGA_SRC=ministere) pentru avere&interese + OCR pe scanate.
"""

from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from connectors.institutie.generic import crawl_declaration_pdfs  # noqa: E402
from romega_core.bronze import BronzeStore  # noqa: E402
from romega_core.http import Client  # noqa: E402

V = os.path.join(ROOT, "data/v1")
OUT = os.path.join(V, "declaratii/_ministere_pdfs.json")


def _institutions() -> list[dict]:
    out = []
    for fn, key in (("institutii/sectiuni.json", "ministere"),
                    ("institutii/agentii_sectiuni.json", "agentii")):
        try:
            doc = json.load(open(os.path.join(V, fn), encoding="utf-8"))
        except Exception:
            continue
        for m in doc.get(key, []):
            decl = (m.get("sections") or {}).get("declaratii")
            if decl:
                out.append({"id": m["id"], "name": m["name"],
                            "host": (m.get("domain") or "").split("/")[0], "start": decl})
    return out


def main() -> dict:
    bronze = BronzeStore(os.path.join(ROOT, "data", "raw"))
    client = Client(bronze=bronze, throttle_seconds=0.4, timeout=20)
    insts = _institutions()
    print(f"Ministere+agenții cu secțiune declarații: {len(insts)}", flush=True)
    pdf_to_who: dict[str, str] = {}
    for it in insts:
        try:
            urls = crawl_declaration_pdfs(client, it["start"], "mina_" + it["id"],
                                          it["host"], max_depth=3, max_pdfs=5000)
        except Exception as e:
            print(f"   ! crawl eșuat {it['name']}: {type(e).__name__}", flush=True)
            urls = []
        for u in urls:
            pdf_to_who.setdefault(u, it["name"])
        if urls:
            print(f"   {it['name'][:40]:40} {len(urls)} PDF", flush=True)
    json.dump(pdf_to_who, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"TOTAL PDF ministere+agenții: {len(pdf_to_who)} -> {OUT}", flush=True)
    return {"pdfs": len(pdf_to_who)}


if __name__ == "__main__":
    main()
