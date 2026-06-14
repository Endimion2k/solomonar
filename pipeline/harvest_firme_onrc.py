"""Îmbogățește firmele FOLLOW-THE-MONEY cu profil ONRC (gratis, data.gov.ro) — „info-firme, dar mai bun".

info-firme (tudorr89) = aceeași sursă ONRC, dar doar lookup generic. Noi adăugăm context de
ACCOUNTABILITY pe firmele care au luat bani de la stat: forma juridică, județ, data înmatriculării,
site, FIRMĂ-MAMĂ STRĂINĂ, CAEN. + flag-uri: firmă nouă care a câștigat contracte, PF/AF cu bani de
stat, capital străin. Stream OD_FIRME (CUI direct) + OD_CAEN_AUTORIZAT (via COD_INMATRICULARE).
Output companii/firme_onrc.json. Țintă: câștigătorii de contracte + furnizorii de achiziții directe.
"""

from __future__ import annotations

import json
import os
import re
import sys

import requests
import urllib3

urllib3.disable_warnings()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V = os.path.join(ROOT, "data/v1")
DS = "https://data.gov.ro/dataset/02a76fa6-70ef-47ed-8237-333f9b6b5939/resource"
URL_FIRME = f"{DS}/e5b53db7-525c-4366-aeb2-fb721446e6d1/download/od_firme.csv"
URL_CAEN = f"{DS}/bd4675cf-d3f1-402d-a750-16fcc9b0b9f2/download/od_caen_autorizat.csv"
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"}

CAEN_DIV = {  # primele 2 cifre → diviziune (sumar)
    "01": "Agricultură", "02": "Silvicultură", "10": "Alimentar", "41": "Construcții clădiri",
    "42": "Construcții inginerești", "43": "Construcții specializate", "45": "Comerț auto",
    "46": "Comerț gros", "47": "Comerț detail", "49": "Transport terestru", "62": "IT/software",
    "63": "Servicii informatice", "71": "Arhitectură/inginerie", "72": "Cercetare", "82": "Servicii suport",
    "84": "Administrație publică", "86": "Sănătate", "35": "Energie", "36": "Apă", "38": "Salubritate",
}


def _load(p):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


def _targets():
    cuis = set()
    cf = _load(os.path.join(V, "achizitii/contracte_firme.json"))
    for r in ((cf or {}).get("firme") or []):
        if str(r.get("cui", "")).isdigit():
            cuis.add(int(r["cui"]))
    ad = _load(os.path.join(V, "companii/achizitii_directe.json"))
    for r in ((ad or {}).get("furnizori") or []):
        if str(r.get("cui", "")).isdigit():
            cuis.add(int(r["cui"]))
    return cuis


def _stream(url):
    with requests.get(url, headers=H, stream=True, timeout=300, verify=False) as r:
        r.raise_for_status()
        r.encoding = "utf-8"
        it = r.iter_lines(decode_unicode=True)
        cols = next(it).lstrip("﻿").split("^")
        idx = {c.strip().upper(): i for i, c in enumerate(cols)}
        for line in it:
            if line:
                yield line.split("^"), idx


