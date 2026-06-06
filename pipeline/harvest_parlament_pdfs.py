"""Construiește lista de PDF-uri de declarații pentru PARLAMENT (deputați + senatori).

cdep.ro expune declarațiile CAPTCHA-free pe profilul fiecărui deputat: tab avere (pag=5) și
interese (pag=6) conțin linkuri .pdf (toți anii). Le strângem într-un checkpoint care apoi e dat
lui harvest_reprocess (ROMEGA_SRC=parlament) pentru extragere avere&interese (text + OCR).

Senatori: senat.ro are structură proprie — adăugat dacă profilul expune linkuri de declarații.
"""

from __future__ import annotations

import json
import os
import sys
from urllib.parse import urljoin

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from romega_core.http import Client  # noqa: E402
from romega_core.parse import selector  # noqa: E402

V = os.path.join(ROOT, "data/v1")
OUT = os.path.join(V, "declaratii/_parlament_pdfs.json")


def _pdf_links(client: Client, url: str) -> list[str]:
    try:
        content, _ = client.fetch(url, "parl_prof", ".html", use_cache=True)
        text = content.decode("utf-8", "ignore") if isinstance(content, bytes) else content
        out = []
        for h in selector(text).css("a::attr(href)").getall():
            full = urljoin(url, h)
            if full.lower().endswith(".pdf") and "declaratii" in full.lower():
                out.append(full)
        return out
    except Exception:
        return []


def main() -> dict:
    client = Client(throttle_seconds=0.3, timeout=20)
    pdf_to_who: dict[str, str] = {}

    deps = json.load(open(os.path.join(V, "parlament/deputati.json"), encoding="utf-8"))["data"]
    print(f"Deputați: {len(deps)}", flush=True)
    for i, d in enumerate(deps, 1):
        prof = d.get("profile_url")
        if not prof:
            continue
        who = f"Deputat {d.get('name', '')}"
        for pag in ("5", "6"):  # 5=avere, 6=interese
            sep = "&" if "?" in prof else "?"
            for u in _pdf_links(client, f"{prof}{sep}pag={pag}"):
                pdf_to_who.setdefault(u, who)
        if i % 50 == 0:
            print(f"   {i}/{len(deps)} deputați | PDF strânse: {len(pdf_to_who)}", flush=True)

    print(f"TOTAL PDF parlament: {len(pdf_to_who)}", flush=True)
    json.dump(pdf_to_who, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"Checkpoint salvat: {OUT}", flush=True)
    return {"pdfs": len(pdf_to_who)}


if __name__ == "__main__":
    main()
