"""Harvest agenții centrale (Tier 2) — secțiuni (conducere/declarații) + declarații la scară.

Reutilizează exact fluxul de la ministere: fetch_many homepages (paralel) → find_institution_sections
→ crawl_declaration_pdfs (BFS 2 niveluri, paralel+cache) → parse avere → guard PII → publică.
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
from connectors.institutie.generic import (  # noqa: E402
    crawl_declaration_pdfs,
    find_institution_sections,
)
from pipeline.config import iter_sources, load_sources  # noqa: E402
from romega_core.bronze import BronzeStore  # noqa: E402
from romega_core.http import Client  # noqa: E402


def main() -> dict:
    bronze = BronzeStore(os.path.join(ROOT, "data", "raw"))
    client = Client(bronze=bronze, throttle_seconds=0.6, timeout=22)

    agencies = []
    for s in iter_sources(load_sources()):
        if s.get("category") != "agency" or s.get("id") == "anaf_api":
            continue
        dom = s.get("domain") or (s.get("base_url", "").split("//")[-1].split("/")[0])
        if dom:
            agencies.append({"id": s["id"], "name": s.get("name", s["id"]), "domain": dom})
    print(f"Agentii de scrapuit: {len(agencies)}", flush=True)

    # 1) homepages in paralel -> sectiuni
    homepages = {a["id"]: f"https://{a['domain'].split('/')[0]}" for a in agencies}
    fetched = client.fetch_many([(u, "ag_" + i, ".html") for i, u in homepages.items()], workers=8)
    sections = {}
    for a in agencies:
        content = fetched.get(homepages[a["id"]])
        a["status"] = "ok" if content else "err"
        a["sections"] = find_institution_sections(content, homepages[a["id"]]) if content else {}

    # 2) crawl declaratii pt. cele cu pagina de declaratii
    pdf_to_inst = {}
    for a in agencies:
        durl = a["sections"].get("declaratii")
        if not durl:
            continue
        try:
            urls = crawl_declaration_pdfs(client, durl, "ag_decl_" + a["id"],
                                          a["domain"].split("/")[0], max_depth=2, max_pdfs=50)
        except Exception:
            urls = []
        for u in urls:
            pdf_to_inst.setdefault(u, a["name"])
    print(f"PDF-uri declaratii (agentii): {len(pdf_to_inst)}", flush=True)

    # 3) download paralel + parse
    pdfs = client.fetch_many([(u, "ag_pdf", ".pdf") for u in pdf_to_inst], workers=10)
    decls = []
    pii_blocked = 0
    for u, content in pdfs.items():
        if not content:
            continue
        try:
            txt = extract_pdf_text(content)
        except Exception:
            continue
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

    out = os.path.join(ROOT, "data/v1")
    os.makedirs(os.path.join(out, "institutii"), exist_ok=True)
    os.makedirs(os.path.join(out, "declaratii"), exist_ok=True)
    json.dump({"generated_at": datetime.now(timezone.utc).isoformat(),
               "agentii": [{k: a[k] for k in ("id", "name", "domain", "status", "sections")} for a in agencies]},
              open(os.path.join(out, "institutii/agentii_sectiuni.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    json.dump({"generated_at": datetime.now(timezone.utc).isoformat(), "sursa": "site-uri agentii (Legea 176/2010)",
               "total": len(decls), "pii_blocate": pii_blocked, "declaratii": decls},
              open(os.path.join(out, "declaratii/avere_agentii.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    ok = sum(1 for a in agencies if a["status"] == "ok")
    cond = sum(1 for a in agencies if a["sections"].get("conducere"))
    decl = sum(1 for a in agencies if a["sections"].get("declaratii"))
    print(f"PUBLICAT: {ok}/{len(agencies)} accesate | {cond} conducere | {decl} pagina declaratii | "
          f"{len(decls)} declaratii reale | {pii_blocked} PII blocate | cache={bronze.count()}", flush=True)
    return {"agentii": len(agencies), "ok": ok, "declaratii": len(decls)}


if __name__ == "__main__":
    main()
