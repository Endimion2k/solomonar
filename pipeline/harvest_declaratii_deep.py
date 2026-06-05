"""Harvest declarații DEEP — ministere + agenții, crawl BFS 3 niveluri, cap mărit.

Combină ambele surse de secțiuni (sectiuni.json + agentii_sectiuni.json), crawl depth=3,
max 150 PDF/instituție. Cache bronze face re-crawl-ul rapid (descarcă doar paginile/PDF-urile noi).
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
from romega_core.bronze import BronzeStore  # noqa: E402
from romega_core.http import Client  # noqa: E402

V = os.path.join(ROOT, "data/v1")


def _institutions() -> list[dict]:
    out = []
    mins = json.load(open(os.path.join(V, "institutii/sectiuni.json"), encoding="utf-8"))["ministere"]
    ags = json.load(open(os.path.join(V, "institutii/agentii_sectiuni.json"), encoding="utf-8"))["agentii"]
    for m in mins + ags:
        if m.get("sections", {}).get("declaratii"):
            out.append({"id": m["id"], "name": m["name"], "domain": m["domain"],
                        "decl": m["sections"]["declaratii"]})
    return out


def main(max_depth: int = 3, max_pdfs: int = 5000) -> dict:
    # fără cap practic (backstop 5000); luăm toate declarațiile, nu doar primele 150
    bronze = BronzeStore(os.path.join(ROOT, "data", "raw"))
    client = Client(bronze=bronze, throttle_seconds=0.5, timeout=22)
    insts = _institutions()
    print(f"Institutii cu pagina de declaratii: {len(insts)}", flush=True)

    pdf_to_inst = {}
    for it in insts:
        try:
            urls = crawl_declaration_pdfs(client, it["decl"], "decl_" + it["id"],
                                          it["domain"].split("/")[0], max_depth=max_depth, max_pdfs=max_pdfs)
        except Exception:
            urls = []
        for u in urls:
            pdf_to_inst.setdefault(u, it["name"])
    print(f"PDF-uri declaratii (deep): {len(pdf_to_inst)}", flush=True)

    pdfs = client.fetch_many([(u, "decl_pdf", ".pdf") for u in pdf_to_inst], workers=12)
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
        if not av.text_extracted or (av.terenuri_count + av.cladiri_count + av.conturi_total_ron + av.venituri_anuale_ron) == 0:
            continue
        decls.append({"institutie": pdf_to_inst.get(u, ""), "pdf_url": u,
                      "terenuri": av.terenuri_count, "cladiri": av.cladiri_count,
                      "conturi_ron": round(av.conturi_total_ron), "venituri_ron": round(av.venituri_anuale_ron),
                      "datorii_ron": round(av.datorii_total_ron), "auto": av.auto_count})

    json.dump({"generated_at": datetime.now(timezone.utc).isoformat(),
               "sursa": "ministere + agentii (Legea 176/2010), crawl depth 3, fara CAPTCHA",
               "total": len(decls), "pdf_descarcate": len([v for v in pdfs.values() if v]),
               "pii_blocate": pii_blocked, "declaratii": decls},
              open(os.path.join(V, "declaratii/avere_toate.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"PUBLICAT avere_toate.json: {len(decls)} declaratii | {parsed} parsate | {pii_blocked} PII | cache={bronze.count()}", flush=True)
    return {"declaratii": len(decls)}


if __name__ == "__main__":
    main()
