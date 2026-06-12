"""Graf COMPLET pt. cosmos.gl — toate nodurile persoană↔companie (layout GPU-live în browser).

cosmos.gl rulează force-layout pe GPU → nu precalculăm poziții (spre deosebire de build_graph_layout
care e bounded la 3000 + spring_layout pe CPU). Exportăm tot graful bipartit follow-the-money:
persoane (cu ≥1 companie) + companii (cu ≥1 administrator) + edge-urile. Atribute pt. culoare/mărime.
Output data/v1/graf/graph_full.json {nodes:[{id,label,type,deg,...}], links:[{source,target}]}.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V = os.path.join(ROOT, "data/v1")


def _load(p):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return {}


def main() -> dict:
    g = _load(os.path.join(V, "graf/persoane_gold.json")).get("persoane", [])
    cidx = {c["cui"]: c for c in _load(os.path.join(V, "companii/_index.json")).get("data", [])}

    nodes = {}   # id -> node
    links = []
    deg = defaultdict(int)

    for p in g:
        comps = p.get("companii", [])
        if not comps:
            continue   # doar persoanele conectate la companii (graful follow-the-money)
        pid = "p:" + (p.get("romega_id") or p.get("nume_key", ""))
        pl = p.get("parlamentar")
        conflict = bool(p.get("firme_contracte_autodeclarate"))
        nodes.setdefault(pid, {
            "id": pid, "label": (p.get("nume") or p.get("nume_key", "")).title()[:40],
            "type": "parlamentar" if pl else ("conflict" if conflict else "persoana"),
            "inc": p.get("incredere", ""),
            "partid": (pl.get("partid") if pl else None),
            "contracte": int(p.get("total_contracte_ron") or 0),
            "directe": int(p.get("total_achizitii_directe_ron") or 0),
        })
        for c in comps:
            cui = c.get("cui")
            if cui is None:
                continue
            cid = "c:" + str(cui)
            if cid not in nodes:
                co = cidx.get(cui, {})
                nodes[cid] = {"id": cid, "label": (c.get("nume") or co.get("name", "") or str(cui))[:40],
                              "type": "companie", "sector": co.get("sector", ""),
                              "is_soe": bool(co.get("is_soe")),
                              "contracte": int((c.get("contracte_stat") or {}).get("total_ron") or 0),
                              "directe": int((c.get("achizitii_directe") or {}).get("total_ron") or 0)}
            links.append({"source": pid, "target": cid})
            deg[pid] += 1
            deg[cid] += 1

    for nid, n in nodes.items():
        n["deg"] = deg[nid]

    out = {"nota": "Graf complet follow-the-money (persoană↔companie). Layout pe GPU (cosmos.gl). "
           "Culoare pe tip; mărime pe grad. Edge = persoana administrează compania.",
           "n_nodes": len(nodes), "n_links": len(links),
           "nodes": list(nodes.values()), "links": links}
    json.dump(out, open(os.path.join(V, "graf/graph_full.json"), "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))
    sz = os.path.getsize(os.path.join(V, "graf/graph_full.json")) // 1024
    import collections
    tp = collections.Counter(n["type"] for n in nodes.values())
    print(f"PUBLICAT graph_full.json: {len(nodes)} noduri, {len(links)} edges, {sz}KB | tipuri: {dict(tp)}", flush=True)
    return {"nodes": len(nodes), "links": len(links)}


if __name__ == "__main__":
    main()
