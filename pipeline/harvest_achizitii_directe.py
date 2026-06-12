"""Harvest ACHIZIȚII DIRECTE (SICAP 2007-2025, ~22M) — streaming + agregare pe CUI furnizor.

Sursa: data.gov.ro ADR, mapate în _achizitii_map.json (86 resurse directe CSV/XLSX). NU stocăm cele
22M de rânduri — STREAMUIM fiecare resursă și AGREGĂM pe CastigatorCUI: {total_ron, nr, nume, ani,
top_autoritati}. Resume-safe per resursă (checkpoint). Output companii/achizitii_directe.json
(toți furnizorii cu total) — multiplică follow-the-money (cine a luat bani de la stat, direct).

CSV: delim '^', col CastigatorCUI/ValoareRON/AutoritateContractanta (auto-detect din header).
XLSX: openpyxl read_only streaming.
"""

from __future__ import annotations

import io
import json
import os
import re
import sys
import time

import requests
import urllib3

urllib3.disable_warnings()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(ROOT, "pipeline")
V = os.path.join(ROOT, "data/v1")
AGG = os.path.join(P, "_achizitii_directe_agg.json")   # CUI -> agregat (checkpoint)
CKPT = os.path.join(P, "_achizitii_directe_done.txt")  # url-uri procesate
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"}

# nume de coloane acceptate (lower, fără spații/diacritice)
COL_CUI = ["castigatorcui", "cuicastigator", "cui_castigator", "cuiofertant", "cui"]
COL_VAL = ["valoareron", "valoare_ron", "valoarecontractron", "valoarecontract", "valoare"]
COL_NUME = ["castigator", "ofertant", "furnizor", "denumirecastigator"]
COL_AUT = ["autoritatecontractanta", "autoritatecontractant", "denumireac", "autoritate"]


def _norm(s):
    return re.sub(r"[^a-z]", "", (s or "").lower())


def _pick(cols, cands):
    nc = [_norm(c) for c in cols]
    for cand in cands:
        if cand in nc:
            return nc.index(cand)
    return None


MAX_VAL = 2_000_000.0   # achizițiile directe au plafon legal (~270k-1M lei); peste 2M = garbage/misaliniat


def _num(s):
    s = re.sub(r"[^\d,.\-]", "", str(s or ""))
    if not s:
        return 0.0
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        v = float(s)
    except (ValueError, OverflowError):
        return 0.0
    return v if 0 < v <= MAX_VAL else 0.0   # sanitizare: skip garbage/outlieri imposibili


def _add(agg, cui, nume, val, an, aut):
    cui = re.sub(r"\D", "", str(cui))
    if not cui or val <= 0:
        return
    a = agg.setdefault(cui, {"cui": cui, "nume": nume[:80], "total_ron": 0.0, "nr": 0, "ani": {}, "aut": {}})
    a["total_ron"] += val
    a["nr"] += 1
    if nume and not a["nume"]:
        a["nume"] = nume[:80]
    if an:
        a["ani"][str(an)] = a["ani"].get(str(an), 0) + 1
    if aut:
        a["aut"][aut[:50]] = a["aut"].get(aut[:50], 0) + 1


def _stream_csv(url, agg, an):
    r = requests.get(url, headers=H, verify=False, timeout=300, stream=True)
    r.raise_for_status()
    r.encoding = "utf-8"
    it = r.iter_lines(decode_unicode=True)
    header = next(it)
    # delimitator: cel mai frecvent dintre candidați în header
    delim = max("^|;,", key=lambda d: header.count(d))
    cols = header.split(delim)
    ic, iv, inm, ia = _pick(cols, COL_CUI), _pick(cols, COL_VAL), _pick(cols, COL_NUME), _pick(cols, COL_AUT)
    if ic is None or iv is None:
        r.close()
        return 0
    ncols = len(cols)
    n = 0
    for line in it:
        if not line:
            continue
        p = line.split(delim)
        if len(p) != ncols:                # rând prost-aliniat (delimitator în câmp) → skip
            continue
        _add(agg, p[ic], p[inm] if inm is not None else "", _num(p[iv]), an,
             p[ia] if ia is not None else "")
        n += 1
    r.close()
    return n


