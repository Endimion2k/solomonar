"""Îmbogățește companiile SOLOMONAR cu REPREZENTANȚI LEGALI din dump-ul ONRC (gratis, data.gov.ro).

Reps file e cheiat pe COD_INMATRICULARE (J40/.../...), nu CUI → punte via OD_FIRME (are CUI +
COD_INMATRICULARE). Stream filtrat (nu încărcăm ~1GB în RAM):
  1. CUI-uri țintă: companii de stat + firme ONRC relevante + (furnizori SICAP).
  2. stream OD_FIRME → COD_INMATRICULARE → CUI (doar pt. ținte).
  3. stream OD_REPREZENTANTI_LEGALI → reprezentanți (nume + calitate) pt. acele coduri.
  4. publică companii/reprezentanti.json + îmbogățește companii/_index.json (legal_reps).

Follow-the-money: cine administrează CFR/Tarom/Romgaz + firmele cu contracte de stat.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from pipeline.onrc_stream import dump_curent, randuri  # noqa: E402

V = os.path.join(ROOT, "data/v1")
MIN_KEEP_RATIO = 0.9   # țintele includ tot ce e publicat, deci o scădere mare = dump citit parțial


def _load(p):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


def _target_cuis() -> tuple[set, dict]:
    cuis, names = set(), {}
    ci = _load(os.path.join(V, "companii/_index.json"))
    rows = (ci.get("data") if ci else None) or []
    for c in rows:
        if c.get("cui"):
            cuis.add(int(c["cui"]))
            names[int(c["cui"])] = c.get("name", "")
    fr = _load(os.path.join(V, "onrc/firme_relevante.json"))
    frr = (fr.get("data") if isinstance(fr, dict) else fr) or []
    for f in frr:
        if f.get("cui"):
            cuis.add(int(f["cui"]))
    # furnizori SICAP (follow-the-money) — firmele care au câștigat contracte de stat + achiziții directe
    for fn, key in [("achizitii/contracte_firme.json", "firme"),
                    ("companii/achizitii_directe.json", "furnizori")]:
        d = _load(os.path.join(V, fn))
        for r in ((d.get(key) if isinstance(d, dict) else d) or []):
            if isinstance(r, dict) and r.get("cui"):
                try:
                    cui = int(r["cui"])
                    cuis.add(cui)
                    names.setdefault(cui, r.get("nume", ""))
                except (ValueError, TypeError):
                    pass
    # acoperirea nu se micșorează la refresh: firmele colectate anterior rămân ținte (reprezentanții lor
    # se reîmprospătează din dump-ul curent). Altfel, lista publicată de furnizori fiind plafonată la
    # top 50.000, orice schimbare a top-ului scotea din graf ~14.000 de firme și reprezentanții lor.
    prev = _load(os.path.join(V, "companii/reprezentanti.json"))
    for c in ((prev.get("companii") if isinstance(prev, dict) else None) or []):
        try:
            cuis.add(int(c["cui"]))
            names.setdefault(int(c["cui"]), c.get("denumire", ""))
        except (KeyError, ValueError, TypeError):
            pass
    return cuis, names


def main() -> dict:
    cuis, names = _target_cuis()
    print(f"CUI-uri țintă: {len(cuis)}", flush=True)
    publicate = len((_load(os.path.join(V, "companii/reprezentanti.json")) or {}).get("companii") or [])
    dump, urls = dump_curent("OD_FIRME", "OD_REPREZENTANTI_LEGALI")
    url_firme, url_reps = urls["OD_FIRME"], urls["OD_REPREZENTANTI_LEGALI"]

    # 2. OD_FIRME → COD_INMATRICULARE -> CUI (doar ținte)
    reg2cui: dict[str, int] = {}
    n = 0
    for parts, idx in randuri(url_firme):
        n += 1
        if n % 1_000_000 == 0:
            print(f"   OD_FIRME: {n//1_000_000}M rânduri, gasite={len(reg2cui)}", flush=True)
        try:
            cui = int(parts[idx["CUI"]])
        except (ValueError, IndexError, KeyError):
            continue
        if cui in cuis:
            reg = parts[idx["COD_INMATRICULARE"]].strip()
            if reg:
                reg2cui[reg] = cui
    print(f"[firme] mapate {len(reg2cui)}/{len(cuis)} CUI-uri la cod înmatriculare", flush=True)

    # 3. OD_REPREZENTANTI_LEGALI → reps
    reps: dict[int, list] = {}
    n = 0
    for parts, idx in randuri(url_reps):
        n += 1
        if n % 1_000_000 == 0:
            print(f"   OD_REPS: {n//1_000_000}M rânduri", flush=True)
        try:
            reg = parts[idx["COD_INMATRICULARE"]].strip()
        except (IndexError, KeyError):
            continue
        cui = reg2cui.get(reg)
        if cui:
            nume = parts[idx.get("PERSOANA_IMPUTERNICITA", 1)].strip() if len(parts) > 1 else ""
            cal = parts[idx.get("CALITATE", 2)].strip() if "CALITATE" in idx and len(parts) > idx["CALITATE"] else ""
            if nume:
                reps.setdefault(cui, []).append({"nume": nume[:120], "calitate": cal[:40]})

    # 4. publică + îmbogățește
    if len(reps) < publicate * MIN_KEEP_RATIO:
        raise SystemExit(f"REFUZ să suprascriu reprezentanti.json: {len(reps)} companii față de {publicate} "
                         f"publicate. Dump-ul ONRC a fost citit parțial; fișierul publicat rămâne neschimbat.")
    out =[{"cui": cui, "denumire": names.get(cui, ""), "reprezentanti": r} for cui, r in reps.items()]
    json.dump({"generated_at": datetime.now(timezone.utc).isoformat(), "sursa": "ONRC OD_REPREZENTANTI_LEGALI (data.gov.ro)", "dump": dump,
               "companii_cu_reprezentanti": len(reps), "total_reprezentanti": sum(len(r) for r in reps.values()),
               "companii": out},
              open(os.path.join(V, "companii/reprezentanti.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    # îmbogățește indexul de companii
    ci = _load(os.path.join(V, "companii/_index.json"))
    enriched = 0
    if ci:
        for c in ci["data"]:
            r = reps.get(int(c["cui"])) if c.get("cui") else None
            if r:
                c["legal_reps"] = sorted({x["nume"] for x in r})
                enriched += 1
        json.dump(ci, open(os.path.join(V, "companii/_index.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
    print(f"PUBLICAT reprezentanti.json: {len(reps)} companii cu reprezentanți "
          f"({sum(len(r) for r in reps.values())} total) | index îmbogățit: {enriched}", flush=True)
    return {"companii_cu_reps": len(reps), "enriched": enriched}


if __name__ == "__main__":
    main()
