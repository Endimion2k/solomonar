"""Aplică DOAR merge-urile SIGURE din SPLINK pe graful gold — colapsează duplicatele OCR/format.

Splink (build_splink_resolution.py) produce o bandă de perechi de revizuit (splink_review.json:
review_pairs). Multe sunt false-merge (ex. 'chira daniel' ≠ 'chioreanu daniela', deși prob 0.95):
nume cu tokeni DIFERIȚI, scor mare din coincidența organizației + Jaro-Winkler. Acest script
aplică NUMAI merge-urile pe care le putem garanta conservator.

REGULĂ DE SIGURANȚĂ (toate condițiile, simultan):
  1. set-ul de tokeni al UNUI nume_key e SUBSET STRICT al celuilalt
     (ex. {eftene,sorin} ⊂ {cim,eftene,sorin}) — captează prefixe/sufixe OCR adăugate,
     RESPINGE substituții de litere (chira/chioreanu au tokeni diferiți → NU se unesc);
  2. cele două persoane gold au cel puțin UN token de organizație DISTINCTIV comun
     (ex. 'brasov' — nu generice ca 'sa'/'srl'/ani), deci sunt în același context;
  3. prob ≥ 0.9.

Pentru că nume_key NU e unic în gold (un nume_key → mai multe persoane), potrivirea se face la
nivel de PERSOANĂ: pentru fiecare latură a perechii alegem persoanele gold cu acel nume_key, apoi
unim doar perechile de persoane care partajează un token de organizație distinctiv. Asta separă
automat omonimii la orașe diferite (eftene sorin@brasov ≠ eftene sorin@bucuresti).

Perechile sigure → union-find → grupuri. Per grup alegem un romega_id canonic (cele mai multe
legături; tie-break: parlamentar / cu CV / nr. declarații+companii) și MERGE-uim: combinăm
declaratii+companii (dedup), însumăm n_*, păstrăm cea mai bună 'incredere'. Backup întâi în _local/.

NU reconstruiește search/duckdb. NU git commit.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "packages", "romega_core"))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
from build_gold import _distinct_tokens, UF  # noqa: E402  (reuse aceeași normalizare ca gold)

V = os.path.join(ROOT, "data/v1")
GOLD_PATH = os.path.join(V, "graf/persoane_gold.json")
REVIEW_PATH = os.path.join(V, "graf/splink_review.json")
LOCAL = os.path.join(ROOT, "_local")
BACKUP_PATH = os.path.join(LOCAL, "persoane_gold.pre_splink.json")

PROB_MIN = 0.9

# ordine de încredere (mai mare = mai bun) pentru a păstra cel mai bun tag pe grup
INCREDERE_RANK = {"high": 3, "context": 2, "candidat": 1}


def _name_tokens(nk: str) -> frozenset:
    return frozenset(t for t in (nk or "").split() if t)


def _person_org_tokens(p: dict) -> set:
    """Token-uri de organizație DISTINCTIVE ale unei persoane (declarații + companii)."""
    t: set = set()
    for d in p.get("declaratii", []) or []:
        t |= _distinct_tokens(d.get("institutie") or "")
    for c in p.get("companii", []) or []:
        t |= _distinct_tokens(c.get("nume") or "")
    return t


DECL_CAP = 20  # gold stochează declaratii[:20] (vezi build_gold.py)


def _decl_key(d: dict) -> tuple:
    return (d.get("tip"), d.get("institutie"), d.get("venituri_ron"))


def _comp_key(c: dict) -> tuple:
    return (c.get("cui"), (c.get("nume") or "").strip().lower(), c.get("rol"))


def _better_canonical(a: dict, b: dict, deg: dict) -> dict:
    """Alege persoana canonică: mai multe legături; tie-break parlamentar/CV/nr. mențiuni."""

    def score(p):
        return (
            deg.get(p["romega_id"], 0),               # nr. de legături sigure în grup
            1 if p.get("parlamentar") else 0,          # parlamentar = identitate certă
            1 if p.get("are_cv") else 0,               # are dată naștere / CV
            INCREDERE_RANK.get(p.get("incredere"), 0),
            (p.get("n_declaratii", 0) or 0) + (p.get("n_companii", 0) or 0),
        )

    return a if score(a) >= score(b) else b


def main() -> dict:
    gold = json.load(open(GOLD_PATH, encoding="utf-8"))
    review = json.load(open(REVIEW_PATH, encoding="utf-8"))
    pairs = review.get("review_pairs", []) if isinstance(review, dict) else review

    persons = gold["persoane"]
    by_id = {p["romega_id"]: p for p in persons}
    by_name = defaultdict(list)
    for p in persons:
        by_name[p["nume_key"]].append(p)

    n_persons_before = len(persons)

    # --- 1. derivă perechile de persoane SIGURE ---
    safe_person_pairs: set = set()           # frozenset({id_a, id_b})
    n_pairs_passing_rule = 0                 # perechi (nume_l,nume_r) care trec regula nume+prob
    for pr in pairs:
        if float(pr.get("prob", 0)) < PROB_MIN:
            continue
        nl, nr = pr.get("nume_l"), pr.get("nume_r")
        tl, tr = _name_tokens(nl), _name_tokens(nr)
        # SUBSET STRICT (unul e prefix/superset de tokeni al celuilalt), nu egalitate, nu disjuncte
        if not (tl and tr and tl != tr and (tl < tr or tr < tl)):
            continue
        cand_l = by_name.get(nl, [])
        cand_r = by_name.get(nr, [])
        if not cand_l or not cand_r:
            continue
        matched_here = False
        for pl in cand_l:
            otl = _person_org_tokens(pl)
            if not otl:
                continue
            for pra in cand_r:
                if pl["romega_id"] == pra["romega_id"]:
                    continue
                # cel puțin un token de organizație DISTINCTIV comun = același context
                if otl & _person_org_tokens(pra):
                    safe_person_pairs.add(frozenset((pl["romega_id"], pra["romega_id"])))
                    matched_here = True
        if matched_here:
            n_pairs_passing_rule += 1

    # --- 2. union-find pe perechile sigure → grupuri ---
    uf = UF()
    deg: dict = defaultdict(int)
    for pair in safe_person_pairs:
        a, b = tuple(pair)
        uf.union(a, b)
        deg[a] += 1
        deg[b] += 1

    groups = defaultdict(list)
    for pair in safe_person_pairs:
        for rid in pair:
            groups[uf.find(rid)].append(rid)
    # dedup membrii fiecărui grup
    groups = {root: sorted(set(ids)) for root, ids in groups.items()}
    multi_groups = [ids for ids in groups.values() if len(ids) > 1]

    n_groups = len(multi_groups)
    n_collapsed_persons = sum(len(ids) - 1 for ids in multi_groups)  # câți dispar prin merge

    # --- 3. MERGE per grup ---
    drop_ids: set = set()
    for ids in multi_groups:
        members = [by_id[i] for i in ids]
        canon = members[0]
        for m in members[1:]:
            canon = _better_canonical(canon, m, deg)

        # acumulează în canon
        decl_seen = {_decl_key(d) for d in canon.get("declaratii", []) or []}
        comp_seen = {_comp_key(c) for c in canon.get("companii", []) or []}
        firme_seen = {
            (f.get("cui"), (f.get("nume") or "").strip().lower()) if isinstance(f, dict) else f
            for f in (canon.get("firme_contracte_autodeclarate") or [])
        }
        canon.setdefault("merged_from", [])

        for m in members:
            if m["romega_id"] == canon["romega_id"]:
                continue
            for d in m.get("declaratii", []) or []:
                if _decl_key(d) not in decl_seen:
                    decl_seen.add(_decl_key(d))
                    canon.setdefault("declaratii", []).append(d)
            for c in m.get("companii", []) or []:
                if _comp_key(c) not in comp_seen:
                    comp_seen.add(_comp_key(c))
                    canon.setdefault("companii", []).append(c)
            for f in m.get("firme_contracte_autodeclarate") or []:
                fk = (f.get("cui"), (f.get("nume") or "").strip().lower()) if isinstance(f, dict) else f
                if fk not in firme_seen:
                    firme_seen.add(fk)
                    canon.setdefault("firme_contracte_autodeclarate", []).append(f)
            # păstrează un nume_key mai informativ (cel mai lung token-set) dacă e superset
            if len(_name_tokens(m["nume_key"])) > len(_name_tokens(canon["nume_key"])):
                if _name_tokens(canon["nume_key"]) < _name_tokens(m["nume_key"]):
                    canon["nume_key"] = m["nume_key"]
            # cea mai bună încredere / steaguri
            if INCREDERE_RANK.get(m.get("incredere"), 0) > INCREDERE_RANK.get(canon.get("incredere"), 0):
                canon["incredere"] = m["incredere"]
            if m.get("parlamentar") and not canon.get("parlamentar"):
                canon["parlamentar"] = m["parlamentar"]
            if m.get("are_cv") and not canon.get("are_cv"):
                canon["are_cv"] = m["are_cv"]
            if m.get("cv") and not canon.get("cv"):
                canon["cv"] = m["cv"]
            canon["merged_from"].append(m["romega_id"])
            drop_ids.add(m["romega_id"])

        # recalculează agregările EXACT ca build_gold.py, pe colecțiile DEDUP-uite:
        #  - declaratii: cap la 20 (n_declaratii = nr. după dedup, capat) — colapsează copiile OCR
        #  - n_companii / contracte: dedup pe CUI (dict CUI->total) ca în gold
        #  - achizitii_directe: sumă pe TOATE rândurile de companie (ca în gold, fără dedup CUI)
        if len(canon.get("declaratii", []) or []) > DECL_CAP:
            canon["declaratii"] = canon["declaratii"][:DECL_CAP]
        canon["n_declaratii"] = len(canon.get("declaratii", []) or [])

        companii = canon.get("companii", []) or []
        firme_ctr = {}
        ad_total = 0.0
        for c in companii:
            adr = c.get("achizitii_directe")
            if adr and adr.get("total_ron"):
                ad_total += adr["total_ron"]
            cs = c.get("contracte_stat")
            if cs:
                firme_ctr[c.get("cui")] = cs.get("total_ron")
        canon["n_companii"] = len({c.get("cui") for c in companii})
        canon["n_firme_cu_contracte"] = len(firme_ctr)
        canon["total_contracte_ron"] = sum(v for v in firme_ctr.values() if v)
        canon["total_achizitii_directe_ron"] = round(ad_total, 2)

    # --- 4. scrie rezultatul (cu backup) ---
    new_persons = [p for p in persons if p["romega_id"] not in drop_ids]
    gold["persoane"] = new_persons
    gold["total_persoane"] = len(new_persons)

    # recompută tier-urile de încredere (numărul de persoane s-a schimbat)
    incr = {"high": 0, "context": 0, "candidat": 0}
    for p in new_persons:
        incr[p.get("incredere", "candidat")] = incr.get(p.get("incredere", "candidat"), 0) + 1
    gold["incredere"] = incr
    gold["splink_apply"] = {
        "perechi_sigure": len(safe_person_pairs),
        "perechi_nume_trecute": n_pairs_passing_rule,
        "grupuri": n_groups,
        "persoane_inainte": n_persons_before,
        "persoane_dupa": len(new_persons),
        "persoane_colapsate": n_collapsed_persons,
        "prob_min": PROB_MIN,
        "regula": "subset strict tokeni nume + token org distinctiv comun + prob>=0.9",
    }

    os.makedirs(LOCAL, exist_ok=True)
    if not os.path.exists(BACKUP_PATH):
        shutil.copy2(GOLD_PATH, BACKUP_PATH)
        backup_note = "creat"
    else:
        backup_note = "există deja (nu suprascris)"

    json.dump(gold, open(GOLD_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    print(f"backup: {BACKUP_PATH} ({backup_note})", flush=True)
    print(f"perechi de revizuit (input): {len(pairs)}", flush=True)
    print(f"perechi-nume care trec regula (subset+org+prob>=0.9): {n_pairs_passing_rule}", flush=True)
    print(f"perechi de persoane SIGURE: {len(safe_person_pairs)}", flush=True)
    print(f"grupuri (>1 persoană): {n_groups}", flush=True)
    print(f"persoane colapsate: {n_persons_before} -> {len(new_persons)} "
          f"(-{n_collapsed_persons})", flush=True)
    return gold["splink_apply"]


if __name__ == "__main__":
    main()
