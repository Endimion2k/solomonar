"""Activitate recentă a comisiilor (ultima lună) — ședințe + PLx discutate + actele de bază.

Citește comisii/sedinte.json + plx.json + comisii.json și produce activitate_recenta.json:
ședințele din ultimele ~30 de zile, grupate, cu PLx-urile discutate și documentele care au stat
la baza lor (forma inițiatorului, expunere de motive, aviz Consiliul Legislativ, punct de vedere Guvern).
"""

from __future__ import annotations

import datetime
import json
import os
import re
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V = os.path.join(ROOT, "data/v1/comisii")
ZILE = int(os.environ.get("COMISII_RECENT_ZILE", "30"))

# documentele „de bază" ale unui PLx (ce a stat la baza lui), în ordinea relevanței
ACTE_BAZA = ["forma_initiator", "expunere_motive", "aviz_consiliu_legislativ",
             "punct_vedere_guvern", "sesizare"]
TIP_LABEL = {"forma_initiator": "forma inițiatorului", "expunere_motive": "expunere de motive",
             "aviz_consiliu_legislativ": "aviz Consiliul Legislativ", "punct_vedere_guvern": "punct de vedere Guvern",
             "sesizare": "sesizare", "raport": "raport", "aviz_comisie": "aviz comisie",
             "raport_suplimentar": "raport suplimentar", "aviz_csm": "aviz CSM", "alt": "alt document"}


def _load(p):
    return json.load(open(os.path.join(V, p), encoding="utf-8"))


_LUNI = {"ian": 1, "feb": 2, "mar": 3, "apr": 4, "mai": 5, "iun": 6, "iul": 7, "aug": 8,
         "sep": 9, "oct": 10, "noi": 11, "nov": 11, "dec": 12}


def _iso(an, luna, zi):
    try:
        return datetime.date(int(an), int(luna), int(zi)).isoformat()
    except (TypeError, ValueError):
        return None


def _eff_date(s):
    """Data ședinței: câmpul `data` sau, dacă lipsește, extrasă din numele PDF-ului agendei.

    Formate recunoscute (doar cele fără ambiguitate): DD.MM.YYYY, YYYY-MM-DD, „2 sept 2025”,
    „oz18mai” / „OZ 10.06” (anul din câmpul `an`). „oz0204” sau „oz100508” rămân fără dată:
    nu se știe dacă e zi-lună sau lună-zi.
    """
    if s.get("data"):
        return s["data"]
    u = urllib.parse.unquote(s.get("agenda_pdf_url") or "")
    nume = u.rsplit("/", 1)[-1].lower()
    m = re.search(r"(?<!\d)(\d{1,2})[.\-_ ](\d{1,2})[.\-_ ](20\d{2})(?!\d)", nume)
    if m:
        return _iso(m.group(3), m.group(2), m.group(1))
    m = re.search(r"(20\d{2})[.\-_](\d{2})[.\-_](\d{2})(?!\d)", nume)
    if m:
        return _iso(m.group(1), m.group(2), m.group(3))
    an = s.get("an")
    m = re.search(r"(?<!\d)(\d{1,2})\s*(ian|feb|mar|apr|mai|iun|iul|aug|sep|oct|noi|nov|dec)[a-zăâîșțş]*"
                  r"(?:\s*(20\d{2}))?", nume)
    if m and (m.group(3) or an):
        return _iso(m.group(3) or an, _LUNI[m.group(2)], m.group(1))
    m = re.search(r"(?<!\d)(\d{1,2})\.(\d{1,2})(?!\d)(?!\.\d)", nume)
    if m and an:
        return _iso(an, m.group(2), m.group(1))
    return None


