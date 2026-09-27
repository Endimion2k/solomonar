"""Harvest guvernanta.gov.ro — registrul oficial al conducerii companiilor de stat (OUG 109/2011 art. 51).

Sursa: https://guvernanta.gov.ro/data/registry.json (Guvernul României, „Date deschise”): companiile
de stat centrale, persoanele din CA / directorat / conducerea executivă, remunerația brută lunară
declarată, afilierea politică, data de sfârșit a mandatului, CV-urile oficiale (PDF, adesea redactate)
și rapoartele anuale de remunerare.

Produce data/v1/guvernanta/registry.json, normalizat și legat de graful SOLOMONAR:
- companie → CUI (se leagă direct de companii/_index.json);
- persoană → romega_id din graf/persoane_gold.json:
    'confirmat' = același nume ȘI persoana apare deja la aceeași companie (CUI) în graf;
    'candidat'  = un singur om cu acest nume în graf, fără legătură cu compania (risc de omonimie);
- comparație cu reprezentanții legali ONRC (companii/reprezentanti.json): cine e numit oficial dar
  lipsește din ONRC și invers (semnal de verificat — datele ONRC pot fi mai vechi);
- cumul de funcții și distribuția afilierii politice.
Nu descarcă CV-urile — doar linkuri către documentele oficiale de pe guvernanta.gov.ro.

    python -m pipeline.harvest_guvernanta
"""

from __future__ import annotations

import collections
import json
import os
import re
import statistics
import sys
from datetime import datetime, timezone
from urllib.parse import quote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from solomonar_core.bronze import BronzeStore  # noqa: E402
from solomonar_core.http import Client  # noqa: E402
from solomonar_core.names import name_key  # noqa: E402

BASE = "https://guvernanta.gov.ro/"
URL = BASE + "data/registry.json"
V = os.path.join(ROOT, "data", "v1")
OUT = os.path.join(V, "guvernanta", "registry.json")

ROL_ORDER = {"board_chair": 0, "board_member": 1, "executive_director": 2, "director": 3, "other": 4}
FARA_PARTID = "Fără apartenență politică"
# reprezentanți ONRC care NU sunt conducere (insolvență, cenzori) sau sunt persoane juridice
_ONRC_SKIP_CALITATE = re.compile(r"judiciar|lichidator|insolv|cenzor|auditor", re.I)
_ONRC_SKIP_NAME = re.compile(r"\b(SPRL|IPURL|SCA|SRL|SA|S\.R\.L|S\.A|INSOLV|LICHIDARE|IPRL|CABINET)\b", re.I)


def _load(rel: str):
    p = os.path.join(V, rel)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}


def _doc_url(rel: str | None) -> str | None:
    return BASE + quote(rel, safe="/") if rel else None


def _party(raw) -> str | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    s = raw.strip().replace("ţ", "ț").replace("ş", "ș")
    return FARA_PARTID if s.lower().startswith("fără apartenență") else s


def _gold_index() -> dict[str, list[tuple[str, set[int]]]]:
    """name_key → [(romega_id, {CUI-uri la care persoana apare în graf})]."""
    idx: dict[str, list[tuple[str, set[int]]]] = collections.defaultdict(list)
    for p in _load("graf/persoane_gold.json").get("persoane", []):
        cuis = set()
        for c in p.get("companii") or []:
            try:
                cuis.add(int(c.get("cui")))
            except (TypeError, ValueError):
                pass
        idx[name_key(p.get("nume_key") or "")].append((p["romega_id"], cuis))
    return idx


def _onrc_index() -> dict[int, dict[str, str]]:
    """CUI → {name_key: nume afișat} pentru reprezentanții legali ONRC (fără lichidatori / firme)."""
    out: dict[int, dict[str, str]] = {}
    for c in _load("companii/reprezentanti.json").get("companii", []):
        try:
            cui = int(c.get("cui"))
        except (TypeError, ValueError):
            continue
        reps = {}
        for r in c.get("reprezentanti") or []:
            nume, cal = (r.get("nume") or "").strip(), r.get("calitate") or ""
            if nume and not _ONRC_SKIP_CALITATE.search(cal) and not _ONRC_SKIP_NAME.search(nume):
                reps[name_key(nume)] = nume.title()
        out[cui] = reps
    return out


def _match(key: str, cui: int, gold: dict) -> tuple[str | None, str | None, int]:
    cands = gold.get(key, [])
    same_company = [rid for rid, cuis in cands if cui in cuis]
    if len(same_company) == 1:
        return same_company[0], "confirmat", len(cands)
    if len(cands) == 1:
        return cands[0][0], "candidat", 1
    return None, None, len(cands)


