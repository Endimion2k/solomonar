"""Cross-ref ROMEGA ↔ OpenSanctions — persoane/firme din graf care sunt SANCȚIONATE sau PEP.

OpenSanctions publică date FtM gratis (data.opensanctions.org). Streamuim datasetul (sanctions /
peps), păstrăm DOAR entitățile cu legătură RO (country/nationality/jurisdiction = ro/Romania) ca să
evităm false-pozitive de nume global, apoi matchuim pe name_key cu cele 56k persoane + companii.
Output data/v1/persoane_sanctiuni.json. Due-diligence: flag PEP/sancțiune internațională.
"""

from __future__ import annotations

import json
import os
import sys

import requests
import urllib3

urllib3.disable_warnings()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "packages", "romega_core"))
from romega_core.names import name_key  # noqa: E402

V = os.path.join(ROOT, "data/v1")
H = {"User-Agent": "Mozilla/5.0 (ROMEGA transparency)"}
DATASETS = {
    "sanctions": "https://data.opensanctions.org/datasets/latest/sanctions/entities.ftm.json",
    "peps": "https://data.opensanctions.org/datasets/latest/peps/entities.ftm.json",
}


def _ro(props):
    vals = []
    for k in ("country", "nationality", "jurisdiction", "citizenship"):
        vals += [str(x).lower() for x in props.get(k, [])]
    return any(v in ("ro", "rou", "romania", "românia") for v in vals)


def _first(props, key):
    v = props.get(key, [])
    return v[0] if v else None


def main() -> dict:
    only = sys.argv[1] if len(sys.argv) > 1 else None   # 'sanctions' / 'peps' / None=ambele
    # cheile noastre: persoane (gold) + companii
    g = json.load(open(os.path.join(V, "graf/persoane_gold.json"), encoding="utf-8")).get("persoane", [])
    pkeys = {}   # name_key -> romega_id (doar cele cu 3+ tokeni = încredere mare, evită omonimi)
    for p in g:
        nk = p.get("nume_key", "")
        if nk and len(nk.split()) >= 2:
            pkeys.setdefault(nk, p)
    print(f"chei persoane ROMEGA: {len(pkeys)}", flush=True)

    ro_entities = []
    for ds, url in DATASETS.items():
        if only and ds != only:
            continue
        print(f"stream {ds} …", flush=True)
        n = ro = hit = 0
        try:
            r = requests.get(url, headers=H, verify=False, timeout=600, stream=True)
            r.raise_for_status()
            for line in r.iter_lines(decode_unicode=True):
                if not line:
                    continue
                n += 1
                try:
                    e = json.loads(line)
                except Exception:
                    continue
                if e.get("schema") not in ("Person", "Company", "Organization", "LegalEntity"):
                    continue
                props = e.get("properties", {})
                if not _ro(props):
                    continue
                nm = _first(props, "name")
                if not nm:
                    continue
                ro += 1
                nk = name_key(nm)
                pm = pkeys.get(nk)
                if pm:
                    hit += 1
                ro_entities.append({
                    "nume": nm, "nume_key": nk, "schema": e.get("schema"), "dataset": ds,
                    "topics": props.get("topics", []), "tara": props.get("country", []),
                    "pozitie": _first(props, "position"), "motiv": _first(props, "notes") or _first(props, "program"),
                    "liste": e.get("datasets", [])[:6],
                    "in_graf": bool(pm), "romega_id": pm.get("romega_id") if pm else None,
                    "n_declaratii": pm.get("n_declaratii", 0) if pm else 0,
                    "n_companii": pm.get("n_companii", 0) if pm else 0,
                })
                if n % 200000 == 0:
                    print(f"   {ds}: {n} entități, RO={ro}, in_graf={hit}", flush=True)
            r.close()
        except Exception as e:
            print(f"   FAIL {ds}: {type(e).__name__} {str(e)[:50]}", flush=True)
        print(f"   {ds}: {n} entități, {ro} RO, {hit} în graf", flush=True)

    ro_entities.sort(key=lambda x: (x["dataset"] != "sanctions", not x["in_graf"], x["nume"]))
    pers = [e for e in ro_entities if e["schema"] == "Person"]
    json.dump({"nota": "Entități cu legătură ROMÂNIA din OpenSanctions (sancțiuni internaționale EU/OFAC/UN "
               "SAU Politically Exposed Persons). Lista e o REFERINȚĂ; 'in_graf'=apare și în ROMEGA "
               "(match pe nume, posibil omonim). Sancțiunile sunt măsuri internaționale documentate; "
               "PEP = expunere politică (așteptat pt. demnitari).",
               "total": len(ro_entities), "persoane": len(pers),
               "sanctiuni": sum(1 for e in ro_entities if e["dataset"] == "sanctions"),
               "pep": sum(1 for e in ro_entities if e["dataset"] == "peps"),
               "in_graf": sum(1 for e in ro_entities if e["in_graf"]), "entitati": ro_entities},
              open(os.path.join(V, "sanctiuni_ro.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"PUBLICAT sanctiuni_ro.json: {len(ro_entities)} entități RO "
          f"({sum(1 for e in ro_entities if e['dataset']=='sanctions')} sancțiuni, "
          f"{sum(1 for e in ro_entities if e['dataset']=='peps')} PEP, "
          f"{sum(1 for e in ro_entities if e['in_graf'])} în graf)", flush=True)
    return {"entitati": len(ro_entities)}


if __name__ == "__main__":
    main()
