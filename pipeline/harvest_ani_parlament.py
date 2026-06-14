"""Harvest ANI central ȚINTIT pe parlamentari (465) — declarațiile lor de pe portalul vechi.

Iterează pe NUME (primitiva robustă: rămâne sub limita de 10k, spre deosebire de instituție). Normalizează
numele la 'nume prenume' (surname-first) ca să se potrivească cu formatul portalului. Resume-safe (reia
din _ani_index.json). Cross-validează + completează declarațiile parlamentarilor.

Rulare: python -m pipeline.harvest_ani_parlament [--max-pages N]
"""

from __future__ import annotations

import json
import os
import re
import sys
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from pipeline.harvest_ani import harvest  # noqa: E402

V = os.path.join(ROOT, "data/v1")


def _query_name(name: str) -> str | None:
    """Normalizează la 'surname firstname' (2 tokeni), fără diacritice, pt. substring-match ANI."""
    toks = [t for t in re.split(r"[\s]+", (name or "").strip()) if t]
    if len(toks) < 2:
        return None
    # surname = token-ul ALL-CAPS (senatori 'Mircea ABRUDEAN'); altfel primul (deputați 'Adomnicai Mirela')
    caps = [t for t in toks if t.isupper() and len(t) > 1]
    if caps:
        surname = caps[0]
        given = next((t for t in toks if t not in caps), "")
    else:
        surname, given = toks[0], toks[1]
    q = f"{surname} {given}".strip()
    q = unicodedata.normalize("NFKD", q).encode("ascii", "ignore").decode().lower()
    return q or None


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-pages", type=int, default=10)
    args = ap.parse_args()

    names = []
    for fn, k in [("parlament/deputati.json", "deputati"), ("parlament/senatori.json", "senatori")]:
        d = json.load(open(os.path.join(V, fn), encoding="utf-8"))
        rows = d.get("data") or d.get(k) or []
        rows = rows if isinstance(rows, list) else list(rows.values())
        for r in rows:
            q = _query_name(r.get("name", ""))
            if q:
                names.append(q)
    # dedup, păstrând ordinea
    seen, queries = set(), []
    for q in names:
        if q not in seen:
            seen.add(q)
            queries.append(("numePrenume", q))
    print(f"parlamentari de căutat în ANI: {len(queries)} nume distincte", flush=True)

    payload = harvest(queries, max_pages=args.max_pages, sample_pdfs=0)
    meta = payload.get("meta", {})
    print(f"GATA: {meta.get('total_metadate')} metadate ANI | "
          f"queries over-limit: {len(meta.get('queries_over_limit', []))} | "
          f"empty: {len(meta.get('queries_empty', []))}", flush=True)


if __name__ == "__main__":
    main()
