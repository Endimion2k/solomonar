"""Construiește layout-ul grafului SOLOMONAR (persoane ↔ companii) pentru vizualizare web.

Sursă: data/v1/graf/persoane_gold.json (persoane cu lista `companii`, fiecare
companie cu `contracte_stat` și flagul `parlamentar`). NU folosim toate cele 56k
persoane — doar componenta "follow the money": persoane cu legături unde există
contracte cu statul sau conflict de interese (parlamentar care conduce companii).

Strategie de bounding (max ~MAX_NODES noduri):
  1. Seed = parlamentari care conduc companii  +  persoanele cu cea mai mare
     valoare de contracte cu statul (top după total_contracte_ron).
  2. Adaugă companiile lor.
  3. Adaugă co-administratorii acelor companii (vecinii la distanță 1) — aici apar
     clusterele reale (mai mulți oameni pe aceeași firmă cu contracte).
  4. Taie la MAX_NODES păstrând nodurile cu cel mai mare grad / valoare.

Layout: networkx.spring_layout (Fruchterman-Reingold). Dacă pachetul `fa2`
(ForceAtlas2) e disponibil, îl folosim — altfel cădem pe spring_layout.
Mărimea nodului = grad. Clusterul = id-ul componentei conexe.

Output: data/v1/graf/graph_layout.json
  {nodes:[{id,label,type,x,y,size,cluster, ...}], edges:[{source,target,type}]}
"""

from __future__ import annotations

import json
import os

import networkx as nx

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data/v1/graf/persoane_gold.json")
OUT = os.path.join(ROOT, "data/v1/graf/graph_layout.json")

MAX_NODES = 3000          # plafon dur pe numărul total de noduri
SEED_PARLAMENTARI = True  # include toți parlamentarii cu companii
TOP_CONTRACTE = 600       # câte persoane (după valoarea contractelor) intră ca seed
TOP_COMPANII_HUB = 400    # câte companii-hub (mulți co-administratori) intră ca seed


def _try_forceatlas2(G):
    """Întoarce poziții ForceAtlas2 dacă pachetul `fa2` e instalat, altfel None."""
    try:
        from fa2 import ForceAtlas2
    except Exception:
        return None
    fa2 = ForceAtlas2(gravity=1.0, scalingRatio=2.0, verbose=False)
    return fa2.forceatlas2_networkx_layout(G, pos=None, iterations=300)


