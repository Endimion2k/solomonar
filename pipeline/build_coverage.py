"""Raport de ACOPERIRE — ce companii de stat / instituții au rămas fără site / declarații / CV.

Încrucișează lista completă (companii index + organizații) cu ce-am strâns:
  - declarații (set de instituții care AU declarații, din 'institutie' în avere_*/interese_*)
  - site/inventar (inventar_declaratii.json = entități cu pagină de declarații găsită)
  - reps / financials / acționariat (din companii index + BVB)
  - CV (entitățile cu CV)
Output data/v1/coverage.json — sumar + LISTE DE GOLURI (fără declarații, fără site).
"""

from __future__ import annotations

import glob
import json
import os
import re
import unicodedata
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V = os.path.join(ROOT, "data/v1")

STOP = {"sa", "srl", "ra", "regia", "autonoma", "compania", "nationala", "national", "societatea",
        "de", "si", "pentru", "din", "a", "al", "ale", "comerciala", "judeteana", "judetean",
        "consiliul", "judetul", "primaria", "comuna", "orasul", "municipiul"}


def _norm(s):
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()


def _toks(s):
    return {t for t in re.findall(r"[a-z]{4,}", _norm(s)) if t not in STOP}


def _load(p):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return {}


def main() -> dict:
    # 1. set de token-uri distinctive ale instituțiilor cu DECLARAȚII
    decl_tokens = set()
    decl_institutii = set()
    for f in glob.glob(os.path.join(V, "declaratii/avere_*.json")) + glob.glob(os.path.join(V, "declaratii/interese_*.json")):
        if os.path.basename(f).startswith("_"):
            continue
        for d in _load(f).get("declaratii", []):
            inst = d.get("institutie", "")
            if inst:
                decl_institutii.add(inst[:60])
                decl_tokens |= _toks(inst)

    # 2. entități cu site găsit (inventar) — CUI + token-uri nume
    inv = _load(os.path.join(V, "companii/inventar_declaratii.json"))
    inv_cuis = {str(s.get("cui")) for s in inv.get("surse", []) if s.get("cui")}
    inv_tokens = set()
    for s in inv.get("surse", []):
        inv_tokens |= _toks(s.get("nume", ""))

    # 3. acționariat BVB (CUI/nume)
    bvb = {_norm(c["nume"]) for c in _load(os.path.join(V, "companii/actionariat_bvb.json")).get("companii", [])}

    # 4. CV — token-uri entități cu CV
    cv_tokens = set()
    for fn in ("companii/cv.json", "companii/cv_parlament.json", "companii/cv_senatori.json"):
        for r in _load(os.path.join(V, fn)).get("cv", []):
            cv_tokens |= _toks(r.get("entitate", "") or "")

    def has_decl(name):
        t = _toks(name)
        return bool(t) and len(t & decl_tokens) >= max(1, len(t) // 2)

    # ---- COMPANII ----
    comp = _load(os.path.join(V, "companii/_index.json")).get("data", [])
    crows = []
    for c in comp:
        name = c.get("name", "")
        cui = str(c.get("cui", ""))
        rec = {"name": name, "cui": cui, "sector": c.get("sector") or "",
               "reps": bool(c.get("legal_reps")), "financials": bool(c.get("financials")),
               "actionariat": bool(c.get("bvb_listed")) or bool(c.get("shareholders")),
               "site": cui in inv_cuis,   # precis: CUI în inventarul de site-uri găsite
               "declaratii": has_decl(name)}
        rec["gol"] = not (rec["declaratii"] or rec["site"])   # nimic găsit (nici site, nici declarații)
        crows.append(rec)

    comp_gol = [r for r in crows if r["gol"]]
    comp_fara_decl = [r for r in crows if not r["declaratii"]]
    comp_fara_fin = [r for r in crows if not r["financials"]]

    # ---- ORGANIZAȚII (instituții) ----
    orgs = _load(os.path.join(V, "organizatii/_index.json"))
    orows_src = orgs.get("data") or orgs.get("organizatii") or []
    if isinstance(orows_src, dict):
        orows_src = list(orows_src.values())
    orows = []
    for o in orows_src:
        name = o.get("name") or o.get("nume") or ""
        if not name:
            continue
        orows.append({"name": name, "tip": o.get("tip", "") or o.get("type", ""),
                      "declaratii": has_decl(name), "cv": bool(_toks(name) & cv_tokens)})
    org_fara_decl = [r for r in orows if not r["declaratii"]]

    out = {
        "generat": "2026-06-11",
        "companii": {
            "total": len(crows),
            "cu_declaratii": sum(1 for r in crows if r["declaratii"]),
            "cu_site": sum(1 for r in crows if r["site"]),
            "cu_reps": sum(1 for r in crows if r["reps"]),
            "cu_financials": sum(1 for r in crows if r["financials"]),
            "cu_actionariat": sum(1 for r in crows if r["actionariat"]),
            "GOL_nici_site_nici_declaratii": len(comp_gol),
            "fara_declaratii": len(comp_fara_decl),
        },
        "organizatii": {
            "total": len(orows),
            "cu_declaratii": sum(1 for r in orows if r["declaratii"]),
            "cu_cv": sum(1 for r in orows if r["cv"]),
            "fara_declaratii": len(org_fara_decl),
        },
        "lista_companii_gol": sorted([{"name": r["name"], "cui": r["cui"], "sector": r["sector"],
                                       "reps": r["reps"], "financials": r["financials"]} for r in comp_gol],
                                     key=lambda x: x["name"])[:500],
        "lista_organizatii_fara_declaratii": sorted([r["name"] for r in org_fara_decl])[:500],
    }
    json.dump(out, open(os.path.join(V, "coverage.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    print("=== ACOPERIRE COMPANII (1.256) ===")
    for k, v in out["companii"].items():
        print(f"  {k}: {v}")
    print("=== ACOPERIRE ORGANIZAȚII ===")
    for k, v in out["organizatii"].items():
        print(f"  {k}: {v}")
    # golurile pe sector
    print("\nGOLURI companii (fără declarații) pe sector:")
    sect = Counter((r.get("sector") or "?")[:24] for r in comp_fara_decl)
    for s, n in sect.most_common(10):
        print(f"  {s:26} {n}")
    print(f"\nGOLURI TOTALE (nici site nici declarații): {len(comp_gol)} — exemple:")
    for r in comp_gol[:12]:
        print(f"  - {r['name'][:45]:45} [{(r['sector'] or '')[:18]}] reps={r['reps']} fin={r['financials']}")
    return out["companii"]


if __name__ == "__main__":
    main()
