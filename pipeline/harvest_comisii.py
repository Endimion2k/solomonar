"""Harvest activitatea comisiilor Camerei Deputaților (2024→prezent) → index SOLOMONAR.

Produce INDEXUL (nu descarcă încă documentele-PDF în masă):
- comisii.json   : [{tip, nume}]
- sedinte.json   : [{tip, comisie, an, data, agenda_pdf_url, plx_idps:[...]}]
- plx.json       : [{idp, numar, an, titlu, camera, documente:[{tip,url}]}]  (dedup pe idp)

Crawl: pt. fiecare comisie×an → ședințe → descarcă ordinea de zi (PDF) → extrage linkuri PLx
(anotări) → pt. fiecare PLx unic → pagina proiectului → documente. cdep.ro (throttle per-host).
Checkpoint-uri pt. resume. Descărcarea în masă a documentelor = pas separat (harvest_comisii_docs).
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from connectors.parlament.comisii import (  # noqa: E402
    COMISII_URL, CO_BASE, agenda_plx_links, parse_committee_name,
    parse_committee_tips, parse_plx_page, parse_session_agendas,
)
from solomonar_core.bronze import BronzeStore  # noqa: E402
from solomonar_core.http import Client  # noqa: E402

V = os.path.join(ROOT, "data/v1/comisii")
YEARS = [int(y) for y in os.environ.get("SOLOMONAR_COMISII_ANI", "2024,2025,2026").split(",")]


def _idp(url: str) -> str | None:
    import re
    m = re.search(r"idp=(\d+)", url)
    return m.group(1) if m else None


def main() -> dict:
    os.makedirs(V, exist_ok=True)
    bronze = BronzeStore(os.path.join(ROOT, "data", "raw"))
    client = Client(bronze=bronze, throttle_seconds=0.35, timeout=25)

    # 1. comisii (tip-uri)
    html, _ = client.fetch(COMISII_URL, "co_list", ".html")
    tips = parse_committee_tips(html)
    print(f"[1] comisii: {len(tips)} tip-uri", flush=True)

    # 2. ședințe per comisie×an + nume comisie
    comisii: dict[int, str] = {}
    sedinte: list[dict] = []
    for tip in tips:
        name = ""
        for an in YEARS:
            url = f"{CO_BASE}sedinte2015.lista?tip={tip}&an={an}"
            try:
                h, _ = client.fetch(url, "co_sess", ".html")
            except Exception:
                continue
            if not name:
                name = parse_committee_name(h)
            for ag in parse_session_agendas(h):
                sedinte.append({"tip": tip, "an": an, "data": ag["date"],
                                "agenda_pdf_url": ag["agenda_pdf_url"], "plx_idps": []})
        comisii[tip] = name
        print(f"   tip={tip} {name[:40]:40} ședințe cumulate={len(sedinte)}", flush=True)

    # 3. descarcă ordinile de zi (PDF) → extrage linkuri PLx (idp)
    agendas = sorted({s["agenda_pdf_url"] for s in sedinte})
    print(f"[3] ordini de zi de procesat: {len(agendas)}", flush=True)
    agenda_to_idps: dict[str, list[str]] = {}
    for i in range(0, len(agendas), 100):
        chunk = agendas[i:i + 100]
        fetched = client.fetch_many([(u, "co_oz", ".pdf") for u in chunk], workers=6)
        for u, content in fetched.items():
            if not content:
                continue
            try:
                idps = [x for x in (_idp(l) for l in agenda_plx_links(content)) if x]
            except Exception:
                idps = []
            agenda_to_idps[u] = sorted(set(idps))
        print(f"   ordini procesate: {min(i + 100, len(agendas))}/{len(agendas)}", flush=True)
    for s in sedinte:
        s["plx_idps"] = agenda_to_idps.get(s["agenda_pdf_url"], [])

    # 4. pagini PLx unice → titlu + documente
    all_idps = sorted({x for s in sedinte for x in s["plx_idps"]}, key=int)
    print(f"[4] PLx unice: {len(all_idps)}", flush=True)
    plx_rows: list[dict] = []
    for i in range(0, len(all_idps), 100):
        chunk = all_idps[i:i + 100]
        items = [(f"https://www.cdep.ro/ords/pls/proiecte/upl_pck2015.proiect?cam=2&idp={d}",
                  "co_plx", ".html") for d in chunk]
        fetched = client.fetch_many(items, workers=6)
        for (url, _, _), d in zip(items, chunk):
            content = fetched.get(url)
            if not content:
                continue
            rec = parse_plx_page(content, url)
            rec["idp"] = d
            rec["camera"] = 2
            plx_rows.append(rec)
        print(f"   PLx procesate: {min(i + 100, len(all_idps))}/{len(all_idps)}", flush=True)

    # 5. publică indexul
    now = datetime.now(timezone.utc).isoformat()
    json.dump({"generated_at": now, "total": len(comisii),
               "comisii": [{"tip": t, "nume": n} for t, n in sorted(comisii.items())]},
              open(os.path.join(V, "comisii.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    json.dump({"generated_at": now, "ani": YEARS, "total": len(sedinte), "sedinte": sedinte},
              open(os.path.join(V, "sedinte.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    ndocs = sum(len(p["documente"]) for p in plx_rows)
    json.dump({"generated_at": now, "total": len(plx_rows), "total_documente": ndocs, "plx": plx_rows},
              open(os.path.join(V, "plx.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"PUBLICAT: comisii={len(comisii)} sedinte={len(sedinte)} PLx={len(plx_rows)} "
          f"documente={ndocs} | cache={bronze.count()}", flush=True)
    return {"comisii": len(comisii), "sedinte": len(sedinte), "plx": len(plx_rows), "documente": ndocs}


if __name__ == "__main__":
    main()
