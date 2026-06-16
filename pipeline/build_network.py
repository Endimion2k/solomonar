"""Analiză de rețea SOLOMONAR — inele de control, administratori-hub, firme-pod.

Construiește un graf companie↔companie din ADMINISTRATORII reali ONRC (reprezentanti.json):
două firme sunt legate dacă au același administrator (persoană fizică). Pe acest graf calculează,
cu igraph (rapid pe zeci de mii de noduri):
  - componente conexe = INELE DE CONTROL (clustere de firme cu administratori comuni)
  - administratori-HUB (cine controlează cele mai multe firme cu bani de stat)
  - articulation points = FIRME-POD (intermediari care leagă mai multe grupuri)

Filtrăm zgomotul: păstrăm doar calitatea „administrator" (nu lichidatori/judiciari/provizorii) și
excludem reprezentanții persoane-juridice (SPRL/IPURL/insolvență) și placeholderele.

Output: data/v1/graf/network_metrics.json (artefact static; clientul doar îl citește).
"""

from __future__ import annotations

import collections
import datetime
import json
import os
import re
import unicodedata

import igraph as ig

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V = os.path.join(ROOT, "data/v1")

RING_MAX_PER_ADMIN = 25       # peste atât = hub/coincidență de nume, nu folosim la muchii de inel
TOP_RINGS = 200
TOP_HUBS = 100
TOP_BRIDGES = 100
MAX_COMP_PER_RING = 40        # câte firme listăm per inel în JSON

# calități de control reale (NU judiciar / lichidator / provizoriu)
_BAD_CALITATE = ("judiciar", "lichidator", "provizoriu", "insolv", "supraveghere", "cenzor")
# nume care sunt de fapt persoane juridice (firme de insolvență) sau placeholder
_BAD_NAME = re.compile(r"\b(SPRL|IPURL|SCA|SRL|SA|S\.R\.L|S\.A|INSOLV|LICHIDARE|REORGANIZARE|"
                       r"FILIALA|IPRL|CAB\.?\s*AV|CABINET)\b", re.IGNORECASE)


def _load(p):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return {}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s.strip().upper())


def _is_real_admin(nume: str, calitate: str) -> bool:
    q = (calitate or "").lower()
    if "administrator" not in q:
        return False
    if any(b in q for b in _BAD_CALITATE):
        return False
    n = norm(nume)
    if not n or n == "FARA REPREZENTANT" or len(n) < 5:
        return False
    if any(ch.isdigit() for ch in n):
        return False
    if _BAD_NAME.search(n):
        return False
    return True


