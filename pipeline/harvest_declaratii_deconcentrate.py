"""Harvest declarații de avere de pe serviciile DECONCENTRATE nou-găsite (Tier 3).

Payoff-ul lui harvest_deconcentrate.py: ia cele 87 site-uri reale (DSP/ITM/ISJ/DGASPC/OCPI...),
intră pe secțiunea „declarații" (sau „integritate", unde sunt de obicei publicate), face crawl
BFS pentru PDF-uri, descarcă paralel + cache, parsează averea, REDACTEAZĂ PII (Legea 176/2010),
și publică declaratii/avere_deconcentrate.json. Fără CAPTCHA — surse publice per-instituție.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from connectors.ani.declaratii import extract_pdf_text, parse_avere_text  # noqa: E402
from connectors.ani.redaction import find_pii  # noqa: E402
from connectors.institutie.generic import crawl_declaration_pdfs  # noqa: E402
from romega_core.bronze import BronzeStore  # noqa: E402
from romega_core.http import Client  # noqa: E402
from romega_core.names import strip_diacritics  # noqa: E402

V = os.path.join(ROOT, "data/v1")


def _institutions() -> list[dict]:
    """Serviciile reale cu o secțiune unde pot fi declarații (declaratii > integritate)."""
    src = json.load(open(os.path.join(V, "institutii/deconcentrate_real.json"), encoding="utf-8"))
    out = []
    for i in src["institutii"]:
        secs = i.get("sections") or {}
        start = secs.get("declaratii") or secs.get("integritate")
        if not start:
            continue
        sid = strip_diacritics(f"{i['service']}_{i['county']}").lower().replace(" ", "")
        out.append({"id": sid, "name": f"{i['service']} {i['county']}",
                    "host": urlparse(i["url"]).netloc, "start": start})
    return out


def main(max_depth: int = 3, max_pdfs: int = 5000) -> dict:
    # FĂRĂ cap practic: max_pdfs=5000 e doar backstop anti-runaway; luăm toate declarațiile
    # găsite. max_depth=3 prinde paginarea/arhivele (an → listă persoane → PDF).
    bronze = BronzeStore(os.path.join(ROOT, "data", "raw"))
    client = Client(bronze=bronze, throttle_seconds=0.4, timeout=20)
    insts = _institutions()
    print(f"Servicii deconcentrate cu secțiune declarații/integritate: {len(insts)}", flush=True)

    pdf_to_inst = {}
    for it in insts:
        try:
            urls = crawl_declaration_pdfs(client, it["start"], "decd_" + it["id"],
                                          it["host"], max_depth=max_depth, max_pdfs=max_pdfs)
        except Exception as e:
            print(f"   ! crawl esuat {it['name']}: {type(e).__name__}", flush=True)
            urls = []
        for u in urls:
            pdf_to_inst.setdefault(u, it["name"])
        if urls:
            flag = "  <-- ATINS BACKSTOP, posibil trunchiat" if len(urls) >= max_pdfs else ""
            print(f"   {it['name']:18} {len(urls)} PDF{flag}", flush=True)
    print(f"PDF-uri declaratii (deconcentrate): {len(pdf_to_inst)}", flush=True)

    pdfs = client.fetch_many([(u, "decd_pdf", ".pdf") for u in pdf_to_inst], workers=12)
    decls, pii_blocked, parsed = [], 0, 0
    for u, content in pdfs.items():
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
        av = parse_avere_text(txt)
        signal = av.terenuri_count + av.cladiri_count + av.conturi_total_ron + av.venituri_anuale_ron
        if not av.text_extracted or signal == 0:
            continue
        decls.append({"institutie": pdf_to_inst.get(u, ""), "pdf_url": u,
                      "terenuri": av.terenuri_count, "cladiri": av.cladiri_count,
                      "conturi_ron": round(av.conturi_total_ron), "venituri_ron": round(av.venituri_anuale_ron),
                      "datorii_ron": round(av.datorii_total_ron), "auto": av.auto_count})

    out = os.path.join(V, "declaratii/avere_deconcentrate.json")
    json.dump({"generated_at": datetime.now(timezone.utc).isoformat(),
               "sursa": "servicii deconcentrate (DSP/ITM/ISJ/DGASPC/OCPI), Legea 176/2010, fara CAPTCHA",
               "total": len(decls), "pdf_descarcate": len([v for v in pdfs.values() if v]),
               "pii_blocate": pii_blocked, "declaratii": decls},
              open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"PUBLICAT avere_deconcentrate.json: {len(decls)} declaratii | {parsed} parsate | "
          f"{pii_blocked} PII blocate | cache={bronze.count()}", flush=True)
    return {"declaratii": len(decls), "parsed": parsed, "pii_blocked": pii_blocked}


if __name__ == "__main__":
    main()
