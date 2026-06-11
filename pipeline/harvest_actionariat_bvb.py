"""Harvest ACȚIONARIATUL companiilor de stat LISTATE la BVB (% deținut, gratis + public).

ONRC open data NU are asociați/acționari (doar reps). Dar pt. SOE-urile listate la BVB structura
acționariatului e PUBLICĂ: `bvb.ro/.../FinancialInstrumentsDetails.aspx?s=SIMBOL` → tabel
Acționar/Acțiuni/Procent + capitalizare. Umple gap-ul acționariat (T1/D7) pt. companiile mari.
Output data/v1/companii/actionariat_bvb.json.
"""

from __future__ import annotations

import html
import json
import os
import re
import time

import requests
import urllib3

urllib3.disable_warnings()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V = os.path.join(ROOT, "data/v1")
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"}
URL = "https://www.bvb.ro/FinancialInstruments/Details/FinancialInstrumentsDetails.aspx?s="

# SOE-uri + companii cu participație de stat, listate la BVB (simbol → nume uzual)
SYMBOLS = {
    "SNG": "Romgaz", "SNN": "Nuclearelectrica", "H2O": "Hidroelectrica", "TGN": "Transgaz",
    "TEL": "Transelectrica", "EL": "Electrica", "COTE": "Conpet", "OIL": "Oil Terminal",
    "SNP": "OMV Petrom", "FP": "Fondul Proprietatea", "SOCP": "Socep", "CMP": "Compa",
    "TRP": "Teraplast", "ALR": "Alro", "ATB": "Antibiotice", "PTR": "Rompetrol Well Services",
}
STATE_RE = re.compile(r"STATUL ROM|MINISTERUL|FONDUL PROPRIETATEA|CONSILIUL (JUDETEAN|LOCAL)|PRIMARIA|UAT", re.I)


def _num(s):
    return s.replace(".", "").replace(",", ".").rstrip(" %").strip()


def _scrape(sym):
    t = requests.get(URL + sym, headers=H, verify=False, timeout=25).text
    actionari = []
    for r in re.findall(r"<tr[^>]*>(.*?)</tr>", t, re.S):
        cells = [re.sub(r"<[^>]+>", "", html.unescape(c)).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)]
        cells = [c for c in cells if c]
        # rând acționar: [nume, acțiuni, "NN,NN %"]
        if len(cells) >= 3 and re.match(r"^[\d.]+$", cells[1].replace(".", "")) and "%" in cells[2]:
            nume = cells[0]
            if nume.upper() in ("TOTAL",):
                continue
            try:
                pct = float(_num(cells[2]))
            except ValueError:
                continue
            actionari.append({"actionar": re.sub(r"\s+", " ", nume)[:80], "actiuni": cells[1],
                              "procent": pct, "stat": bool(STATE_RE.search(nume))})
    cap = re.search(r"Capitalizare[^0-9]*([\d.,]+)", html.unescape(t))
    caps = re.search(r"Capital social[^0-9]*([\d.,]+)", html.unescape(t))
    pct_stat = round(sum(a["procent"] for a in actionari if a["stat"]), 4)
    return {"actionari": actionari, "procent_stat": pct_stat,
            "capitalizare_ron": cap.group(1) if cap else None,
            "capital_social_ron": caps.group(1) if caps else None}


def main() -> dict:
    out = []
    for sym, nume in SYMBOLS.items():
        try:
            d = _scrape(sym)
        except Exception as e:
            print(f"   FAIL {sym}: {type(e).__name__}", flush=True)
            continue
        if not d["actionari"]:
            print(f"   {sym} ({nume}): fără structură acționariat", flush=True)
            continue
        rec = {"simbol": sym, "nume": nume, **d}
        out.append(rec)
        print(f"   {sym:5} {nume:22} stat={d['procent_stat']:7}% | "
              f"{len(d['actionari'])} acționari | cap={d['capitalizare_ron']}", flush=True)
        time.sleep(0.4)
    out.sort(key=lambda x: -x["procent_stat"])
    os.makedirs(os.path.join(V, "companii"), exist_ok=True)
    json.dump({"sursa": "BVB structura acționariatului (bvb.ro)", "nota": "% deținut de stat pt. SOE-uri "
               "LISTATE (public). Pt. firme nelistate, acționarii nu-s gratis (ONRC=doar reps).",
               "total": len(out), "cu_participatie_stat": sum(1 for x in out if x["procent_stat"] > 0),
               "companii": out},
              open(os.path.join(V, "companii/actionariat_bvb.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"PUBLICAT actionariat_bvb.json: {len(out)} companii listate, "
          f"{sum(1 for x in out if x['procent_stat']>0)} cu participație de stat", flush=True)
    return {"companii": len(out)}


if __name__ == "__main__":
    main()