def build(reg: dict) -> dict:
    gold, onrc = _gold_index(), _onrc_index()
    ours = {str(c.get("cui")): c.get("name") for c in _load("companii/_index.json").get("data", [])}
    inst = {i["id"]: i for i in reg.get("institutions", [])}
    people = {p["id"]: p for p in reg.get("people", [])}

    numiri = []
    for a in reg.get("appointments", []):
        i, p = inst.get(a.get("institution_id")), people.get(a.get("person_id"))
        if not i or not p:
            continue
        cui = int(re.sub(r"\D", "", str(i.get("cui"))) or 0)
        rid, match, n_cand = _match(name_key(p["full_name"]), cui, gold)
        comp = a.get("compensation") or {}
        cv = a.get("cv") or {}
        numiri.append({
            "id": a["id"], "cui": cui, "companie": i.get("name"), "persoana_id": p["id"],
            "nume": p["full_name"], "rol": (a.get("role") or {}).get("label"),
            "rol_categorie": (a.get("role") or {}).get("category"),
            "partid": _party(a.get("political_affiliation")),
            "brut_lunar_ron": comp.get("gross_ron"), "net_lunar_ron": comp.get("net_ron"),
            "mandat_pana_la": a.get("mandate_end_date"),
            "cv_url": _doc_url(cv.get("local_url")) or cv.get("public_url"),
            "romega_id": rid, "potrivire": match, "n_omonimi_graf": n_cand,
        })
    numiri.sort(key=lambda n: (n["companie"] or "", ROL_ORDER.get(n["rol_categorie"], 9), n["nume"]))

    by_cui: dict[int, list[dict]] = collections.defaultdict(list)
    for n in numiri:
        by_cui[n["cui"]].append(n)
    companii = []
    for i in reg.get("institutions", []):
        cui = int(re.sub(r"\D", "", str(i.get("cui"))) or 0)
        assets = i.get("assets") or {}
        ns = by_cui.get(cui, [])
        brut = [n["brut_lunar_ron"] for n in ns if n["brut_lunar_ron"]]
        rec = {
            "cui": cui, "nume": i.get("name"), "in_solomonar": str(cui) in ours,
            "autoritate_tutelara": i.get("supervising_authority"), "website": i.get("website_url"),
            "n_conducere": len(ns), "n_cu_partid": sum(1 for n in ns if n["partid"] and n["partid"] != FARA_PARTID),
            "brut_lunar_total_ron": round(sum(brut), 2) if brut else None,
            "rapoarte_remunerare": [{"nume": d.get("name"), "url": _doc_url(d.get("url"))}
                                    for d in assets.get("annual_remuneration_reports") or []],
            "contracte_mandat_model": [{"nume": d.get("name"), "url": _doc_url(d.get("url"))}
                                       for d in assets.get("mandate_templates") or []],
        }
        reps = onrc.get(cui)
        if reps is not None:
            oficial = {name_key(n["nume"]): n["nume"] for n in ns}
            rec["comparatie_onrc"] = {
                "doar_oficial": sorted(v for k, v in oficial.items() if k not in reps),
                "doar_onrc": sorted(v for k, v in reps.items() if k not in oficial),
                "comune": len(set(oficial) & set(reps)),
            }
        companii.append(rec)
    companii.sort(key=lambda c: c["nume"] or "")

    per_pers: dict[str, list[dict]] = collections.defaultdict(list)
    for n in numiri:
        per_pers[n["persoana_id"]].append(n)
    cumul = []
    for pid, ns in per_pers.items():
        if len({n["cui"] for n in ns}) > 1:
            brut = [n["brut_lunar_ron"] for n in ns if n["brut_lunar_ron"]]
            cumul.append({"persoana_id": pid, "nume": ns[0]["nume"], "romega_id": ns[0]["romega_id"],
                          "n_companii": len({n["cui"] for n in ns}),
                          "brut_lunar_total_ron": round(sum(brut), 2) if brut else None,
                          "functii": [{"companie": n["companie"], "cui": n["cui"], "rol": n["rol"]} for n in ns]})
    cumul.sort(key=lambda c: (-c["n_companii"], -(c["brut_lunar_total_ron"] or 0)))

    persoane_partid: dict[str, set] = collections.defaultdict(set)
    for n in numiri:
        persoane_partid[n["partid"] or "nedeclarat"].add(n["persoana_id"])
    rem = collections.defaultdict(list)
    for n in numiri:
        if n["brut_lunar_ron"]:
            rem[n["rol_categorie"]].append(n["brut_lunar_ron"])

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sursa": "guvernanta.gov.ro — Guvernul României, registrul companiilor de stat (OUG 109/2011 art. 51)",
        "source_url": URL,
        "source_generated_at": reg.get("generated_at"),
        "source_published_at": reg.get("published_at"),
        "nota": ("Date deschise publicate de Guvern. Remunerația = brut lunar declarat, așa cum e raportat "
                 "(câteva valori par incomplete la sursă). Potrivirea cu graful SOLOMONAR: 'confirmat' = nume + "
                 "aceeași companie; 'candidat' = nume unic, fără confirmare pe companie (posibilă omonimie). "
                 "Comparația cu ONRC e un semnal de verificat: registrul ONRC poate fi mai vechi."),
        "n_companii": len(companii), "n_persoane": len(people), "n_numiri": len(numiri),
        "n_potrivite": {"confirmat": sum(n["potrivire"] == "confirmat" for n in numiri),
                        "candidat": sum(n["potrivire"] == "candidat" for n in numiri)},
        "afiliere_politica": dict(sorted(((k, len(v)) for k, v in persoane_partid.items()), key=lambda kv: -kv[1])),
        "remuneratie_pe_rol": {k: {"n": len(v), "median": statistics.median(v), "max": max(v)}
                               for k, v in rem.items()},
        "companii": companii,
        "numiri": numiri,
        "cumul": cumul,
    }


def main() -> dict:
    client = Client(bronze=BronzeStore(os.path.join(ROOT, "data", "raw")), throttle_seconds=0.5, timeout=60)
    content, _ = client.fetch(URL, "guvernanta", ".json", use_cache=False)   # sursa se actualizează
    out = build(json.loads(content))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    print(f"PUBLICAT guvernanta/registry.json: {out['n_companii']} companii, {out['n_numiri']} numiri, "
          f"{out['n_persoane']} persoane | potrivite în graf: {out['n_potrivite']} | cumul: {len(out['cumul'])} "
          f"| sursă generată {out['source_generated_at']}", flush=True)
    return out


if __name__ == "__main__":
    main()
