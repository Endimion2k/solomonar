"""Consolidează entitatea PARTID: subvenții (2008-2026) + rapoarte RVC + nr. parlamentari.

Leagă cele 3 surse pe un cod canonic de partid (subvenții folosesc 'PSD', RVC 'psd',
deputati/senatori 'Partidul Social Democrat'). Output data/v1/partide/partide.json — entitate
queryable pt. graf (partid → bani de stat + raportări + membri în parlament).
"""

from __future__ import annotations

import json
import os
import re
import sys
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V = os.path.join(ROOT, "data/v1")

# cod canonic → tipare de potrivire (normalizate fără diacritice, lowercase)
CANON = {
    "PSD": ["psd", "social democrat"],
    "PNL": ["pnl", "national liberal"],
    "AUR": ["aur", "alianta pentru unirea romanilor"],
    "USR": ["usr", "uniunea salvati romania", "salvati romania", "plus"],
    "UDMR": ["udmr", "maghiara", "rmdsz"],
    "POT": ["pot", "partidul oamenilor tineri"],
    "SOS": ["sos", "s.o.s"],
    "PMP": ["pmp", "miscarea populara"],
    "PRO": ["pro romania"],
    "ALDE": ["alde"],
    "PDL": ["pdl", "democrat liberal"],
    "PRM": ["prm", "romania mare"],
    "PC": ["partidul conservator"],
    "PPDD": ["poporului dan diaconescu", "ppdd"],
    "UNPR": ["unpr"],
    "FC": ["forta civica"],
    "FD": ["forta dreptei"],
    "PNTCD": ["pntcd", "taranesc crestin"],
    "PFN": ["pfn"],
}


def _norm(s):
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()


def _canon(name):
    n = _norm(name)
    for code, pats in CANON.items():
        if _norm(code) == n.strip() or any(p in n for p in pats):
            return code
    return None


def main() -> dict:
    parties = {}

    def P(code):
        return parties.setdefault(code, {"cod": code, "subventii_pe_an": {}, "total_subventie_lei": 0,
                                         "rapoarte_rvc": [], "nr_deputati": 0, "nr_senatori": 0})

    # 1. subvenții (subventii.json)
    sub = json.load(open(os.path.join(V, "partide/subventii.json"), encoding="utf-8")).get("subventii", [])
    for r in sub:
        c = _canon(r.get("partid"))
        if not c:
            continue
        p = P(c)
        an = str(r.get("an"))
        p["subventii_pe_an"][an] = p["subventii_pe_an"].get(an, 0) + (r.get("suma_lei") or 0)
        p["total_subventie_lei"] += (r.get("suma_lei") or 0)

    # 2. rapoarte RVC
    rvc_path = os.path.join(V, "partide/rapoarte_rvc.json")
    if os.path.exists(rvc_path):
        rvc = json.load(open(rvc_path, encoding="utf-8"))
        for r in (rvc.get("data") or rvc.get("rapoarte") or []):
            c = _canon(r.get("partid") or r.get("partid_cod"))
            if not c:
                continue
            P(c)["rapoarte_rvc"].append({"an": r.get("an"), "doc_id": r.get("doc_id"),
                                         "url": r.get("url"), "venituri": r.get("venituri")})

    # 3. parlamentari (party membership)
    dep = json.load(open(os.path.join(V, "parlament/deputati.json"), encoding="utf-8"))
    deps = dep.get("data") or dep.get("deputati") or []
    for d in (deps if isinstance(deps, list) else deps.values()):
        c = _canon(d.get("current_party") or d.get("current_group"))
        if c:
            P(c)["nr_deputati"] += 1
    sen = json.load(open(os.path.join(V, "parlament/senatori.json"), encoding="utf-8"))
    sens = sen.get("data") or sen.get("senatori") or []
    for s in (sens if isinstance(sens, list) else sens.values()):
        c = _canon(s.get("party") or s.get("group"))
        if c:
            P(c)["nr_senatori"] += 1

    out = sorted(parties.values(), key=lambda x: -x["total_subventie_lei"])
    for p in out:
        p["nr_rapoarte_rvc"] = len(p["rapoarte_rvc"])
    json.dump({"total_partide": len(out), "sursa": "subventii (EFOR/AEP) + RVC (Monitorul Oficial) + parlament",
               "partide": out}, open(os.path.join(V, "partide/partide.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"PUBLICAT partide.json: {len(out)} partide", flush=True)
    for p in out[:6]:
        print(f"   {p['cod']}: subv total {p['total_subventie_lei']:,} lei | RVC {p['nr_rapoarte_rvc']} | "
              f"dep {p['nr_deputati']} sen {p['nr_senatori']}", flush=True)
    return {"partide": len(out)}


if __name__ == "__main__":
    main()