def main() -> dict:
    comp = _load(os.path.join(V, "companii/reprezentanti.json")).get("companii", [])

    # cui -> denumire ; cui -> bani de stat (contracte + achiziții directe)
    nume_by_cui: dict = {}
    for c in comp:
        try:
            cui = int(c.get("cui"))
        except (TypeError, ValueError):
            continue
        if c.get("denumire"):
            nume_by_cui[cui] = c["denumire"]

    bani_by_cui: dict = collections.defaultdict(float)
    for r in _load(os.path.join(V, "achizitii/contracte_firme.json")).get("firme", []):
        try:
            bani_by_cui[int(r["cui"])] += float(r.get("total_ron") or 0)
        except (TypeError, ValueError, KeyError):
            pass
    for r in _load(os.path.join(V, "companii/achizitii_directe.json")).get("furnizori", []):
        try:
            bani_by_cui[int(r["cui"])] += float(r.get("total_ron") or 0)
            nume_by_cui.setdefault(int(r["cui"]), r.get("nume"))
        except (TypeError, ValueError, KeyError):
            pass

    def has_bani(cui):
        return bani_by_cui.get(cui, 0) > 0

    # admin (normalizat) -> {cui...}
    admin_cuis: dict = collections.defaultdict(set)
    for c in comp:
        try:
            cui = int(c.get("cui"))
        except (TypeError, ValueError):
            continue
        for r in c.get("reprezentanti") or []:
            if _is_real_admin(r.get("nume"), r.get("calitate")):
                admin_cuis[norm(r.get("nume"))].add(cui)

    # muchii companie-companie din admini partajați (cap la RING_MAX_PER_ADMIN)
    edges: set = set()
    edge_admin: dict = collections.defaultdict(set)   # (a,b) -> {admini}
    cui_admins: dict = collections.defaultdict(set)    # cui -> {admini}
    for admin, cuis in admin_cuis.items():
        for cui in cuis:
            cui_admins[cui].add(admin)
        if 2 <= len(cuis) <= RING_MAX_PER_ADMIN:
            cl = sorted(cuis)
            for i in range(len(cl)):
                for j in range(i + 1, len(cl)):
                    e = (cl[i], cl[j])
                    edges.add(e)
                    edge_admin[e].add(admin)

    nodes = sorted({n for e in edges for n in e})
    idx = {c: i for i, c in enumerate(nodes)}
    g = ig.Graph()
    g.add_vertices(len(nodes))
    g.add_edges([(idx[a], idx[b]) for a, b in edges])

    # ---- componente conexe = inele de control ----
    comps = g.connected_components()
    rings = []
    for membership in comps:
        if len(membership) < 2:
            continue
        cuis = [nodes[i] for i in membership]
        admins = set()
        for cu in cuis:
            admins |= cui_admins.get(cu, set())
        firme = sorted(
            ({"cui": cu, "nume": nume_by_cui.get(cu, ""), "bani_stat": has_bani(cu),
              "total_ron": round(bani_by_cui.get(cu, 0)),
              "admini": sorted(cui_admins.get(cu, set()))[:6]} for cu in cuis),
            key=lambda x: -x["total_ron"])
        n_bani = sum(1 for f in firme if f["bani_stat"])
        total = sum(f["total_ron"] for f in firme)
        if n_bani < 1:
            continue
        rings.append({
            "n_companii": len(cuis),
            "n_companii_bani_stat": n_bani,
            "total_bani_stat_ron": round(total),
            "admini": sorted(admins)[:8],
            "n_admini": len(admins),
            "companii": firme[:MAX_COMP_PER_RING],
        })
    # inele „suspecte": ≥2 firme cu bani de stat. Sortăm după bani.
    rings.sort(key=lambda r: (r["n_companii_bani_stat"] >= 2, r["total_bani_stat_ron"]), reverse=True)
    n_rings_multi = sum(1 for r in rings if r["n_companii_bani_stat"] >= 2)

    # ---- administratori-hub: cei mai mulți cu firme cu bani de stat ----
    hubs = []
    for admin, cuis in admin_cuis.items():
        firme_bani = [cu for cu in cuis if has_bani(cu)]
        if len(firme_bani) < 2:
            continue
        total = sum(bani_by_cui.get(cu, 0) for cu in firme_bani)
        hubs.append({
            "admin": admin,
            "n_firme": len(cuis),
            "n_firme_bani_stat": len(firme_bani),
            "total_bani_stat_ron": round(total),
            "companii": [{"cui": cu, "nume": nume_by_cui.get(cu, ""),
                          "total_ron": round(bani_by_cui.get(cu, 0))}
                         for cu in sorted(firme_bani, key=lambda c: -bani_by_cui.get(c, 0))[:15]],
        })
    hubs.sort(key=lambda h: (h["n_firme_bani_stat"], h["total_bani_stat_ron"]), reverse=True)

    # ---- firme-pod: articulation points (leagă mai multe grupuri) ----
    bridges = []
    for vi in g.articulation_points():
        cu = nodes[vi]
        if not has_bani(cu) and len(cui_admins.get(cu, set())) < 2:
            continue
        bridges.append({
            "cui": cu, "nume": nume_by_cui.get(cu, ""),
            "n_admini": len(cui_admins.get(cu, set())),
            "grad": g.degree(vi),
            "total_bani_stat_ron": round(bani_by_cui.get(cu, 0)),
            "bani_stat": has_bani(cu),
        })
    bridges.sort(key=lambda b: (b["bani_stat"], b["grad"], b["total_bani_stat_ron"]), reverse=True)

    out = {
        "generat": datetime.date.today().isoformat(),
        "disclaimer": "Inelele sunt firme cu ADMINISTRATORI COMUNI (date reale ONRC). Un om care "
                      "controlează mai multe firme NU e ilegal — e un LEAD de verificat. Numele de "
                      "administrator se potrivesc pe text; pot exista omonimi.",
        "meta": {
            "companii_in_graf": len(nodes),
            "muchii": len(edges),
            "administratori_reali": len(admin_cuis),
            "inele_total": len(rings),
            "inele_cu_2plus_firme_bani_stat": n_rings_multi,
            "firme_cu_bani_stat": sum(1 for c in bani_by_cui if bani_by_cui[c] > 0),
        },
        "inele": rings[:TOP_RINGS],
        "huburi": hubs[:TOP_HUBS],
        "poduri": bridges[:TOP_BRIDGES],
    }

    outp = os.path.join(V, "graf/network_metrics.json")
    with open(outp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    return out


if __name__ == "__main__":
    res = main()
    m = res["meta"]
    print("OK -> data/v1/graf/network_metrics.json")
    print(f"  graf: {m['companii_in_graf']} companii, {m['muchii']} muchii, "
          f"{m['administratori_reali']} administratori reali")
    print(f"  inele: {m['inele_total']} (din care {m['inele_cu_2plus_firme_bani_stat']} cu ≥2 firme cu bani de stat)")
    print(f"  huburi: {len(res['huburi'])} | poduri: {len(res['poduri'])}")
    print("\n=== TOP 5 INELE (după bani de stat) ===")
    for i, r in enumerate(res["inele"][:5], 1):
        print(f"{i}. {r['n_companii']} firme ({r['n_companii_bani_stat']} cu bani), "
              f"{r['total_bani_stat_ron']:,} lei | admini: {', '.join(r['admini'][:3])}")
        for f in r["companii"][:4]:
            print(f"     - {f['nume'][:40]} (CUI {f['cui']}) {'💰' if f['bani_stat'] else ''}")