def main() -> dict:
    comisii = {c["tip"]: c["nume"] for c in _load("comisii.json").get("comisii", [])}
    plx_by_idp = {p["idp"]: p for p in _load("plx.json").get("plx", [])}
    sedinte = _load("sedinte.json").get("sedinte", [])

    for s in sedinte:
        s["_d"] = _eff_date(s)
    dated = [s for s in sedinte if s["_d"]]
    if not dated:
        raise RuntimeError("nicio ședință cu dată")
    # ancoră = azi (sau ultima dată din date, dacă e în viitor evităm); fereastră ZILE
    today = datetime.date.today().isoformat()
    max_d = max((s["_d"] for s in dated if s["_d"] <= today), default=max(s["_d"] for s in dated))
    cutoff = (datetime.date.fromisoformat(max_d) - datetime.timedelta(days=ZILE)).isoformat()
    inrange = [s for s in dated if cutoff <= s["_d"] <= max_d]
    # contopește ședințele aceleiași comisii din aceeași zi (agende-interval suprapuse) — uniune PLx
    merged: dict = {}
    for s in inrange:
        m = merged.setdefault((s["tip"], s["_d"]),
                              {"tip": s["tip"], "_d": s["_d"],
                               "agenda_pdf_url": s.get("agenda_pdf_url"), "plx_idps": set()})
        m["plx_idps"].update(s.get("plx_idps", []))
    for m in merged.values():
        m["plx_idps"] = sorted(m["plx_idps"], key=lambda x: int(x) if str(x).isdigit() else 0)
    recent = sorted(merged.values(), key=lambda s: s["_d"], reverse=True)

    def _plx_view(idp):
        p = plx_by_idp.get(idp)
        if not p:
            return {"idp": idp, "titlu": f"PLx idp {idp}", "url": None, "acte_baza": [], "n_documente": 0}
        docs = p.get("documente", [])
        acte = [{"tip": TIP_LABEL.get(d["tip"], d["tip"]), "url": d["url"]}
                for d in docs if d.get("tip") in ACTE_BAZA]
        return {
            "idp": idp, "titlu": p.get("titlu") or f"PLx idp {idp}",
            "url": f"https://www.cdep.ro/ords/pls/proiecte/upl_pck2015.proiect?cam=2&idp={idp}",
            "acte_baza": acte, "n_documente": len(docs)}

    sed_out, plx_unice = [], {}
    for s in recent:
        plx = [_plx_view(i) for i in s.get("plx_idps", [])]
        sed_out.append({
            "comisie": comisii.get(s["tip"], f"comisie tip {s['tip']}"), "tip": s["tip"],
            "data": s["_d"], "agenda_url": s.get("agenda_pdf_url"),
            "n_plx": len(plx), "plx": plx})
        for pv in plx:
            u = plx_unice.setdefault(pv["idp"], {**pv, "comisii": set()})
            u["comisii"].add(comisii.get(s["tip"], f"tip {s['tip']}"))

    plx_list = sorted(plx_unice.values(), key=lambda x: -x["n_documente"])
    for u in plx_list:
        u["comisii"] = sorted(u["comisii"])

    out = {
        "generat": datetime.date.today().isoformat(),
        "perioada": {"de_la": cutoff, "pana_la": max_d, "zile": ZILE},
        "n_sedinte": len(sed_out),
        "n_comisii_active": len({s["tip"] for s in recent}),
        "n_plx_unice": len(plx_list),
        "sedinte": sed_out,
        "plx_unice": plx_list,
    }
    json.dump(out, open(os.path.join(V, "activitate_recenta.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    # tot istoricul, pentru filtrul pe comisie + perioadă din aplicație. Ședințele fără dată exactă
    # rămân cu `data: null` și anul agendei; aplicația le arată doar la cerere.
    toate: dict = {}
    for s in sedinte:
        k = (s["tip"], s["_d"]) if s["_d"] else (s["tip"], None, s.get("agenda_pdf_url"))
        m = toate.setdefault(k, {"tip": s["tip"], "_d": s["_d"], "an": s.get("an"),
                                 "agenda_pdf_url": s.get("agenda_pdf_url"), "plx_idps": set()})
        m["plx_idps"].update(s.get("plx_idps", []))
    ist = []
    for s in sorted(toate.values(), key=lambda s: (s["_d"] or f"{s['an']}-00-00"), reverse=True):
        idps = sorted(s["plx_idps"], key=lambda x: int(x) if str(x).isdigit() else 0)
        ist.append({"comisie": comisii.get(s["tip"], f"comisie tip {s['tip']}"), "tip": s["tip"],
                    "data": s["_d"], "an": int(s["_d"][:4]) if s["_d"] else s["an"],
                    "agenda_url": s.get("agenda_pdf_url"), "n_plx": len(idps), "plx": [_plx_view(i) for i in idps]})
    zile = [s["data"] for s in ist if s["data"]]
    json.dump({"generat": out["generat"], "perioada": {"de_la": min(zile), "pana_la": max(zile)},
               "n_sedinte": len(ist), "n_fara_data": sum(1 for s in ist if not s["data"]), "sedinte": ist},
              open(os.path.join(V, "activitate.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    out["n_istoric"] = len(ist)
    return out


if __name__ == "__main__":
    r = main()
    print(f"OK -> activitate_recenta.json | perioada {r['perioada']['de_la']} → {r['perioada']['pana_la']}")
    print(f"  ședințe: {r['n_sedinte']} | comisii active: {r['n_comisii_active']} | PLx unice: {r['n_plx_unice']}")
    print("=== ședințe recente (top 6) ===")
    for s in r["sedinte"][:6]:
        print(f"  {s['data']} · {s['comisie'][:45]:45} · {s['n_plx']} PLx")
