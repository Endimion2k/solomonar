"""Generează achizitii/contracte_firme.json din fișierele SICAP pe ani (_sicap_<an>.json).

Până acum fișierul era combinat manual (iunie 2026) din _sicap_2024 și _sicap_2025; scriptul
reproduce aceeași agregare, ca să poată fi regenerat și verificat:
  pe CUI furnizor (doar cifre, fără prefixul RO): total_ron, nr_contracte adunate pe ani + anii.

Valorile sunt BRUTE (vezi harvest_sicap_an.py): în exportul SICAP valoarea lotului se repetă la
fiecare ofertant, deci sumele pe firmă supraestimează banii încasați.

_sicap_2023.json acoperă doar trimestrul III 2023 și nu intră implicit (anii incompleți ar strica
comparația între firme). Anii se aleg cu SICAP_ANI=2024,2025.
"""

from __future__ import annotations

import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
A = os.path.join(ROOT, "data/v1/achizitii")
ANI = [int(x) for x in os.environ.get("SICAP_ANI", "2024,2025").split(",") if x.strip()]


def _furnizori(d: dict) -> dict:
    """Ambele formate de _sicap_<an>.json: {"furnizori": {cui: ...}} sau direct {cui: ...}."""
    f = d.get("furnizori") if isinstance(d.get("furnizori"), dict) else d
    return {k: v for k, v in f.items() if isinstance(v, dict)}


def _cui(k) -> int | None:
    s = re.sub(r"\D", "", str(k))
    return int(s) if s and s == str(k).upper().replace("RO", "").strip() else None


def combina(pe_an: dict[int, dict]) -> list[dict]:
    m: dict[int, dict] = {}
    for an in sorted(pe_an):
        for k, r in _furnizori(pe_an[an]).items():
            cui = _cui(k)
            if not cui:
                continue
            x = m.setdefault(cui, {"cui": cui, "nume": r.get("nume") or "", "total_ron": 0.0,
                                   "nr_contracte": 0, "ani": []})
            x["total_ron"] += float(r.get("total_ron") or 0)
            x["nr_contracte"] += int(r.get("nr_contracte") or 0)
            if an not in x["ani"]:
                x["ani"].append(an)
    return sorted(m.values(), key=lambda x: -x["total_ron"])


def main() -> dict:
    pe_an = {}
    for an in ANI:
        p = os.path.join(A, f"_sicap_{an}.json")
        if os.path.exists(p):
            pe_an[an] = json.load(open(p, encoding="utf-8"))
    if not pe_an:
        raise SystemExit(f"niciun _sicap_<an>.json pentru anii {ANI}")
    firme = combina(pe_an)
    ani = "-".join(str(a) for a in sorted({min(pe_an), max(pe_an)}))
    json.dump({"total_firme": len(firme), "sursa": f"SICAP/ADR data.gov.ro {ani}",
               "ani": sorted(pe_an), "nota_valori": "brute: valoarea lotului se repetă la fiecare ofertant",
               "firme": firme},
              open(os.path.join(A, "contracte_firme.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"PUBLICAT contracte_firme.json: {len(firme)} firme din anii {sorted(pe_an)}", flush=True)
    return {"firme": len(firme)}


if __name__ == "__main__":
    main()
