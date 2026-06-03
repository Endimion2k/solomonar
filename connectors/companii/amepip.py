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


def _is_amepip_header(row: list) -> bool:
    j = " ".join((c or "").upper() for c in row)
    return "CUI" in j and "DENUMIRE" in j


def parse_amepip_rows(rows: list[list], source: SourceRef | None = None) -> list[Company]:
    """Parsează rândurile tabelului AMEPIP (Anexa 1: Nr | CUI IP | DENUMIRE | DENUMIRE APT)."""
    out: list[Company] = []
    seen: set[int] = set()
    for row in rows:
        if not row or len(row) < 4 or _is_amepip_header(row):
            continue
        cui = _to_int(row[1])
        if not cui or cui in seen:
            continue
        seen.add(cui)
        out.append(
            Company(
                romega_id=Company.id_for_cui(cui),
                cui=cui,
                name=(row[2] or "").replace("\n", " ").strip(),
                is_soe=True,
                tutelary_authority=(row[3] or "").replace("\n", " ").strip() or None,
                sources=[source] if source else [],
            )
        )
    return out


def extract_amepip_pdf(pdf_bytes: bytes) -> list[list]:
    """Extrage rândurile tabelelor Anexa 1 dintr-un PDF AMEPIP (detectează tabelele după header)."""
    import io as _io

    import pdfplumber

    rows: list[list] = []
    with pdfplumber.open(_io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                if any(_is_amepip_header(r) for r in table[:2]):
                    rows.extend(table)
    return rows


def parse_amepip_pdf(pdf_bytes: bytes, source: SourceRef | None = None) -> list[Company]:
    """PDF AMEPIP → listă de companii de stat (Company, is_soe=True)."""
    return parse_amepip_rows(extract_amepip_pdf(pdf_bytes), source)
