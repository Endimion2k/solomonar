"""Graful follow-the-money — rezoluție de entități person-centric.

Leagă, pe nume normalizat (nume_norm), tot ce-am strâns:
- declarații avere/interese (cine + ce declară + la ce instituție)
- reprezentanți legali (ce companii de stat administrează)
- CV-uri (studii + experiență)

Output: graf/persoane.json (persoană → declarații + companii + cv) + graf/cross_links.json
(demnitari care ȘI conduc companii = follow-the-money). Onest: coliziuni de nume pt. nume cu
2 tokeni → flag 'incredere' (low/med/high după nr. tokeni).
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys
import unicodedata
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V = os.path.join(ROOT, "data/v1")


def _norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().upper()
    return " ".join(sorted(re.findall(r"[A-Z]{2,}", s)))


def _conf(norm):
    n = len(norm.split())
    return "high" if n >= 3 else ("med" if n == 2 else "low")


_CANON = {
    "PSD": ["psd", "social democrat"], "PNL": ["pnl", "national liberal"],
    "AUR": ["aur", "alianta pentru unirea romanilor"], "USR": ["usr", "salvati romania", "plus"],
    "UDMR": ["udmr", "maghiara", "rmdsz"], "POT": ["pot", "oamenilor tineri"],
    "SOS": ["sos", "s.o.s"], "PMP": ["pmp", "miscarea populara"], "PRO": ["pro romania"],
    "FD": ["forta dreptei"], "ALDE": ["alde"],
}


def _canon_party(name):
    import unicodedata as u
    n = u.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    for code, pats in _CANON.items():
        if any(p in n for p in pats):
            return code
    return None


def main() -> dict:
    persoane = defaultdict(lambda: {"nume": "", "declaratii": [], "companii": [], "cv": None})

    # 1. declarații
    nd = 0
    for f in glob.glob(os.path.join(V, "declaratii/avere_*.json")) + \
            glob.glob(os.path.join(V, "declaratii/interese_*.json")):
        tip = "avere" if "/avere_" in f.replace("\\", "/") else "interese"
        src = os.path.basename(f).split("_", 1)[1][:-5]
        for d in json.load(open(f, encoding="utf-8")).get("declaratii", []):
            nm = d.get("nume_norm")
            if not nm:
                continue
            p = persoane[nm]
            p["nume"] = p["nume"] or d.get("nume", "")
            rec = {"tip": tip, "sursa": src, "institutie": d.get("institutie", "")}
            if tip == "avere":
                rec.update({k: d.get(k) for k in ("venituri_ron", "terenuri", "cladiri") if d.get(k)})
            else:
                rec.update({k: d.get(k) for k in ("conducere", "actionariat") if d.get(k)})
            p["declaratii"].append(rec)
            nd += 1

    # 2. reprezentanți legali (companii de stat)
    nc = 0
    reps = json.load(open(os.path.join(V, "companii/reprezentanti.json"), encoding="utf-8"))["companii"]
    cidx = {c["cui"]: c for c in json.load(open(os.path.join(V, "companii/_index.json"), encoding="utf-8"))["data"]}
    for c in reps:
        co = cidx.get(c["cui"], {})
        for r in c["reprezentanti"]:
            nm = _norm(r["nume"])
            p = persoane[nm]
            p["nume"] = p["nume"] or r["nume"]
            p["companii"].append({"cui": c["cui"], "nume": co.get("name", c.get("denumire", "")),
                                  "rol": r["calitate"], "sector": co.get("sector", ""),
                                  "status_fin": co.get("financial_status", ""),
                                  "financials": co.get("financials")})
            nc += 1

    # 3. CV-uri (conducere SOE/instituții + deputați)
    ncv = 0
    cv_files = [("companii/cv.json", "cv"), ("companii/cv_parlament.json", "cv"), ("companii/cv_senatori.json", "cv")]
    for fn, key in cv_files:
        p_ = os.path.join(V, fn)
        if not os.path.exists(p_):
            continue
        for r in json.load(open(p_, encoding="utf-8")).get(key, []):
            if not r.get("nume") or not (r.get("studii") or r.get("experienta")):
                continue
            nm = _norm(r["nume"])
            persoane[nm]["cv"] = {"studii": r.get("studii", ""), "experienta": r.get("experienta", ""),
                                  "entitate": r.get("entitate", "") or r.get("partid", "")}
            persoane[nm]["nume"] = persoane[nm]["nume"] or r["nume"]
            ncv += 1

    # 4. parlamentari (deputați + senatori) + partid + subvenția partidului
    partide_fin = {}
    pp = os.path.join(V, "partide/partide.json")
    if os.path.exists(pp):
        for p in json.load(open(pp, encoding="utf-8")).get("partide", []):
            partide_fin[p["cod"]] = {"total_subventie_lei": p["total_subventie_lei"],
                                     "nr_rapoarte_rvc": p.get("nr_rapoarte_rvc", 0)}
    parlam = {}
    for fn, key, cam, pcol in [("parlament/deputati.json", "deputati", "deputat", "current_party"),
                               ("parlament/senatori.json", "senatori", "senator", "party")]:
        d = json.load(open(os.path.join(V, fn), encoding="utf-8"))
        rows = d.get("data") or d.get(key) or []
        for r in (rows if isinstance(rows, list) else rows.values()):
            parlam[_norm(r.get("name", ""))] = {"camera": cam, "partid": _canon_party(r.get(pcol)),
                                                "legislatura": r.get("legislatura"), "judet": r.get("judet")}

    # finalizează
    out = []
    nparl = 0
    for nm, p in persoane.items():
        pl = parlam.get(nm)
        if pl:
            nparl += 1
            if pl.get("partid") and pl["partid"] in partide_fin:
                pl = {**pl, "partid_subventie_lei": partide_fin[pl["partid"]]["total_subventie_lei"]}
        rec = {"nume": p["nume"], "nume_norm": nm, "incredere": _conf(nm),
               "n_declaratii": len(p["declaratii"]), "n_companii": len({c["cui"] for c in p["companii"]}),
               "are_cv": p["cv"] is not None, "parlamentar": pl,
               "declaratii": p["declaratii"][:20], "companii": p["companii"], "cv": p["cv"]}
        out.append(rec)
    out.sort(key=lambda x: (-x["n_companii"], -x["n_declaratii"]))

    # cross-links: persoane în declarații ȘI cu companii (demnitar care conduce SOE)
    cross = [r for r in out if r["n_declaratii"] > 0 and r["n_companii"] > 0]

    os.makedirs(os.path.join(V, "graf"), exist_ok=True)
    json.dump({"total_persoane": len(out), "cu_declaratii": sum(1 for r in out if r["n_declaratii"]),
               "cu_companii": sum(1 for r in out if r["n_companii"]), "cu_cv": ncv,
               "cu_parlamentar": nparl,
               "persoane": out}, open(os.path.join(V, "graf/persoane.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    # cross-link nou: parlamentari care conduc companii de stat
    parl_co = [r for r in out if r.get("parlamentar") and r["n_companii"] > 0]
    json.dump({"nota": "Parlamentari (deputați/senatori) care conduc și companii de stat.",
               "total": len(parl_co), "links": parl_co},
              open(os.path.join(V, "graf/parlamentari_companii.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    json.dump({"nota": "Demnitari/declaranti care conduc si companii de stat. Atentie coliziuni nume "
               "(verifica 'incredere'=high pt. nume cu 3+ tokeni).", "total": len(cross),
               "links": cross}, open(os.path.join(V, "graf/cross_links.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"PUBLICAT graf: {len(out)} persoane unice | declaratii={nd} companii={nc} cv={ncv} parlamentari={nparl}")
    print(f"  cross-links (declarant + conduce companie): {len(cross)} "
          f"(high: {sum(1 for r in cross if r['incredere']=='high')})")
    print(f"  parlamentari care conduc companii de stat: {len(parl_co)}")
    return {"persoane": len(out), "cross": len(cross), "parl_co": len(parl_co)}


if __name__ == "__main__":
    main()
