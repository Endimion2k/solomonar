"""Connector companii/onrc_dump — dump ONRC gratuit de pe data.gov.ro.

Arhetip `bulk`. Fișiere CSV (CC BY 4.0): OD_FIRME (denumire, CUI, cod înmatriculare) +
OD_REPREZENTANTI_LEGALI (CUI → reprezentanți). GRATIS, dar conține DOAR reprezentanți legali,
NU asociați/% (acționariatul cu % e plătit — deferit; vezi T1 în STATE.md).

NOTĂ v0: `legal_reps` stochează NUME (string-uri). Rezoluția nume → romega_id Person e un pas
ulterior (reprezentanții devin noduri Person în graf).
"""

from __future__ import annotations

import csv
import io

from romega_core.models import Company
from romega_core.provenance import SourceRef


def _to_int(s: str | None) -> int | None:
    try:
        return int(str(s).strip().replace(" ", ""))
    except (ValueError, TypeError):
        return None


def _sniff_delimiter(csv_text: str) -> str:
    """Dump-urile ONRC 2025 folosesc '^'; cele vechi ','. Detectează din prima linie."""
    first = csv_text.lstrip("﻿").splitlines()[0] if csv_text.strip() else ""
    return "^" if first.count("^") > first.count(",") else ","


def _rows(csv_text: str, delimiter: str | None = None) -> list[dict]:
    csv_text = csv_text.lstrip("﻿")
    reader = csv.DictReader(io.StringIO(csv_text), delimiter=delimiter or _sniff_delimiter(csv_text))
    return [{(k or "").strip().lower(): (v or "").strip() for k, v in row.items()} for row in reader]


def parse_firme(csv_text: str) -> dict[int, dict]:
    out: dict[int, dict] = {}
    for r in _rows(csv_text):
        cui = _to_int(r.get("cui"))
        if not cui:
            continue
        out[cui] = {
            "cui": cui,
            "name": r.get("denumire") or r.get("nume") or "",
            "reg_com": r.get("cod_inmatriculare") or r.get("reg_com") or None,
        }
    return out


def parse_reprezentanti(csv_text: str) -> dict[int, list[str]]:
    out: dict[int, list[str]] = {}
    for r in _rows(csv_text):
        cui = _to_int(r.get("cui"))
        nume = r.get("nume") or r.get("reprezentant") or r.get("nume_reprezentant") or ""
        if cui and nume:
            out.setdefault(cui, []).append(nume)
    return out


def to_companies(
    firme: dict[int, dict],
    reprezentanti: dict[int, list[str]] | None = None,
    source: SourceRef | None = None,
) -> list[Company]:
    reprezentanti = reprezentanti or {}
    out: list[Company] = []
    for cui, f in firme.items():
        out.append(
            Company(
                romega_id=Company.id_for_cui(cui),
                cui=cui,
                name=f["name"],
                reg_com=f["reg_com"],
                legal_reps=reprezentanti.get(cui, []),  # nume (string-uri) — rezolvate ulterior
                sources=[source] if source else [],
            )
        )
    return out
