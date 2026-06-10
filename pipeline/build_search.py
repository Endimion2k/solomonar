"""Construiește indexul de CĂUTARE compact pt. client (data/v1/search/index.json).

persoane_gold.json = 43MB (prea mare pt. client). Aici extragem un index compact + auto-suficient:
persoane (nume + fapte cheie: declarații/companii/contracte/partid), companii, partide. Clientul
îl încarcă o dată și caută local. Câmpuri scurte ca să rămână mic (gzip CDN ~1MB).
"""

from __future__ import annotations

import json
import os
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V = os.path.join(ROOT, "data/v1")


def _load(p):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return {}


def _ck(s):
    """Cheie de căutare normalizată (fără diacritice, lowercase) pt. filtrare rapidă în client."""
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()


def main() -> dict:
    items = []

    # 1. PERSOANE (din gold) — compact + fapte cheie
    g = _load(os.path.join(V, "graf/persoane_gold.json")).get("persoane", [])
    for p in g:
        nd, nc = p.get("n_declaratii", 0), p.get("n_companii", 0)
        pl = p.get("parlamentar")
        ct = p.get("total_contracte_ron") or 0
        # include doar persoane cu CEVA relevant (declarație/companie/mandat) — restul sunt mențiuni izolate
        if not (nd or nc or pl):
            continue
        nume = (p.get("nume") or p.get("nume_key", "")).title()
        rol = (pl["camera"] + " " + str(pl.get("partid"))) if pl else ""
        comp = sorted({c.get("nume", "")[:40] for c in p.get("companii", []) if c.get("nume")})[:4]
        inst = sorted({d.get("institutie", "")[:40] for d in p.get("declaratii", []) if d.get("institutie")})[:4]
        autodecl = p.get("firme_contracte_autodeclarate") or []
        rec = {"n": nume, "k": _ck(nume), "t": "p", "inc": p.get("incredere", ""),
               "nd": nd, "nc": nc}
        if rol:
            rec["rol"] = rol
        if ct:
            rec["ct"] = int(ct)
        if comp:
            rec["co"] = comp
        if inst:
            rec["in"] = inst
        if autodecl:
            rec["conflict"] = [{"f": a["nume"][:40], "v": a.get("total_ron")} for a in autodecl[:3]]
        items.append(rec)

    # 2. COMPANII (din index) + contracte
    cf = {int(r["cui"]): r for r in _load(os.path.join(V, "achizitii/contracte_firme.json")).get("firme", [])
          if str(r.get("cui", "")).isdigit()}
    for c in _load(os.path.join(V, "companii/_index.json")).get("data", []):
        nume = c.get("name", "")
        if not nume:
            continue
        cui = c.get("cui")
        fin = c.get("financials") or {}
        rec = {"n": nume, "k": _ck(nume), "t": "c", "cui": cui, "sector": (c.get("sector") or "")[:30]}
        if c.get("legal_reps"):
            rec["reps"] = c["legal_reps"][:5]
        if fin.get("cifra_afaceri_ron") or fin.get("profit_net_ron"):
            rec["fin"] = {"ca": fin.get("cifra_afaceri_ron"), "profit": fin.get("profit_net_ron")}
        try:
            ctr = cf.get(int(cui))
            if ctr:
                rec["contracte"] = {"total": ctr.get("total_ron"), "nr": ctr.get("nr_contracte")}
        except (ValueError, TypeError):
            pass
        items.append(rec)

    # 3. PARTIDE
    for p in _load(os.path.join(V, "partide/partide.json")).get("partide", []):
        items.append({"n": p["cod"], "k": _ck(p["cod"]), "t": "partid",
                      "subv": p.get("total_subventie_lei"), "rvc": p.get("nr_rapoarte_rvc"),
                      "dep": p.get("nr_deputati"), "sen": p.get("nr_senatori")})

    out = os.path.join(V, "search")
    os.makedirs(out, exist_ok=True)
    json.dump({"total": len(items), "tipuri": {"p": "persoană", "c": "companie", "partid": "partid"},
               "items": items}, open(os.path.join(out, "index.json"), "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))
    sz = os.path.getsize(os.path.join(out, "index.json")) // 1024
    np = sum(1 for i in items if i["t"] == "p")
    nc = sum(1 for i in items if i["t"] == "c")
    print(f"PUBLICAT search/index.json: {len(items)} entități ({np} persoane + {nc} companii + partide) | {sz} KB")
    return {"items": len(items), "kb": sz}


if __name__ == "__main__":
    main()
