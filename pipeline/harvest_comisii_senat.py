"""Harvest comisiile permanente ale SENATULUI — componența (ce senatori, ce rol).

senat.ro e ASP.NET-gated, dar taburile comisiei sunt URL-uri GET directe (nu postback):
  - comisii.aspx → 23 comisii (ComisieID GUID + nume)
  - ComponentaComisii.aspx?ComisieID=GUID → membri (FisaSenator ParlamentarID + nume + rol)
Output data/v1/comisii/senat_comisii.json (comisie → membri) + index senator→comisii.
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
BASE = "https://www.senat.ro"


def _get(url):
    return html.unescape(requests.get(url, headers=H, verify=False, timeout=30).text)


def _committees():
    """(GUID, nume) pentru cele 23 comisii permanente de pe comisii.aspx."""
    t = _get(f"{BASE}/comisii.aspx")
    # orice link cu ComisieID + text; numele real = textul care începe cu 'Comisia'
    pairs = re.findall(r'<a[^>]*ComisieID=([0-9a-fA-F\-]{30,})[^>]*>\s*([^<]{4,90}?)\s*</a>', t, re.I)
    names = {}
    order = []
    for guid, txt in pairs:
        g = guid.upper()
        nm = re.sub(r"\s+", " ", txt).strip()
        if g not in order:
            order.append(g)
        if nm.lower().startswith("comisia") and g not in names:
            names[g] = nm
    return [{"comisie_id": g, "nume": names.get(g, "")} for g in order]


def _members(guid):
    t = _get(f"{BASE}/ComponentaComisii.aspx?Zi=&ComisieID={guid}")
    # nume comisie din pagină (dacă lipsea)
    cn = re.search(r'(Comisia[^<\r\n]{5,90})', re.sub(r"<[^>]+>", " ", t))
    membri = []
    # rolul apare adesea ca header de secțiune înainte de blocul de membri
    # parsăm secvențial: marcăm rolul curent, apoi fiecare link FisaSenator
    rol_curent = "Membru"
    for m in re.finditer(
        r'(Preşedinte|Vicepreşedinte|Secretar)\b'
        r'|<a[^>]*FisaSenator\.aspx\?[^"\']*ParlamentarID=([0-9a-fA-F\-]{20,})[^>]*>([^<]+)</a>', t):
        if m.group(1):
            rol_curent = m.group(1)
        elif m.group(2):
            membri.append({"nume": re.sub(r"\s+", " ", m.group(3)).strip(),
                           "parlamentar_id": m.group(2).upper(), "rol": rol_curent})
            rol_curent = "Membru"   # rolul se aplică doar membrului imediat următor
    return (cn.group(1).strip() if cn else ""), membri


def main() -> dict:
    comisii = _committees()
    print(f"comisii găsite: {len(comisii)}", flush=True)
    sen_to_com = {}   # parlamentar_id -> [comisii]
    for c in comisii:
        try:
            _, membri = _members(c["comisie_id"])
        except Exception as e:
            print(f"   FAIL {c['comisie_id'][:8]}: {type(e).__name__}", flush=True)
            membri = []
        c["membri"] = membri
        c["n_membri"] = len(membri)
        for m in membri:
            sen_to_com.setdefault(m["parlamentar_id"], []).append({"comisie": c["nume"], "rol": m["rol"]})
        print(f"   {c['nume'][:45]:45} → {len(membri)} membri", flush=True)
        time.sleep(0.2)

    os.makedirs(os.path.join(V, "comisii"), exist_ok=True)
    json.dump({"sursa": "senat.ro ComponentaComisii.aspx", "total_comisii": len(comisii),
               "total_locuri": sum(c["n_membri"] for c in comisii), "comisii": comisii},
              open(os.path.join(V, "comisii/senat_comisii.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    json.dump({"nota": "senator (ParlamentarID) → comisiile din care face parte",
               "total_senatori": len(sen_to_com), "index": sen_to_com},
              open(os.path.join(V, "comisii/senat_membru_index.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"PUBLICAT senat_comisii.json: {len(comisii)} comisii, "
          f"{sum(c['n_membri'] for c in comisii)} locuri, {len(sen_to_com)} senatori distincți", flush=True)
    return {"comisii": len(comisii), "senatori": len(sen_to_com)}


if __name__ == "__main__":
    main()
