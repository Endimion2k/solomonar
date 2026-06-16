"""Changelog SOLOMONAR — diff între rebuild-uri (deepdiff) pentru monitorizare.

Compară un digest compact al persoanelor (contracte, companii, declarații) cu snapshot-ul de la
rebuild-ul anterior și scrie data/v1/changelog.json (persoane noi + modificări de valori).
Primul rulaj: doar salvează baza (changelog gol). Snapshot-ul anterior stă în _local/ (gitignored).
"""

from __future__ import annotations

import datetime
import json
import os
import re

from deepdiff import DeepDiff

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V = os.path.join(ROOT, "data/v1")
SNAP = os.path.join(ROOT, "_local", "changelog_snapshot.json")

CAMP_LABEL = {"contracte_ron": "contracte de stat (lei)", "n_companii": "companii conduse",
              "n_declaratii": "declarații"}


def _digest() -> dict:
    ps = json.load(open(os.path.join(V, "graf/persoane_gold.json"), encoding="utf-8")).get("persoane", [])
    out = {}
    for p in ps:
        rid = p.get("romega_id")
        if not rid:
            continue
        out[rid] = {
            "nume": (p.get("nume_key") or "").title(),
            "contracte_ron": round(p.get("total_contracte_ron") or 0),
            "n_companii": int(p.get("n_companii") or 0),
            "n_declaratii": int(p.get("n_declaratii") or 0),
        }
    return out


def _parse_path(path: str):
    """root['<rid>']['<camp>'] -> (rid, camp)."""
    keys = re.findall(r"\['([^']*)'\]", path)
    return (keys[0] if keys else None, keys[1] if len(keys) > 1 else None)


def main() -> dict:
    cur = _digest()
    prev = None
    if os.path.exists(SNAP):
        try:
            prev = json.load(open(SNAP, encoding="utf-8"))
        except Exception:
            prev = None

    persoane_noi, modificari = [], []
    if prev:
        dd = DeepDiff(prev, cur, ignore_order=True)
        for path in dd.get("dictionary_item_added", []):
            rid, _ = _parse_path(path)
            if rid and rid in cur and cur[rid].get("contracte_ron", 0) > 0:
                persoane_noi.append({"romega_id": rid, **cur[rid]})
        for path, ch in dd.get("values_changed", {}).items():
            rid, camp = _parse_path(path)
            if not rid or camp not in CAMP_LABEL:
                continue
            modificari.append({
                "romega_id": rid, "nume": cur.get(rid, {}).get("nume"),
                "camp": CAMP_LABEL.get(camp, camp),
                "vechi": ch.get("old_value"), "nou": ch.get("new_value"),
                "delta": (ch.get("new_value") or 0) - (ch.get("old_value") or 0),
            })
        modificari.sort(key=lambda m: abs(m.get("delta") or 0), reverse=True)

    out = {
        "generat": datetime.date.today().isoformat(),
        "are_baza_anterioara": prev is not None,
        "n_persoane_monitorizate": len(cur),
        "n_persoane_noi": len(persoane_noi),
        "n_modificari": len(modificari),
        "persoane_noi": persoane_noi[:200],
        "modificari": modificari[:500],
    }
    os.makedirs(os.path.dirname(SNAP), exist_ok=True)
    json.dump(out, open(os.path.join(V, "changelog.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    json.dump(cur, open(SNAP, "w", encoding="utf-8"), ensure_ascii=False)
    return out


if __name__ == "__main__":
    r = main()
    print("OK -> data/v1/changelog.json")
    print(f"  monitorizate: {r['n_persoane_monitorizate']} persoane | "
          f"bază anterioară: {r['are_baza_anterioara']}")
    print(f"  persoane noi cu bani: {r['n_persoane_noi']} | modificări: {r['n_modificari']}")
