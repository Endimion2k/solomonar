"""Cross-ref DNA ↔ graful SOLOMONAR — inculpați DNA care sunt declaranți/parlamentari/conduc companii.

Cel mai puternic semnal de accountability: o persoană numită într-un comunicat DNA (trimitere în
judecată) care apare ȘI în graful nostru (declarație de avere / mandat / administrator de companie
de stat). Match pe nume normalizat (name_key) → flag de încredere (nr. tokeni; fără CNP, omonim posibil).

⚠️ OUTPUT SENSIBIL — scrie în `_local/` (gitignored), NU în data/v1 (decizie user 2026-06-10): comunicatele
DNA = trimiteri în judecată NU condamnări (prezumția de nevinovăție) + match pe nume = omonim posibil →
asociere falsă a unui nevinovat cu un dosar penal. Doar pistă internă de investigație, nepublicată.
"""

from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "packages", "solomonar_core"))
sys.path.insert(0, ROOT)
from solomonar_core.names import name_key  # noqa: E402

V = os.path.join(ROOT, "data/v1")


def _load(p):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return {}


def main() -> dict:
    # graf gold: name_key → persoană (cu fapte)
    gold = {}
    for p in _load(os.path.join(V, "graf/persoane_gold.json")).get("persoane", []):
        nk = p.get("nume_key")
        if nk and (p.get("n_declaratii") or p.get("n_companii") or p.get("parlamentar")):
            # păstrează persoana cu cele mai multe legături per name_key
            cur = gold.get(nk)
            score = (p.get("n_declaratii", 0) + p.get("n_companii", 0))
            if not cur or score > cur[1]:
                gold[nk] = (p, score)

    dna = _load(os.path.join(V, "audit/dna.json")).get("data", [])
    # name_key → comunicate DNA în care apare numele
    nk_to_dna = {}
    for c in dna:
        for nm in c.get("nume_extrase", []):
            nk = name_key(nm)
            if nk and len(nk.split()) >= 2:
                nk_to_dna.setdefault(nk, {"nume": nm, "comunicate": []})
                nk_to_dna[nk]["comunicate"].append({"id": c["id"], "data": c.get("data"), "url": c["url"]})

    matches = []
    for nk, dnainfo in nk_to_dna.items():
        if nk not in gold:
            continue
        p = gold[nk][0]
        ntok = len(nk.split())
        conf = "high" if (ntok >= 3 or p.get("parlamentar")) else "med"
        pl = p.get("parlamentar")
        matches.append({
            "nume": dnainfo["nume"], "incredere": conf,
            "rol": (pl["camera"] + " " + str(pl.get("partid"))) if pl else "declarant/administrator",
            "n_declaratii": p.get("n_declaratii", 0), "n_companii": p.get("n_companii", 0),
            "companii": [c.get("nume", "") for c in p.get("companii", [])][:5],
            "total_contracte_ron": p.get("total_contracte_ron") or 0,
            "dna_comunicate": dnainfo["comunicate"][:5],
        })
    matches.sort(key=lambda x: (x["incredere"] != "high", -x["n_companii"], -x["n_declaratii"]))

    os.makedirs(os.path.join(ROOT, "_local"), exist_ok=True)
    json.dump({"nota": "Inculpați/menționați în comunicate DNA care apar ȘI în graful SOLOMONAR "
               "(declarație de avere / mandat / administrator companie). Match pe NUME (fără CNP) → "
               "'med' = posibil omonim (2 tokeni); 'high' = 3+ tokeni sau parlamentar. NU sunt verdicte; "
               "comunicatele DNA pot fi trimiteri în judecată, NU condamnări — prezumția de nevinovăție.",
               "total_matches": len(matches), "high_conf": sum(1 for m in matches if m["incredere"] == "high"),
               "matches": matches},
              open(os.path.join(ROOT, "_local/dna_cross.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"PUBLICAT dna_cross.json: {len(matches)} persoane în DNA ∩ graf "
          f"({sum(1 for m in matches if m['incredere']=='high')} high-conf)", flush=True)
    for m in matches[:10]:
        line = f"  [{m['incredere']}] {m['nume']} ({m['rol']}) decl={m['n_declaratii']} comp={m['n_companii']}"
        print(line.encode("ascii", "replace").decode(), flush=True)
    return {"matches": len(matches)}


if __name__ == "__main__":
    main()
