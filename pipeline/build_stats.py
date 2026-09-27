"""Statistici globale + starea publicării: data/v1/stats.json și data/v1/status.json.

Ambele fișiere nu aveau producător: stats.json (KPI-urile din Overview) era actualizat manual, iar
status.json (pagina publică web/index.html) rămăsese la bootstrap-ul din 2026-06-01 („7 companii”).
Acest pas le recalculează din fișierele publicate; rulează la FINALUL refresh-ului.

- stats.json: aceleași chei ca înainte (compatibil cu Overview / search.html), recalculate; o secțiune
  al cărei fișier-sursă lipsește își păstrează valoarea anterioară.
- status.json: generated_at, colecțiile afișate pe pagina publică + `surse`: data generării fiecărui
  fișier din data/v1 (câmp generated_at/generat, altfel data ultimei modificări) — pentru prospețime.

    python -m pipeline.build_stats
"""

from __future__ import annotations

import collections
import json
import os
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V = os.path.join(ROOT, "data", "v1")


def _load(rel: str):
    p = os.path.join(V, rel)
    if not os.path.exists(p):
        return None
    try:
        return json.load(open(p, encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _rows(d, *keys):
    if isinstance(d, list):
        return d
    for k in keys:
        if isinstance((d or {}).get(k), list):
            return d[k]
    return []


def _generated(rel: str) -> str:
    d = _load(rel)
    if isinstance(d, dict):
        for k in ("generated_at", "generat", "generated"):
            if isinstance(d.get(k), str):
                return d[k][:19]
        meta = d.get("meta") if isinstance(d.get("meta"), dict) else {}
        if isinstance(meta.get("generated_at"), str):
            return meta["generated_at"][:19]
    ts = os.path.getmtime(os.path.join(V, rel))
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()[:19] + " (mtime)"


def build_stats(prev: dict) -> dict:
    s = dict(prev)
    s["generat"] = datetime.now(timezone.utc).isoformat()

    def section(name, fn):
        try:
            val = fn()
            if val is not None:
                s[name] = val
        except Exception as e:  # o secțiune stricată nu oprește restul
            print(f"   [stats] {name}: păstrez valoarea anterioară ({type(e).__name__}: {e})")

    def decl():
        files = os.listdir(os.path.join(V, "declaratii"))
        n = lambda pref: sum(len(_rows(_load(f"declaratii/{f}"), "declaratii"))   # noqa: E731
                             for f in files if f.startswith(pref) and f.endswith(".json"))
        av, it = n("avere_"), n("interese_")
        return {"total": av + it, "avere": av, "interese": it} if av else None
    section("declaratii", decl)

    def comp():
        cs = _rows(_load("companii/_index.json"), "data")
        return {"total": len(cs), "cu_reprezentanti": sum(1 for c in cs if c.get("legal_reps")),
                "cu_bilant": sum(1 for c in cs if c.get("financials"))} if cs else None
    section("companii_stat", comp)

    def cvs():
        soe = len(_rows(_load("companii/cv.json"), "cv"))
        dep = len(_rows(_load("companii/cv_parlament.json"), "cv"))
        sen = len(_rows(_load("companii/cv_senatori.json"), "cv"))
        return {"total": soe + dep + sen, "soe_institutii": soe, "deputati": dep, "senatori": sen}
    section("cv_uri", cvs)

    def gold():
        g = _load("graf/persoane_gold.json") or {}
        rz = _load("graf/rezolutie_stats.json") or {}
        return {**(prev.get("gold") or {}), "persoane_canonice": g.get("total_persoane"),
                "parlamentari": g.get("parlamentari"), "incredere": g.get("incredere"),
                "cross_links_total": rz.get("cross_links_total"),
                "cross_links_confirmate": rz.get("cross_links_confirmate")} if g else None
    section("gold", gold)

    def comisii():
        p = _load("comisii/plx.json") or {}
        return {"plx": p.get("total"), "documente": p.get("total_documente")} if p else None
    section("comisii_cdep", comisii)
    section("motiuni", lambda: (_load("parlament/motiuni.json") or {}).get("total"))

    def partide():
        p = _rows(_load("partide/partide.json"), "partide")
        sub = _rows(_load("partide/subventii.json"), "subventii")
        rvc = _rows(_load("partide/rapoarte_rvc.json"), "data")
        top = sorted(((x.get("cod"), x.get("total_subventie_lei") or 0) for x in p), key=lambda t: -t[1])[:5]
        return {"total": len(p), "subventii_inreg": len(sub), "rapoarte_rvc": len(rvc),
                "subventie_totala_top": dict(top)} if p else None
    section("partide", partide)
    section("bugete", lambda: {"uat_inreg": len(_rows(_load("bugete/uat.json"))),
                               "bgc_luni": len(_rows(_load("bugete/bgc.json")))})

    def achiz():
        ad = _load("companii/achizitii_directe.json") or {}
        cf = _rows(_load("achizitii/contracte_firme.json"), "firme")
        ftm = _load("graf/follow_the_money.json") or {}
        return {**(prev.get("achizitii") or {}), "firme_castigatoare": len(cf),
                "follow_the_money_leaduri": ftm.get("total_leaduri"),
                "confirmate_autodeclarate": (ftm.get("CONFIRMATE_autodeclarate")
                                             if isinstance(ftm.get("CONFIRMATE_autodeclarate"), int)
                                             else len(ftm.get("confirmate") or [])),
                "achizitii_directe_total": ad.get("total_achizitii"), "furnizori_directe": ad.get("total_furnizori"),
                "valoare_directe_mld": round((ad.get("valoare_totala_ron") or 0) / 1e9, 1)}
    section("achizitii", achiz)

    def audit():
        dna = _rows(_load("audit/dna.json"), "data")
        cc = _rows(_load("audit/curtea_de_conturi.json"), "data")
        return {"dna_comunicate": len(dna), "dna_ro": sum(1 for x in dna if x.get("limba", "ro") == "ro"),
                "curtea_de_conturi": len(cc)}
    section("audit", audit)
    section("legislatie", lambda: {"acte_esantion": len(_rows(_load("legislatie/index.json"), "acte"))})

    def senat():
        c = _load("comisii/senat_comisii.json") or {}
        return {**(prev.get("comisii_senat") or {}), "comisii": c.get("total_comisii"),
                "locuri": c.get("total_locuri")} if c else None
    section("comisii_senat", senat)

    def bvb():
        b = _load("companii/actionariat_bvb.json") or {}
        return {**(prev.get("actionariat") or {}), "companii_listate": b.get("total"),
                "cu_participatie_stat": b.get("cu_participatie_stat")} if b else None
    section("actionariat", bvb)
    section("search", lambda: {"entitati": (_load("search/index.json") or {}).get("total")})

    def plx():
        p = _load("comisii/plx_initiatori.json") or {}
        return {**(prev.get("legislativ") or {}), "plx": p.get("total_plx"),
                "plx_cu_initiatori_parlamentari": p.get("cu_initiatori_parlamentari"),
                "plx_guvern": p.get("guvern_initiator"),
                "legislatie_acte": (_load("legislatie/index.json") or {}).get("total")} if p else None
    section("legislativ", plx)

    def sanct():
        o = _load("sanctiuni_ro.json") or {}
        cnt = lambda k: len(o[k]) if isinstance(o.get(k), list) else o.get(k)
        return {"entitati_ro": cnt("entitati") or o.get("total"), "sanctiuni": cnt("sanctiuni"),
                "pep": cnt("pep"), "in_graf": cnt("in_graf")} if o else None
    section("opensanctions", sanct)

    def onrc():
        f = _load("companii/firme_onrc.json") or {}
        return {**(prev.get("firme_onrc") or {}), "total": f.get("total"), "cu_caen": f.get("cu_caen")} if f else None
    section("firme_onrc", onrc)

    def alerte():
        a = _load("alerte.json") or {}
        return {"total": a.get("total"), "pe_tip": a.get("pe_tip")} if a else None
    section("alerte", alerte)

    def reps():
        r = _load("companii/reprezentanti.json") or {}
        return {"companii_cu_reps": r.get("companii_cu_reprezentanti"),
                "total_reps": r.get("total_reprezentanti")} if r else None
    section("reprezentanti", reps)

    def guv():
        g = _load("guvernanta/registry.json") or {}
        return {"companii": g.get("n_companii"), "numiri": g.get("n_numiri"), "persoane": g.get("n_persoane"),
                "potrivite_graf": g.get("n_potrivite"), "cumul": len(g.get("cumul") or []),
                "sursa_generata": g.get("source_generated_at")} if g else None
    section("guvernanta", guv)
    return s


def build_status() -> dict:
    orgs = _rows(_load("organizatii/_index.json"), "data")
    tiers = collections.Counter(o.get("tier") for o in orgs)
    graph = _load("graf/graph_full.json") or {}
    gold = _load("graf/persoane_gold.json") or {}
    files = sorted(os.path.relpath(os.path.join(dp, f), V).replace(os.sep, "/")
                   for dp, _, fs in os.walk(V) for f in fs if f.endswith(".json") and not f.startswith("~$"))
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "version": "0.2.0",
        "collections": {
            "organizatii": len(orgs),
            "organizatii_centrale": tiers.get("central", 0) + tiers.get("parliament", 0) + tiers.get("subordinated", 0),
            "organizatii_deconcentrate": tiers.get("deconcentrated", 0),
            "organizatii_locale": tiers.get("local_autonomy", 0),
            "companii": len(_rows(_load("companii/_index.json"), "data")),
            "persoane": gold.get("total_persoane"),
            "graph_edges": graph.get("n_links") or len(graph.get("links") or []),
        },
        "surse": {f: _generated(f) for f in files if f not in ("status.json", "stats.json")},
    }


def main() -> dict:
    stats = build_stats(_load("stats.json") or {})
    status = build_status()
    for name, obj in (("stats.json", stats), ("status.json", status)):
        with open(os.path.join(V, name), "w", encoding="utf-8", newline="\n") as fh:
            json.dump(obj, fh, ensure_ascii=False, indent=2)
    print(f"PUBLICAT stats.json + status.json: {status['collections']} | {len(status['surse'])} fișiere datate",
          flush=True)
    return status


if __name__ == "__main__":
    main()