def _iter_excel(b):
    """Iterator de rânduri peste Excel — calamine (robust pt. XLSX/XLS cu dimensiuni greșite)."""
    from python_calamine import CalamineWorkbook
    wb = CalamineWorkbook.from_filelike(io.BytesIO(b))
    ws = wb.get_sheet_by_index(0)
    for row in ws.to_python(skip_empty_area=True):
        yield row


def _stream_xlsx(url, agg, an):
    b = requests.get(url, headers=H, verify=False, timeout=600).content
    rows = _iter_excel(b)
    # header-ul poate fi pe oricare din primele 10 rânduri (titluri/bannere înainte)
    ic = iv = inm = ia = None
    for _ in range(10):
        try:
            header = [str(c or "") for c in next(rows)]
        except StopIteration:
            return 0
        ic, iv = _pick(header, COL_CUI), _pick(header, COL_VAL)
        if ic is not None and iv is not None:
            inm, ia = _pick(header, COL_NUME), _pick(header, COL_AUT)
            break
    if ic is None or iv is None:
        return 0
    n = 0
    for row in rows:
        if len(row) <= max(ic, iv):
            continue
        _add(agg, row[ic], str(row[inm]) if inm is not None and len(row) > inm and row[inm] else "",
             _num(row[iv]), an, str(row[ia]) if ia is not None and len(row) > ia and row[ia] else "")
        n += 1
    return n


def main() -> dict:
    res = json.load(open(os.path.join(P, "_achizitii_map.json"), encoding="utf-8"))
    res = res if isinstance(res, list) else res.get("resurse", res.get("data", []))
    directe = [r for r in res if r.get("tip") == "directe" and r.get("url")]
    directe.sort(key=lambda x: (x.get("an", 0), str(x.get("perioada", ""))))

    agg = json.load(open(AGG, encoding="utf-8")) if os.path.exists(AGG) else {}
    done = set(open(CKPT, encoding="utf-8").read().splitlines()) if os.path.exists(CKPT) else set()
    print(f"resurse directe: {len(directe)} | deja={len(done)} | CUI agregate={len(agg)}", flush=True)

    fc = open(CKPT, "a", encoding="utf-8")
    for r in directe:
        url, an, fmt = r["url"], r.get("an"), (r.get("format") or "").upper()
        if url in done:
            continue
        t0 = time.time()
        try:
            n = _stream_xlsx(url, agg, an) if "XLS" in fmt else _stream_csv(url, agg, an)
        except Exception as e:
            print(f"   FAIL {an} {r.get('perioada')}: {type(e).__name__} {str(e)[:40]}", flush=True)
            continue
        fc.write(url + "\n"); fc.flush()
        done.add(url)
        json.dump(agg, open(AGG, "w", encoding="utf-8"))   # checkpoint
        print(f"   {an} {r.get('perioada')} [{fmt}]: {n} rânduri, {round(time.time()-t0)}s | "
              f"CUI total={len(agg)}", flush=True)
    fc.close()

    # publică: top + cei legați de graf (companii de stat + firme cu contracte)
    out = sorted(agg.values(), key=lambda x: -x["total_ron"])
    for a in out:
        a["total_ron"] = round(a["total_ron"], 2)
        a["top_autoritati"] = [k for k, _ in sorted(a.pop("aut", {}).items(), key=lambda kv: -kv[1])[:3]]
        a["ani_activi"] = sorted(a.pop("ani", {}).keys())
    os.makedirs(os.path.join(V, "companii"), exist_ok=True)
    json.dump({"sursa": "data.gov.ro ADR achiziții directe SICAP 2007-2025", "total_furnizori": len(out),
               "total_achizitii": sum(a["nr"] for a in out),
               "valoare_totala_ron": round(sum(a["total_ron"] for a in out), 2),
               "furnizori": out[:50000]},
              open(os.path.join(V, "companii/achizitii_directe.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"PUBLICAT achizitii_directe.json: {len(out)} furnizori, "
          f"{sum(a['nr'] for a in out)} achiziții, {round(sum(a['total_ron'] for a in out)/1e9,1)} mld lei", flush=True)
    return {"furnizori": len(out)}


if __name__ == "__main__":
    main()
