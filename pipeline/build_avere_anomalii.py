"""Anomalii de avere (PyOD/ECOD) pe declarațiile de avere SOLOMONAR.

Vector per declarație: venituri, conturi, datorii, terenuri, clădiri, auto (deja extrase în
avere_*.json). ECOD (parameter-free, interpretabil) marchează profilurile STATISTIC neobișnuite
față de restul + dimensiunea care „trage" scorul. Lead-uri de verificat, NU acuzații de îmbogățire.

Output: data/v1/avere_anomalii.json (top profiluri anormale, cu scor + driver).
"""

from __future__ import annotations

import glob
import json
import os
import re
import time

import numpy as np
from pyod.models.ecod import ECOD

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V = os.path.join(ROOT, "data/v1")

FEATS = ["venituri_ron", "conturi_ron", "datorii_ron", "terenuri", "cladiri", "auto"]
FEAT_LBL = {"venituri_ron": "venituri", "conturi_ron": "conturi", "datorii_ron": "datorii",
            "terenuri": "terenuri", "cladiri": "clădiri", "auto": "auto"}
TOP = 1500


def _an(url: str):
    m = re.search(r"/(20\d\d)/", url or "")
    return int(m.group(1)) if m else None


def _real_name(n: str) -> bool:
    """Filtrează nume-garbage din OCR prost (ex. 'Cbf Beb Bb Fb Df Bc')."""
    toks = [t for t in re.split(r"\s+", n or "") if t]
    return len(toks) >= 2 and any(
        len(t) >= 4 and re.search(r"[aeiouăâî]", t.lower()) for t in toks)


def main() -> dict:
    rows = []
    for f in glob.glob(os.path.join(V, "declaratii", "avere_*.json")):
        src = os.path.basename(f).split("avere_")[1][:-5]
        d = json.load(open(f, encoding="utf-8"))
        arr = d if isinstance(d, list) else (d.get("declaratii") or d.get("data") or [])
        for r in arr:
            if not any(isinstance(r.get(k), (int, float)) and r.get(k) for k in FEATS):
                continue
            rows.append({
                "nume": (r.get("nume") or "").title(),
                "nume_norm": r.get("nume_norm") or "",
                "institutie": (r.get("institutie") or "")[:80], "src": src,
                "an": _an(r.get("pdf_url")),
                **{k: float(r.get(k) or 0) for k in FEATS},
            })

    # dedup: cea mai recentă declarație per persoană (nume_norm)
    latest = {}
    for r in rows:
        key = r["nume_norm"] or (r["nume"] + "|" + r["institutie"])
        if key not in latest or (r["an"] or 0) > (latest[key]["an"] or 0):
            latest[key] = r
    rows = list(latest.values())

    X = np.array([[r[k] for k in FEATS] for r in rows], dtype=float)
    clf = ECOD()
    clf.fit(X)
    scores = clf.decision_scores_
    O = getattr(clf, "O", None)  # contribuția per-dimensiune (n, d)

    # normalizează scorul 0-100 pentru afișare
    smin, smax = float(scores.min()), float(scores.max())
    rng = (smax - smin) or 1.0
    for i, r in enumerate(rows):
        r["scor"] = round((scores[i] - smin) / rng * 100, 1)
        if O is not None:
            drv = int(np.argmax(O[i]))
            r["driver"] = FEAT_LBL.get(FEATS[drv], FEATS[drv])
        else:
            r["driver"] = ""

    rows.sort(key=lambda r: r["scor"], reverse=True)
    top = []
    for r in rows:
        if len(top) >= TOP:
            break
        if not _real_name(r["nume"]):    # sare peste nume-garbage din OCR
            continue
        top.append({
            "nume": r["nume"], "institutie": r["institutie"], "an": r["an"], "sursa": r["src"],
            "scor": r["scor"], "driver": r["driver"],
            "venituri_ron": round(r["venituri_ron"]), "conturi_ron": round(r["conturi_ron"]),
            "datorii_ron": round(r["datorii_ron"]), "terenuri": int(r["terenuri"]),
            "cladiri": int(r["cladiri"]), "auto": int(r["auto"]),
        })

    out = {
        "generat": time.strftime("%Y-%m-%d"),
        "metoda": "PyOD ECOD (empirical CDF, parameter-free) pe [venituri, conturi, datorii, terenuri, clădiri, auto]",
        "disclaimer": "Scorul = cât de NEOBIȘNUIT statistic e profilul declarat față de restul (nu dovadă "
                      "de îmbogățire ilicită). Poate fi și artefact de extragere (numărări imperfecte). "
                      "Lead de verificat manual în declarația originală.",
        "n_persoane": len(rows),
        "items": top,
    }
    json.dump(out, open(os.path.join(V, "avere_anomalii.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    return out


if __name__ == "__main__":
    r = main()
    print(f"OK -> data/v1/avere_anomalii.json | {r['n_persoane']} persoane, top {len(r['items'])}")
    print("=== TOP 6 profiluri anormale ===")
    for x in r["items"][:6]:
        print(f"  scor {x['scor']:5} | drv:{x['driver']:8} | {x['nume'][:26]:26} | "
              f"venit {x['venituri_ron']:>12,} conturi {x['conturi_ron']:>12,} "
              f"ter {x['terenuri']} cl {x['cladiri']} auto {x['auto']}")
