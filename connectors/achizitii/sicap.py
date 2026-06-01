"""Connector achizitii/sicap — achiziții publice (SICAP/SEAP).

Arhetip `bulk`. Sursa stabilă: XLSX anual pe data.gov.ro (`achizitii-publice-{an}`, publisher
ADR). FĂRĂ OCDS funcțional. Vezi docs/03-SOURCES.md §I.

- parse_contracts_rows : rânduri (XLSX/CSV) → Contract canonic (autoritate→firmă, sumă)
- awarded_contract_edges: muchii AWARDED_CONTRACT pentru graf
- total_by_supplier/authority: agregate (cine ia/dă cei mai mulți bani publici)
- SicapConnector.discover : găsește resursele XLSX prin CKAN (live)
"""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import date

from romega_core.http import Client
from romega_core.models import Company, Contract, Edge, EdgeType, make_id
from romega_core.provenance import SourceRef

UNKNOWN_AUTHORITY = "o:autoritate-necunoscuta"


def _to_int(v) -> int | None:
    try:
        return int(str(v).strip().replace(" ", ""))
    except (ValueError, TypeError):
        return None


def _to_float(v) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(" ", "")
    if not s:
        return None
    if "." in s and "," in s:
        s = s.replace(".", "").replace(",", ".") if s.rindex(",") > s.rindex(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".") if len(s.split(",")[-1]) <= 2 else s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def _to_date(v) -> date | None:
    if not v:
        return None
    s = str(v).strip()[:10]
    for fmt in ("iso", "dmy"):
        try:
            if fmt == "iso":
                return date.fromisoformat(s)
            d, m, y = s.replace("/", ".").split(".")
            return date(int(y), int(m), int(d))
        except (ValueError, IndexError):
            continue
    return None


def parse_contracts_rows(rows: list[dict], source: SourceRef | None = None) -> list[Contract]:
    """Mapează rânduri de achiziții → Contract (tolerant la denumiri de coloane)."""
    out: list[Contract] = []
    for row in rows:
        r = {(k or "").strip().lower(): v for k, v in row.items()}
        cui = _to_int(r.get("cui_castigator") or r.get("castigator_cui") or r.get("cui"))
        amount = _to_float(r.get("valoare_ron") or r.get("valoare") or r.get("amount"))
        if not cui or amount is None:
            continue
        authority = str(r.get("autoritate_contractanta") or r.get("autoritate") or "").strip()
        title = str(r.get("obiect_contract") or r.get("obiect") or r.get("titlu") or "").strip()
        cpv = str(r.get("cod_cpv") or r.get("cpv") or "").strip() or None
        award = _to_date(r.get("data_atribuire") or r.get("data"))
        out.append(
            Contract(
                romega_id=make_id("ct", authority, cui, amount, str(award or "")),
                contracting_authority_id=make_id("o", authority) if authority else UNKNOWN_AUTHORITY,
                supplier_id=Company.id_for_cui(cui),
                amount=amount,
                currency="RON",
                award_date=award,
                cpv=cpv,
                title=title,
                sources=[source] if source else [],
            )
        )
    return out


def parse_contracts_csv(csv_text: str, source: SourceRef | None = None) -> list[Contract]:
    return parse_contracts_rows(list(csv.DictReader(io.StringIO(csv_text))), source)


def read_xlsx(content: bytes, sheet: int = 0) -> list[dict]:
    """Citește un XLSX → listă de dict-uri (lazy openpyxl; `pip install openpyxl`)."""
    try:
        import openpyxl
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("openpyxl necesar pentru XLSX: pip install openpyxl") from e
    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    ws = wb.worksheets[sheet]
    it = ws.iter_rows(values_only=True)
    header = [str(h).strip() if h is not None else "" for h in next(it)]
    return [dict(zip(header, r)) for r in it]


def awarded_contract_edges(contracts: list[Contract]) -> list[Edge]:
    return [
        Edge(
            src=c.contracting_authority_id,
            dst=c.supplier_id,
            type=EdgeType.AWARDED_CONTRACT,
            props={"amount": c.amount, "date": str(c.award_date or ""), "title": c.title},
        )
        for c in contracts
    ]


def total_by_supplier(contracts: list[Contract]) -> dict[str, float]:
    agg: dict[str, float] = defaultdict(float)
    for c in contracts:
        agg[c.supplier_id] += c.amount
    return dict(agg)


def total_by_authority(contracts: list[Contract]) -> dict[str, float]:
    agg: dict[str, float] = defaultdict(float)
    for c in contracts:
        agg[c.contracting_authority_id] += c.amount
    return dict(agg)


class SicapConnector:
    """Arhetip `bulk`. Descoperă XLSX-urile anuale prin CKAN, apoi le ingestează (pe runner)."""

    source_id = "sicap_bulk"
    CKAN = "https://data.gov.ro/api/3/action"

    def __init__(self, client: Client | None = None) -> None:
        self.client = client or Client()

    def discover(self, year: int) -> list[dict]:
        """Listează resursele dataset-ului achizitii-publice-{an} (name, url, format)."""
        r = self.client.get(f"{self.CKAN}/package_show?id=achizitii-publice-{year}")
        r.raise_for_status()
        resources = (r.json().get("result") or {}).get("resources", [])
        return [
            {"name": x.get("name"), "url": x.get("url"), "format": x.get("format")}
            for x in resources
        ]
