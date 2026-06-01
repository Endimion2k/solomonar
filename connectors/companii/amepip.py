"""Connector companii/amepip — master list de companii de stat (SOE).

Sursa autoritativă: AMEPIP, Raport anual, Anexa 1 (CUI + denumire + autoritate tutelară).
~1.320 întreprinderi publice (146 centrale + 1.174 locale). Vezi docs/03-SOURCES.md §G.

Anexa 1 e un tabel într-un PDF — pe runner se extrage cu pdfplumber, apoi `parse_master_list`
ia rândurile (CSV) → Company(is_soe=True). Coloanele reale de validat pe raportul live.
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


def parse_master_list(csv_text: str, source: SourceRef | None = None) -> list[Company]:
    """Parsează Anexa 1 (CSV cu coloane cui, denumire, autoritate_tutelara) → companii SOE."""
    reader = csv.DictReader(io.StringIO(csv_text))
    out: list[Company] = []
    for row in reader:
        r = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        cui = _to_int(r.get("cui"))
        if not cui:
            continue
        out.append(
            Company(
                romega_id=Company.id_for_cui(cui),
                cui=cui,
                name=r.get("denumire") or r.get("nume") or "",
                is_soe=True,
                tutelary_authority=(r.get("autoritate_tutelara") or r.get("apt") or None),
                sources=[source] if source else [],
            )
        )
    return out