def main() -> dict:
    with open(SRC, encoding="utf-8") as f:
        data = json.load(f)
    persoane = data["persoane"]

    # Indexăm persoanele relevante (au cel puțin o companie).
    rel = [p for p in persoane if p.get("companii")]

    pidx = {p["romega_id"]: p for p in rel}

    # Index companie → administratori + metadate (necesar înainte de seeding).
    comp_persons: dict[int, set[str]] = {}
    comp_meta: dict[int, dict] = {}
    for p in rel:
        for c in p.get("companii", []):
            cui = c.get("cui")
            if cui is None:
                continue
            comp_persons.setdefault(cui, set()).add(p["romega_id"])
            if cui not in comp_meta:
                comp_meta[cui] = {
                    "nume": c.get("nume", ""),
                    "sector": c.get("sector", ""),
                    "contracte": (c.get("contracte_stat") or {}).get("total_ron", 0) or 0,
                }

    # --- 1. seed-uri ---
    # (a) parlamentari cu companii (conflict de interese)
    # (b) top persoane după valoarea contractelor cu statul
    # (c) companiile cu cei mai mulți co-administratori ȘI/SAU contracte de stat
    #     — acestea aduc clusterele dense (mai mulți oameni pe aceeași firmă).
    seeds: set[str] = set()
    seed_companies: set[int] = set()
    if SEED_PARLAMENTARI:
        for p in rel:
            if p.get("parlamentar"):
                seeds.add(p["romega_id"])
    by_contracte = sorted(
        rel, key=lambda p: p.get("total_contracte_ron") or 0, reverse=True
    )
    for p in by_contracte[:TOP_CONTRACTE]:
        if (p.get("total_contracte_ron") or 0) > 0:
            seeds.add(p["romega_id"])
    # companii-hub: scor = nr co-administratori, ponderat dacă au contracte de stat
    comp_score = sorted(
        comp_persons,
        key=lambda cui: (
            len(comp_persons[cui]) * (2 if (comp_meta[cui]["contracte"] or 0) > 0 else 1)
        ),
        reverse=True,
    )
    for cui in comp_score[:TOP_COMPANII_HUB]:
        if len(comp_persons[cui]) >= 2:
            seed_companies.add(cui)

    seeds = {s for s in seeds if s in pidx}

    # --- 2+3. extindem cu companiile seed-urilor și co-administratorii lor ---
    keep_persons: set[str] = set(seeds)
    keep_companies: set[int] = set(seed_companies)
    # companiile-hub aduc direct toți co-administratorii
    for cui in seed_companies:
        keep_persons |= comp_persons.get(cui, set())
    # hop 1: companiile persoanelor-seed + co-administratorii lor
    for rid in seeds:
        for c in pidx[rid].get("companii", []):
            cui = c.get("cui")
            if cui is None:
                continue
            keep_companies.add(cui)
            keep_persons |= comp_persons.get(cui, set())
    # hop 2: companiile co-administratorilor (leagă clusterele între ele —
    # aceiași oameni care administrează mai multe firme cu contracte).
    hop1_persons = set(keep_persons)
    for rid in hop1_persons:
        p = pidx.get(rid)
        if not p:
            continue
        for c in p.get("companii", []):
            cui = c.get("cui")
            if cui is None:
                continue
            # adăugăm doar companii care leagă (≥2 persoane deja în set) sau
            # care au contracte de stat — ca să nu umflăm cu firme-satelit izolate.
            others = comp_persons.get(cui, set())
            has_contract = (comp_meta.get(cui, {}).get("contracte", 0) or 0) > 0
            if len(others & keep_persons) >= 2 or has_contract:
                keep_companies.add(cui)
                keep_persons |= others

    # --- 4. construim graful bipartit persoană↔companie pe nodurile păstrate ---
    G = nx.Graph()
    for rid in keep_persons:
        p = pidx[rid]
        parl = p.get("parlamentar")
        ntype = "parlamentar" if parl else "persoana"
        G.add_node(
            rid, ntype=ntype,
            label=(p.get("nume_key") or rid).title(),
            contracte=p.get("total_contracte_ron") or 0,
            incredere=p.get("incredere", ""),
            partid=(parl or {}).get("partid", "") if parl else "",
        )
    for cui in keep_companies:
        m = comp_meta.get(cui, {})
        G.add_node(
            f"c:{cui}", ntype="companie",
            label=m.get("nume", str(cui)),
            sector=m.get("sector", ""),
            contracte=m.get("contracte", 0),
        )
    for rid in keep_persons:
        for c in pidx[rid].get("companii", []):
            cui = c.get("cui")
            if cui is not None and cui in keep_companies:
                G.add_edge(rid, f"c:{cui}", type="conduce")

    # scoatem nodurile izolate (fără nicio muchie în subgraf)
    G.remove_nodes_from([n for n in list(G.nodes) if G.degree(n) == 0])

    # --- bounding la MAX_NODES: păstrăm componentele conexe cele mai mari ---
    # (preferăm clustere dense în loc de noduri izolate cu grad mare).
    if G.number_of_nodes() > MAX_NODES:
        comps = sorted(nx.connected_components(G), key=len, reverse=True)
        keep: set = set()
        for comp in comps:
            if len(keep) + len(comp) > MAX_NODES:
                # dacă următoarea componentă nu mai încape întreagă, ne oprim
                # (evităm să spargem un cluster în două).
                if not keep:  # prima componentă deja > MAX_NODES: o trunchiem pe grad
                    sub = sorted(comp, key=lambda n: G.degree(n), reverse=True)
                    keep |= set(sub[:MAX_NODES])
                break
            keep |= set(comp)
        G = G.subgraph(keep).copy()
        G.remove_nodes_from([n for n in list(G.nodes) if G.degree(n) == 0])

    # clustere = componente conexe (id stabil, ordonate descrescător după mărime)
    comps = sorted(nx.connected_components(G), key=len, reverse=True)
    cluster_of = {}
    for i, comp in enumerate(comps):
        for n in comp:
            cluster_of[n] = i

    # --- layout ---
    pos = _try_forceatlas2(G)
    layout_algo = "forceatlas2"
    if pos is None:
        # spring_layout pe graf mare: k mic, puține iterații, seed fix → reproducibil
        k = 1.0 / (G.number_of_nodes() ** 0.5) if G.number_of_nodes() else None
        pos = nx.spring_layout(G, k=k, iterations=60, seed=42)
        layout_algo = "spring"

    # normalizăm pozițiile la [0, 1000] ca să fie ușor de randat în sigma.js
    xs = [p[0] for p in pos.values()]
    ys = [p[1] for p in pos.values()]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    spanx = (maxx - minx) or 1.0
    spany = (maxy - miny) or 1.0

    nodes = []
    for n in G.nodes:
        d = G.nodes[n]
        x = (pos[n][0] - minx) / spanx * 1000.0
        y = (pos[n][1] - miny) / spany * 1000.0
        size = 2.0 + (G.degree(n) ** 0.6) * 1.6  # grad → rază, comprimat cu putere
        nodes.append({
            "id": n,
            "label": d.get("label", n),
            "type": d.get("ntype", "persoana"),
            "x": round(x, 2),
            "y": round(y, 2),
            "size": round(size, 2),
            "degree": G.degree(n),
            "cluster": cluster_of[n],
            "contracte": round(float(d.get("contracte", 0) or 0)),
            "sector": d.get("sector", ""),
            "partid": d.get("partid", ""),
        })

    edges = [{"source": u, "target": v, "type": "conduce"} for u, v in G.edges]

    out = {
        "nota": ("Subgraf 'follow the money': parlamentari + persoane cu contracte de "
                 "stat și co-administratorii companiilor lor. Bounded la "
                 f"{MAX_NODES} noduri. NU conține toate cele 56k persoane."),
        "layout": layout_algo,
        "max_nodes": MAX_NODES,
        "n_nodes": len(nodes),
        "n_edges": len(edges),
        "n_clusters": len(comps),
        "tipuri": {
            "persoana": sum(1 for n in nodes if n["type"] == "persoana"),
            "parlamentar": sum(1 for n in nodes if n["type"] == "parlamentar"),
            "companie": sum(1 for n in nodes if n["type"] == "companie"),
        },
        "nodes": nodes,
        "edges": edges,
    }

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))

    print(f"PUBLICAT graph_layout ({layout_algo}): {len(nodes)} noduri, "
          f"{len(edges)} muchii, {len(comps)} clustere → {os.path.relpath(OUT, ROOT)}")
    print(f"  tipuri: {out['tipuri']}")
    return {"nodes": len(nodes), "edges": len(edges), "clusters": len(comps)}


if __name__ == "__main__":
    main()