def main() -> dict:
    cuis = _targets()
    print(f"CUI-uri țintă (firme cu bani de stat): {len(cuis)}", flush=True)

    firme = {}      # cui -> profil
    reg2cui = {}    # cod_inmatriculare -> cui (pt. join CAEN)
    n = 0
    for p, idx in _stream(URL_FIRME):
        n += 1
        if n % 1_000_000 == 0:
            print(f"   OD_FIRME: {n//1_000_000}M, găsite={len(firme)}", flush=True)
        try:
            cui = int(p[idx["CUI"]])
        except (ValueError, IndexError, KeyError):
            continue
        if cui not in cuis or cui in firme:
            continue
        reg = p[idx["COD_INMATRICULARE"]].strip() if "COD_INMATRICULARE" in idx else ""
        data = p[idx.get("DATA_INMATRICULARE", -1)].strip() if "DATA_INMATRICULARE" in idx else ""
        an = re.search(r"(\d{4})", data)
        firme[cui] = {
            "cui": cui, "reg_com": reg,
            "forma_juridica": p[idx["FORMA_JURIDICA"]].strip() if "FORMA_JURIDICA" in idx else "",
            "judet": p[idx["ADR_JUDET"]].strip() if "ADR_JUDET" in idx else "",
            "localitate": p[idx["ADR_LOCALITATE"]].strip() if "ADR_LOCALITATE" in idx else "",
            "an_infiintare": int(an.group(1)) if an else None,
            "web": p[idx["WEB"]].strip() if "WEB" in idx and len(p) > idx["WEB"] else "",
            "tara_mama": p[idx["TARA_FIRMA_MAMA"]].strip() if "TARA_FIRMA_MAMA" in idx and len(p) > idx["TARA_FIRMA_MAMA"] else "",
        }
        if reg:
            reg2cui[reg] = cui
    print(f"[firme] {len(firme)}/{len(cuis)} CUI-uri găsite în OD_FIRME", flush=True)

    # CAEN principal (primul cod per firmă) via cod înmatriculare
    n = 0
    for p, idx in _stream(URL_CAEN):
        n += 1
        if n % 2_000_000 == 0:
            print(f"   OD_CAEN: {n//1_000_000}M", flush=True)
        try:
            reg = p[idx["COD_INMATRICULARE"]].strip()
        except (IndexError, KeyError):
            continue
        cui = reg2cui.get(reg)
        if cui and not firme[cui].get("caen"):
            cod = p[idx.get("COD_CAEN_AUTORIZAT", 1)].strip() if len(p) > 1 else ""
            if cod:
                firme[cui]["caen"] = cod
                firme[cui]["caen_domeniu"] = CAEN_DIV.get(cod[:2], "")

    # firme cu contracte (an primul contract) pt. flag „firmă nouă"
    cf = {int(r["cui"]): r for r in (_load(os.path.join(V, "achizitii/contracte_firme.json")) or {}).get("firme", [])
          if str(r.get("cui", "")).isdigit()}
    ad = {int(r["cui"]): r for r in (_load(os.path.join(V, "companii/achizitii_directe.json")) or {}).get("furnizori", [])
          if str(r.get("cui", "")).isdigit()}

    out = list(firme.values())
    for f in out:
        cui = f["cui"]
        f["are_contracte"] = cui in cf
        f["are_achizitii_directe"] = cui in ad
        # flag-uri de accountability
        flags = []
        ani_active = (ad.get(cui, {}).get("ani_activi") or []) + [str(x) for x in (cf.get(cui, {}).get("ani", []) or [])]
        an_prim = min((int(a) for a in ani_active if str(a).isdigit()), default=None)
        if f.get("an_infiintare") and an_prim and an_prim - f["an_infiintare"] <= 1:
            flags.append("firmă nouă cu bani de stat (înființată cu ≤1 an înainte de prima achiziție)")
        if f.get("forma_juridica") in ("PF", "PFA", "AF", "II", "IF"):
            flags.append(f"persoană fizică/întreprindere individuală ({f['forma_juridica']}) cu bani de stat")
        if f.get("tara_mama") and f["tara_mama"].lower() not in ("", "românia", "romania"):
            flags.append(f"firmă-mamă în {f['tara_mama']}")
        f["flaguri"] = flags

    flagged = [f for f in out if f["flaguri"]]
    os.makedirs(os.path.join(V, "companii"), exist_ok=True)
    json.dump({"sursa": "ONRC OD_FIRME + OD_CAEN_AUTORIZAT (data.gov.ro)",
               "nota": "Profil ONRC pt. firmele care au luat bani de la stat (contracte + achiziții directe). "
               "Flag-uri = semnale de interes pentru analiză, NU acuzații.",
               "total": len(out), "cu_caen": sum(1 for f in out if f.get("caen")),
               "cu_mama_straina": sum(1 for f in out if f.get("tara_mama") and f["tara_mama"].lower() not in ("", "românia", "romania")),
               "flagged": len(flagged), "firme": out},
              open(os.path.join(V, "companii/firme_onrc.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"PUBLICAT firme_onrc.json: {len(out)} firme | {sum(1 for f in out if f.get('caen'))} cu CAEN | "
          f"{len(flagged)} cu flag-uri", flush=True)
    return {"firme": len(out), "flagged": len(flagged)}


if __name__ == "__main__":
    main()
