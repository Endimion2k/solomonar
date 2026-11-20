"""Registrul ONRC pentru firmele RELEVANTE: companiile de stat + câștigătorii de contracte SICAP.

Generează onrc/firme_relevante.json (CUI, denumire, nr. registru, localitate, județ, formă juridică)
din cel mai nou dump OD_FIRME de pe data.gov.ro (vezi onrc_stream.dump_curent). Lista e folosită ca
ținte de enrich_reprezentanti. Acoperirea nu scade la refresh: firmele publicate anterior rămân ținte.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from pipeline.onrc_stream import dump_curent, randuri  # noqa: E402

V = os.path.join(ROOT, "data/v1")
OUT = os.path.join(V, "onrc/firme_relevante.json")
MIN_KEEP_RATIO = 0.9   # țintele includ tot ce e publicat, deci o scădere mare = dump citit parțial


def _load(p):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _cui(x) -> int | None:
    try:
        cui = int(str(x).strip())
    except (TypeError, ValueError):
        return None
    return cui if cui > 0 else None


def tinte(index_companii, contracte_firme, publicate) -> set[int]:
    """CUI-urile căutate: companii de stat + câștigători SICAP + tot ce e deja publicat."""
    cuis = set()
    for c in ((index_companii or {}).get("data") or []):
        cuis.add(_cui(c.get("cui")))
    for f in ((contracte_firme or {}).get("firme") or []):
        cuis.add(_cui(f.get("cui")))
    for f in ((publicate or {}).get("firme") or []):
        cuis.add(_cui(f.get("cui")))
    cuis.discard(None)
    return cuis


def firma(p: list[str], idx: dict[str, int]) -> dict:
    """Rând OD_FIRME → înregistrarea publicată."""
    def col(nume):
        i = idx.get(nume)
        return p[i].strip() if i is not None and i < len(p) else ""
    return {"cui": _cui(col("CUI")), "denumire": col("DENUMIRE"), "reg_com": col("COD_INMATRICULARE"),
            "localitate": col("ADR_LOCALITATE"), "judet": col("ADR_JUDET"), "forma_juridica": col("FORMA_JURIDICA")}


def main() -> dict:
    publicate = _load(OUT) or {}
    cuis = tinte(_load(os.path.join(V, "companii/_index.json")),
                 _load(os.path.join(V, "achizitii/contracte_firme.json")), publicate)
    print(f"CUI-uri țintă (stat + câștigători SICAP): {len(cuis)}", flush=True)
    dump, urls = dump_curent("OD_FIRME")

    gasite: dict[int, dict] = {}
    n = 0
    for p, idx in randuri(urls["OD_FIRME"]):
        n += 1
        if n % 1_000_000 == 0:
            print(f"   OD_FIRME: {n // 1_000_000}M rânduri, găsite={len(gasite)}", flush=True)
        try:
            cui = int(p[idx["CUI"]])
        except (ValueError, IndexError, KeyError):
            continue
        if cui in cuis:
            gasite[cui] = firma(p, idx)   # la duplicate rămâne ultima apariție din dump

    vechi = publicate.get("total") or 0
    if len(gasite) < vechi * MIN_KEEP_RATIO:
        raise SystemExit(f"REFUZ să suprascriu firme_relevante.json: {len(gasite)} firme față de {vechi} publicate. "
                         f"Dump-ul ONRC a fost citit parțial; fișierul publicat rămâne neschimbat.")
    out = sorted(gasite.values(), key=lambda f: f["cui"])
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"sursa": "data.gov.ro OD_FIRME (ONRC)", "dump": dump,
                   "generated_at": datetime.now(timezone.utc).isoformat(),
                   "total": len(out), "firme": out}, f, ensure_ascii=False, indent=1)
    print(f"PUBLICAT firme_relevante.json: {len(out)}/{len(cuis)} firme găsite în {n:,} rânduri", flush=True)
    return {"total": len(out), "tinte": len(cuis)}


if __name__ == "__main__":
    main()
