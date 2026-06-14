"""Integrează metadatele ANI central (portal vechi) în graf — fără a re-rula build_gold (păstrează splink).

(1) Publică data/v1/declaratii/ani_central.json — index curat de metadate (nume, instituție, funcție,
    an, tip), 0 PII (nu există CNP în metadate).
(2) Post-process pe persoane_gold.json: adaugă câmpul 'ani_central' {n, ani, functii} persoanelor care
    se potrivesc pe nume (cross-validare: cine are declarații pe portalul central + ce funcții/ani).

Rulează DUPĂ build_gold + build_splink_apply. Apoi rebuild search.
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "packages", "romega_core"))
from romega_core.names import name_key  # noqa: E402

V = os.path.join(ROOT, "data/v1")


def _an(s):
    s = str(s or "")
    for tok in s.replace("-", ".").replace("/", ".").split("."):
        if len(tok) == 4 and tok.isdigit() and tok.startswith("20"):
            return tok
    return s[-4:] if s[-4:].isdigit() else None


def main() -> dict:
    raw = json.load(open(os.path.join(V, "declaratii/_ani_index.json"), encoding="utf-8"))
    recs = raw.get("records", [])

    # 1. index public curat (metadate, fără câmpuri interne)
    clean = [{"nume": r.get("nume"), "institutie": r.get("institutie"), "functie": r.get("functie"),
              "judet": r.get("judet"), "an": _an(r.get("data_completare")), "tip": r.get("tip_declaratie")}
             for r in recs if r.get("nume")]
    json.dump({"sursa": "old-declaratii.integritate.eu (ANI central, portal vechi, fără captcha)",
               "nota": "Metadate declarații de avere/interese (FĂRĂ PII/CNP). Arhivă 2008-2023; "
               "publicarea nouă oprită prin decizia CCR 297/2025. Acoperire: parlamentari (țintit pe nume).",
               "total": len(clean), "declaratii": clean},
              open(os.path.join(V, "declaratii/ani_central.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    # 2. sumar per nume_key (n, ani, funcții)
    by_nk = defaultdict(lambda: {"n": 0, "ani": set(), "functii": set(), "institutii": set()})
    for r in recs:
        nk = name_key(r.get("nume", ""))
        if not nk:
            continue
        s = by_nk[nk]
        s["n"] += 1
        if _an(r.get("data_completare")):
            s["ani"].add(_an(r.get("data_completare")))
        if r.get("functie"):
            s["functii"].add(str(r["functie"])[:50])
        if r.get("institutie"):
            s["institutii"].add(str(r["institutie"])[:50])

    # 3. patch pe persoane_gold (post-splink, NU re-rula build_gold)
    gp = os.path.join(V, "graf/persoane_gold.json")
    g = json.load(open(gp, encoding="utf-8"))
    patched = 0
    for p in g.get("persoane", []):
        s = by_nk.get(p.get("nume_key"))
        if s:
            p["ani_central"] = {"n": s["n"], "ani": sorted(s["ani"]),
                                "functii": sorted(s["functii"])[:5], "institutii": sorted(s["institutii"])[:5]}
            patched += 1
    g["cu_ani_central"] = patched
    json.dump(g, open(gp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    print(f"PUBLICAT ani_central.json: {len(clean)} metadate | persoane patch-uite cu ani_central: {patched} "
          f"| nume distincte ANI: {len(by_nk)}", flush=True)
    return {"metadate": len(clean), "patched": patched}


if __name__ == "__main__":
    main()
