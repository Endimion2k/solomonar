"""Generează achizitii/contracte_firme.json din fișierele SICAP pe ani (_sicap_<an>.json).

Până acum fișierul era combinat manual (iunie 2026) din _sicap_2024 și _sicap_2025; scriptul
reproduce aceeași agregare, ca să poată fi regenerat și verificat:
  pe CUI furnizor (doar cifre, fără prefixul RO): total_ron, nr_contracte adunate pe ani + anii.

`total_ron` e NET ESTIMAT când fișierele pe an vin din harvest_contracte_nete.py (fiecare contract o
singură dată, împărțit egal între semnatari; plafoanele de acord-cadru separat). Câmpurile
`total_ron_singur`, `total_ron_brut`, `plafon_acorduri_ron`, `nr_contracte_comune` și
`nr_acorduri_cadru` se adună și ele, dacă există. Fișierele vechi (iunie 2026) aveau doar suma brută.

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


EXTRA = ("total_ron_singur", "total_ron_brut", "plafon_acorduri_ron", "nr_contracte_comune", "nr_acorduri_cadru")
NOTA_BRUT = "brute: valoarea lotului se repetă la fiecare ofertant"
NOTA_NET = ("total_ron = net estimat: fiecare contract o singură dată, împărțit egal între semnatari; "
            "acordurile-cadru (plafoane) sunt separat în plafon_acorduri_ron; total_ron_brut = metoda veche")


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
            for k in EXTRA:
                if k in r:
                    x[k] = round(x.get(k, 0) + r[k], 2)
            if an not in x["ani"]:
                x["ani"].append(an)
    for x in m.values():
        x["total_ron"] = round(x["total_ron"], 2)
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
               "ani": sorted(pe_an),
               "nota_valori": NOTA_NET if all("statistici" in d for d in pe_an.values()) else NOTA_BRUT,
               "firme": firme},
              open(os.path.join(A, "contracte_firme.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"PUBLICAT contracte_firme.json: {len(firme)} firme din anii {sorted(pe_an)}", flush=True)
    return {"firme": len(firme)}


if __name__ == "__main__":
    main()
