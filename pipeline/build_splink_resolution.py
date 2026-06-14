"""Rezoluție probabilistică de entități cu SPLINK (pe DuckDB) — benchmark + perechi de revizuit.

Gold-ul nostru rezolvă pe nume + dată naștere (MP) + context-instituție (union-find heuristic). Splink
adaugă un model PROBABILISTIC: estimează ponderi (EM) pe comparații multi-câmp (nume Jaro-Winkler +
dată naștere exact + organizație + județ), produce o probabilitate de match per pereche, clusterizează.

Limită onestă: fără CNP + dată naștere doar la ~329 MP → puterea reală e pe subsetul cu features.
Output data/v1/graf/splink_review.json (perechi în banda de incertitudine = candidați de revizuit/merge)
+ comparație nr. clustere splink vs gold. Mențiuni brute reconstruite din surse (ca build_gold).
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "packages", "solomonar_core"))
from solomonar_core.names import name_key  # noqa: E402

V = os.path.join(ROOT, "data/v1")


def _load(p):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return {}


def _rows(d, *keys):
    for k in keys:
        v = d.get(k)
        if isinstance(v, list):
            return v
        if isinstance(v, dict):
            return list(v.values())
    return []


def _split_name(nume):
    """Surname (primul token, de obicei majuscule) + forenames (restul). Aproximativ pt. RO."""
    toks = [t for t in re.split(r"[\s\-]+", (nume or "").strip()) if t]
    if not toks:
        return "", ""
    return toks[0].lower(), " ".join(toks[1:]).lower()


def _mentions():
    """Reconstruiește mențiunile brute (un rând = o apariție) cu features pt. splink."""
    m = []

    def add(nume, birth=None, org=None, judet=None, src=""):
        nk = name_key(nume)
        if not nk or len(nk.split()) < 2:
            return
        sn, fn = _split_name(nume)
        m.append({"unique_id": len(m), "nume_key": nk, "surname": sn, "forename": fn,
                  "birth_date": (birth or "")[:10] or None, "org": (org or "").lower()[:60] or None,
                  "judet": (judet or "").lower() or None, "src": src})

    # parlamentari (dată naștere + județ)
    for fn, k, pcol in [("parlament/deputati.json", "deputati", "current_party"),
                        ("parlament/senatori.json", "senatori", "party")]:
        for r in _rows(_load(os.path.join(V, fn)), "data", k):
            add(r.get("name", ""), r.get("birth_date"), str(r.get(pcol) or ""), r.get("judet"), "parlament")
    # reprezentanți (companie)
    cidx = {c["cui"]: c for c in _rows(_load(os.path.join(V, "companii/_index.json")), "data")}
    for c in _rows(_load(os.path.join(V, "companii/reprezentanti.json")), "companii"):
        co = cidx.get(c["cui"], {})
        for rp in c.get("reprezentanti", []):
            add(rp["nume"], None, co.get("name", c.get("denumire", "")), co.get("county"), "rep")
    # declarații (instituție)
    for f in glob.glob(os.path.join(V, "declaratii/avere_*.json")):
        if os.path.basename(f).startswith("_"):
            continue
        for d in _load(f).get("declaratii", []):
            if d.get("nume"):
                add(d["nume"], None, d.get("institutie"), None, "declaratie")
    return m


def main() -> dict:
    import pandas as pd
    from splink import DuckDBAPI, Linker, SettingsCreator, block_on
    import splink.comparison_library as cl

    df = pd.DataFrame(_mentions())
    print(f"mențiuni: {len(df)}", flush=True)

    settings = SettingsCreator(
        link_type="dedupe_only",
        blocking_rules_to_generate_predictions=[
            block_on("surname", "substr(forename,1,3)"),
            block_on("birth_date"),
            block_on("org"),
        ],
        comparisons=[
            cl.ForenameSurnameComparison("forename", "surname"),
            cl.DateOfBirthComparison("birth_date", input_is_string=True,
                                     datetime_thresholds=[1, 1], datetime_metrics=["month", "year"]),
            cl.ExactMatch("org").configure(term_frequency_adjustments=True),
            cl.ExactMatch("judet"),
        ],
        retain_intermediate_calculation_columns=True,
        additional_columns_to_retain=["nume_key", "src"],
    )
    linker = Linker(df, settings, db_api=DuckDBAPI())

    # estimare parametri
    linker.training.estimate_probability_two_random_records_match(
        [block_on("birth_date"), block_on("surname", "forename")], recall=0.7)
    linker.training.estimate_u_using_random_sampling(max_pairs=2e6)
    for br in [block_on("surname", "substr(forename,1,3)"), block_on("org")]:
        try:
            linker.training.estimate_parameters_using_expectation_maximisation(br)
        except Exception as e:
            print(f"   EM skip ({type(e).__name__})", flush=True)

    preds = linker.inference.predict(threshold_match_probability=0.5)
    pdf = preds.as_pandas_dataframe()
    print(f"perechi peste 0.5: {len(pdf)}", flush=True)

    # clusterizare la prag 0.9
    clusters = linker.clustering.cluster_pairwise_predictions_at_threshold(preds, threshold_match_probability=0.9)
    cdf = clusters.as_pandas_dataframe()
    n_clusters = cdf["cluster_id"].nunique()
    gold = _load(os.path.join(V, "graf/persoane_gold.json")).get("total_persoane", 0)

    # perechi de revizuit: bandă de incertitudine (0.5-0.95), cross-source (rep↔declarație etc.)
    review = pdf[(pdf["match_probability"] >= 0.5) & (pdf["match_probability"] < 0.95)].copy()
    review = review.sort_values("match_probability", ascending=False).head(500)
    rev = [{"nume_l": r.get("nume_key_l"), "nume_r": r.get("nume_key_r"),
            "prob": round(float(r["match_probability"]), 4),
            "org_l": r.get("org_l"), "org_r": r.get("org_r"),
            "src_l": r.get("src_l"), "src_r": r.get("src_r")}
           for _, r in review.iterrows()]

    os.makedirs(os.path.join(V, "graf"), exist_ok=True)
    json.dump({"nota": "Rezoluție probabilistică SPLINK (DuckDB). 'review' = perechi în banda de "
               "incertitudine (prob 0.5-0.95) = candidați de verificat/merge manual. Model EM pe "
               "nume(Jaro-Winkler)+dată naștere+organizație+județ. Fără CNP → puterea e pe rândurile cu features.",
               "mentiuni": len(df), "perechi_match_0.5+": len(pdf),
               "clustere_splink_0.9": int(n_clusters), "persoane_gold": gold,
               "review_pairs": rev},
              open(os.path.join(V, "graf/splink_review.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"PUBLICAT splink_review.json: {len(df)} mențiuni → {n_clusters} clustere splink "
          f"(gold={gold}) | {len(rev)} perechi de revizuit", flush=True)
    return {"clustere": int(n_clusters), "review": len(rev)}


if __name__ == "__main__":
    main()
