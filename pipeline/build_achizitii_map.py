"""Harta resurselor SICAP de pe data.gov.ro (achiziții directe + contracte) → pipeline/_achizitii_map.json.

Înlocuiește scriptul local ne-versionat `_build_achizitii_map.py` (vezi docs/AUDIT-2026-09.md, F18):
1. reîmprospătează catalogul prin API-ul CKAN (package_show pe seturile cunoscute + package_search pt.
   seturi noi „achizitii-publice-AAAA”) → pipeline/_achizitii_raw.json;
2. clasifică resursele (directe | contracte), extrage anul/perioada, completează dimensiunile lipsă
   (Range GET, fără descărcare) → pipeline/_achizitii_map.json, citit de harvest_achizitii_directe
   și harvest_redflags.
Include ANUL CURENT (versiunea veche se oprea la 2025).

    python -m pipeline.build_achizitii_map            # catalog proaspăt + hartă
    python -m pipeline.build_achizitii_map --offline  # doar hartă, din _achizitii_raw.json existent
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from datetime import date

import requests
import urllib3

urllib3.disable_warnings()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "pipeline", "_achizitii_raw.json")
OUT = os.path.join(ROOT, "pipeline", "_achizitii_map.json")
CKAN = "https://data.gov.ro/api/3/action/"
ORG = "agentia-pentru-agenda-digitala-a-romaniei"
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"}
AN_CURENT = date.today().year

EXCLUDE_PAT = re.compile(r"anunt|invitati|notificar|modificare")
ROMAN = {"i": "T1", "ii": "T2", "iii": "T3", "iv": "T4"}
MULTI = "achizitii-publice-2007-2016-contracte6"


def norm(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s.lower()).strip()


def parse_perioada(nname):
    if re.search(r"t\s*1\s*-\s*t\s*3", nname):
        return "T1-T3"
    m = re.search(r"\bt\s*-?\s*(iv|iii|ii|i)\b", nname)
    if m:
        return ROMAN[m.group(1)]
    m = re.search(r"\bt\s*-?\s*([1-4])\b", nname)
    if m:
        return "T" + m.group(1)
    m = re.search(r"\bs\s*-?\s*([12])\b", nname)
    if m:
        return "S" + m.group(1)
    return "an"


def classify(nname):
    if EXCLUDE_PAT.search(nname):
        return None
    if "directe" in nname:
        return "directe"
    if "contract" in nname:
        return "contracte"
    return None


def head_size(url):
    """Dimensiunea totală prin Range GET (serverul raportează Content-Range, corpul nu se citește)."""
    try:
        g = requests.get(url, verify=False, timeout=60, stream=True, headers={**H, "Range": "bytes=0-0"})
        cr, cl, status = g.headers.get("Content-Range") or "", g.headers.get("Content-Length"), g.status_code
        g.close()
        m = re.search(r"/(\d+)$", cr)
        return status, int(m.group(1)) if m else (int(cl) if cl else None)
    except Exception as e:
        print("  SIZE ERR", url[:80], type(e).__name__, file=sys.stderr)
        return None, None


def refresh_catalog(raw: dict) -> dict:
    """Resurse proaspete pt. seturile cunoscute + seturi noi „achizitii-publice-*” ale ADR."""
    names = set(raw)
    try:
        r = requests.get(CKAN + "package_search", params={"q": "achizitii publice", "fq": f"organization:{ORG}",
                                                          "rows": 200}, headers=H, verify=False, timeout=60)
        for p in r.json().get("result", {}).get("results", []):
            if re.search(r"achizit", p.get("name", "")):
                names.add(p["name"])
    except Exception as e:
        print(f"  package_search eșuat ({type(e).__name__}) — folosesc doar seturile cunoscute")
    out = {}
    for n in sorted(names):
        try:
            r = requests.get(CKAN + "package_show", params={"id": n}, headers=H, verify=False, timeout=60)
            res = r.json().get("result", {}).get("resources", [])
            out[n] = [{k: x.get(k) for k in ("name", "url", "format", "size", "last_modified", "created")}
                      for x in res]
            print(f"  {n:45} {len(res):3} resurse")
        except Exception as e:
            out[n] = raw.get(n, [])
            print(f"  {n:45} EȘEC ({type(e).__name__}) — păstrez lista veche ({len(out[n])})")
    return out


def build_map(raw: dict) -> dict:
    entries, skipped_2016_dupes, y2009_alt = [], [], []
    for ds_name, resources in raw.items():
        m = re.search(r"(20\d\d)", ds_name)
        ds_year = int(m.group(1)) if m else None
        multi = ds_name == MULTI
        for r in resources:
            name = r.get("name") or ""
            nname = norm(name)
            tip = classify(nname)
            if tip is None:
                continue
            ym = re.search(r"(200[7-9]|20[1-9][0-9])", nname)
            an = int(ym.group(1)) if ym else ds_year
            if an is None or an > AN_CURENT or (multi and ym is None):
                continue
            if multi and an == 2016:
                skipped_2016_dupes.append(name)       # 2016 are set dedicat
                continue
            if nname.startswith("y_contracte-2009"):
                y2009_alt.append(r["url"])            # re-upload al contracte-2009.csv
                continue
            size = r.get("size")
            entry = {"an": an, "perioada": parse_perioada(nname), "tip": tip, "url": r["url"],
                     "format": (r.get("format") or "").lstrip(".").upper(),
                     "size_mb": round(size / 1048576, 1) if size else None,
                     "nume_resursa": name.strip(), "dataset": ds_name}
            pm = re.search(r"part\s*([0-9])", nname)
            if pm:
                entry["part"] = int(pm.group(1))
            if "subsecvente" in nname:
                entry["subtip"] = "subsecvente"
            entries.append(entry)

    for e in (x for x in entries if x["size_mb"] is None):
        status, size = head_size(e["url"])
        if size:
            e["size_mb"] = round(size / 1048576, 1)

    pkey = {"an": 0, "S1": 1, "T1": 1, "T1-T3": 1, "T2": 2, "S2": 3, "T3": 3, "T4": 4}
    entries.sort(key=lambda e: (e["an"], pkey.get(e["perioada"], 9), e["tip"], e.get("part", 0)))
    years = sorted({e["an"] for e in entries})
    per_year: dict = {}
    for e in entries:
        per_year.setdefault(e["an"], {"directe": 0, "contracte": 0})[e["tip"]] += 1
    return {
        "_meta": {
            "sursa": f"data.gov.ro CKAN API, organizatie {ORG} (ADR/AADR)",
            "generat": date.today().isoformat(),
            "acoperire_ani": f"{years[0]}-{years[-1]}" if years else "",
            "goluri_ani": [y for y in range(2007, AN_CURENT + 1) if y not in years],
            "total_resurse": len(entries),
            "total_mb_estimat": round(sum(e["size_mb"] or 0 for e in entries), 1),
            "resurse_pe_an": {str(k): v for k, v in sorted(per_year.items())},
            "note": [
                "Exclus: anunturi de initiere/participare, invitatii, notificari si anunturi de atribuire, "
                "modificari de contract.",
                f"2016 apare si in '{MULTI}'; pastrat doar setul dedicat. Dubluri omise: {len(skipped_2016_dupes)}",
                f"y_contracte-2009.csv = re-upload al contracte-2009.csv; URL-uri alternative: {len(y2009_alt)}",
                "Contracte 2012-2016 sunt pe semestre (S1/S2); 'subsecvente' = contracte sub acord-cadru.",
            ],
        },
        "resurse": entries,
    }


def main(argv=None) -> dict:
    ap = argparse.ArgumentParser(prog="build_achizitii_map")
    ap.add_argument("--offline", action="store_true", help="fără rețea pt. catalog: doar hartă din raw existent")
    args = ap.parse_args(argv)
    raw = json.load(open(RAW, encoding="utf-8")) if os.path.exists(RAW) else {}
    if not args.offline:
        raw = refresh_catalog(raw)
        json.dump(raw, open(RAW, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    out = build_map(raw)
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    m = out["_meta"]
    print(f"SCRIS {os.path.relpath(OUT, ROOT)}: {m['total_resurse']} resurse, ~{m['total_mb_estimat']} MB, "
          f"ani {m['acoperire_ani']} | pe an (ultimii 3): "
          f"{ {k: v for k, v in list(m['resurse_pe_an'].items())[-3:]} }", flush=True)
    return out


if __name__ == "__main__":
    main()
