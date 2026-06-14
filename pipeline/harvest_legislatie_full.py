"""Harvest legislație EXTINS (bounded) — paginare pe topici + ani, reutilizează helperii connectorului.

SOAP just.ro plafonează 10/pagină → paginăm NumarPagina pe topici cheie + ani recenți. Bounded la
~MAX acte (nu tot corpusul de 150k, care e text-bulk cu valoare mică de graf). Output extinde
data/v1/legislatie/index.json. Resume nu e necesar (rulare scurtă, dedup pe doc_id).
"""

from __future__ import annotations

import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from pipeline.harvest_legislatie import (  # noqa: E402
    NS, _post, build_search_envelope, get_token_envelope, parse_search_response, parse_token)

V = os.path.join(ROOT, "data/v1")
MAX_ACTE = int(os.environ.get("SOLOMONAR_LEG_MAX", "2500"))
PAGINI = int(os.environ.get("SOLOMONAR_LEG_PAGINI", "8"))

TOPICI = ["achizitii publice", "integritate", "transparenta", "protectia datelor", "cod fiscal",
          "conflict de interese", "avere", "anticoruptie", "societati comerciale", "buget de stat",
          "finantarea partidelor", "functii publice", "administratie publica", "energie", "mediu",
          "sanatate", "educatie", "munca", "pensii", "fonduri europene"]


def main() -> dict:
    tok = parse_token(_post(get_token_envelope(NS), "GetToken").text)
    if not tok:
        print("[legislatie] GetToken eșuat"); return {"acte": 0}
    print(f"[legislatie] token (len={len(tok)})", flush=True)

    # pornim de la ce avem deja
    existing = {}
    p = os.path.join(V, "legislatie/index.json")
    if os.path.exists(p):
        ex = json.load(open(p, encoding="utf-8"))
        for a in (ex.get("acte") or ex.get("data") or []):
            k = a.get("DocId") or a.get("doc_id") or (str(a.get("Numar"))+str(a.get("Titlu",""))[:20])
            if k: existing[str(k)] = a

    n0 = len(existing)
    for topic in TOPICI:
        if len(existing) >= MAX_ACTE:
            break
        for pag in range(1, PAGINI + 1):
            env = build_search_envelope(tok, titlu=topic, pagina=pag, rezultate=20)
            try:
                r = _post(env, "Search")
                if "Fault" in r.text[:2000]:
                    break
                acte = parse_search_response(r.text)
            except Exception:
                break
            if not acte:
                break
            for a in acte:
                k = a.get("DocId") or (str(a.get("Numar"))+str(a.get("Titlu",""))[:20])
                if k and k!="NoneNone": existing.setdefault(str(k), a)
            time.sleep(0.3)
        print(f"   '{topic[:24]}': total acum {len(existing)}", flush=True)
        if len(existing) >= MAX_ACTE:
            break

    data = list(existing.values())
    json.dump({"sursa": "legislatie.just.ro SOAP FreeWebService (extins, bounded)",
               "total": len(data), "nota": f"Eșantion-dovadă extins ({len(TOPICI)} topici × {PAGINI} pagini); "
               "corpus integral ~150k acte. doc_id → legislatie.just.ro/Public/DetaliiDocument/{id}",
               "acte": data},
              open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"PUBLICAT legislatie/index.json: {len(data)} acte ({len(data)-n0} noi)", flush=True)
    return {"acte": len(data)}


if __name__ == "__main__":
    main()
