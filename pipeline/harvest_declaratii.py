"""Harvest declarații de avere LA SCARĂ de pe site-urile ministerelor (FĂRĂ CAPTCHA).

Crawl BFS (2 niveluri) per minister → PDF-uri de declarații → download PARALEL + cache bronze
→ extract text (pdfplumber) → parse avere → guard PII → publică.

Ocolește complet portalul central ANI (Turnstile): Legea 176/2010 obligă fiecare instituție
să publice declarațiile pe site propriu. Rulează de pe mașina din RO.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from connectors.ani.declaratii import extract_pdf_text, parse_avere_text  # noqa: E402
from connectors.ani.redaction import find_pii  # noqa: E402
from connectors.institutie.generic import crawl_declaration_pdfs  # noqa: E402
from solomonar_core.bronze import BronzeStore  # noqa: E402
from solomonar_core.http import Client  # noqa: E402


def main(max_pdfs_per_min: int = 60) -> dict:
    bronze = BronzeStore(os.path.join(ROOT, "data", "raw"))
    client = Client(bronze=bronze, throttle_seconds=0.6, timeout=25)
    sect = json.load(open(os.path.join(ROOT, "data/v1/institutii/sectiuni.json"), encoding="utf-8"))["ministere"]

    # 1) crawl per minister -> URL-uri PDF (paralel + cache prin fetch_many)
    pdf_to_inst: dict[str, str] = {}
    for m in sect:
        durl = m["sections"].get("declaratii")
        if not durl:
            continue
        try:
            urls = crawl_declaration_pdfs(client, durl, "decl_" + m["id"], m["domain"],
                                          max_depth=2, max_pdfs=max_pdfs_per_min)
        except Exception:
            urls = []
        for u in urls:
            pdf_to_inst.setdefault(u, m["name"])
    print(f"PDF-uri de declaratii gasite (crawl): {len(pdf_to_inst)}", flush=True)

    # 2) download TOATE in paralel (cross-host) + cache
    fetched = client.fetch_many([(u, "decl_pdf", ".pdf") for u in pdf_to_inst], workers=10)

    # 3) extract + parse + guard PII
    decls = []
    parsed = pii_blocked = 0
    for u, content in fetched.items():
        if not content:
            continue
        try:
            txt = extract_pdf_text(content)
        except Exception:
            continue
        parsed += 1
        if find_pii(txt):
            pii_blocked += 1
            continue
        a = parse_avere_text(txt)
        if not a.text_extracted:
            continue
        if (a.terenuri_count + a.cladiri_count + a.conturi_total_ron + a.venituri_anuale_ron) == 0:
            continue
        decls.append({
            "institutie": pdf_to_inst.get(u, ""), "pdf_url": u,
            "terenuri": a.terenuri_count, "cladiri": a.cladiri_count,
            "conturi_ron": round(a.conturi_total_ron), "venituri_ron": round(a.venituri_anuale_ron),
            "datorii_ron": round(a.datorii_total_ron), "auto": a.auto_count,
        })

    out = os.path.join(ROOT, "data/v1/declaratii")
    os.makedirs(out, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sursa": "site-uri ministere (Legea 176/2010, fara CAPTCHA) — crawl 2 niveluri",
        "total": len(decls), "pdf_descarcate": len([v for v in fetched.values() if v]),
        "pii_blocate": pii_blocked, "declaratii": decls,
    }
    json.dump(payload, open(os.path.join(out, "avere_institutii.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"PUBLICAT: {len(decls)} declaratii cu date reale | {parsed} PDF-uri parsate | "
          f"{pii_blocked} blocate PII | cache bronze = {bronze.count()} URL-uri", flush=True)
    return payload


if __name__ == "__main__":
    main()
