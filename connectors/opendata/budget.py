"""Connector opendata/budget — bugete & salarii sector public (data.gov.ro).

Arhetip `bulk`. Două familii de dataset-uri CKAN:
- `drepturi-salariale-*` : situații salariale pe FUNCȚIE (lunar, per instituție).
- `buget*` : execuție/sinteză bugetară pe capitol/indicator (per instituție).

Privacy-by-design (Legea 176/2010 + GDPR, vezi docs/04-LEGAL-GDPR.md §2): NU modelăm nume
individuale — doar funcția/categoria + sume. Fiecare câmp text trece prin guard-ul PII; un
rând cu PII este sărit, nu publicat. Vezi docs/03-SOURCES.md §K (K3) și docs/00-MASTERPLAN.md.

- parse_salary_rows : rânduri XLSX/CSV → SalaryRecord (funcție + net/brut RON)
- parse_budget_rows : rânduri XLSX/CSV → BudgetLine (capitol/indicator + sumă RON)
- salary_stats / budget_total : agregate
- BudgetConnector.discover_salaries / discover_budgets : găsește dataset-urile prin CKAN (live)
"""

from __future__ import annotations

import csv
import io
from statistics import median

from pydantic import BaseModel, Field

from connectors.achizitii.sicap import read_xlsx
from connectors.ani.redaction import find_pii
from connectors.opendata.datagov import CkanClient, discover_datasets, parse_resources
from solomonar_core.http import Client
from solomonar_core.provenance import SourceRef

# Coloane acceptate (lower-case, tolerant la denumirile reale heterogene din data.gov.ro).
_FUNCTION_KEYS = (
    "functia", "funcția", "functie", "funcție", "denumire functie",
    "denumirea functiei", "post", "categorie", "denumire post",
)
_NET_KEYS = (
    "salariu net", "drepturi salariale nete", "venit net", "net",
    "salariu nominal net", "total net",
)
_GROSS_KEYS = (
    "salariu brut", "salariu de baza", "salariu de bază", "venit brut",
    "brut", "salariu nominal brut", "total brut",
)
_BUDGET_LABEL_KEYS = (
    "capitol", "indicator", "denumire indicator", "denumire", "capitol bugetar",
    "subcapitol", "titlu", "articol",
)
_BUDGET_AMOUNT_KEYS = (
    "suma", "valoare", "credite bugetare", "credite de angajament",
    "plati efectuate", "plăți efectuate", "cheltuieli", "executat", "prevederi",
)


def to_ron(v) -> float | None:
    """Parsează o sumă RON tolerant la formatul românesc (1.234,56) și separatori.

    Why: fișierele data.gov.ro amestecă formatul EN și RO; un parser naiv ar produce sume
    eronate de ordine de mărime (1.234 → 1234 vs 1.234).
    """
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(" ", "").replace("\xa0", "")
    if not s or s in ("-", "."):
        return None
    if "." in s and "," in s:
        # ultimul separator = zecimal; celălalt = mii.
        s = s.replace(".", "").replace(",", ".") if s.rindex(",") > s.rindex(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".") if len(s.split(",")[-1]) <= 2 else s.replace(",", "")
    elif "." in s:
        # Convenție RO: punctul e separator de mii dacă apare de mai multe ori
        # sau dacă grupul final are exact 3 cifre (ex. "12.500" = 12500). Altfel zecimal.
        parts = s.split(".")
        if len(parts) > 2 or (len(parts) == 2 and len(parts[1]) == 3):
            s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def _first(row: dict, keys: tuple[str, ...]) -> object:
    for k in keys:
        if k in row and row[k] not in (None, ""):
            return row[k]
    return None


class SalaryRecord(BaseModel):
    """Salariu agregat pe funcție (FĂRĂ nume — privacy-by-design)."""

    function: str
    org_id: str | None = None
    period: str | None = None  # ex. "2026-03"
    net_ron: float | None = None
    gross_ron: float | None = None
    sources: list[SourceRef] = Field(default_factory=list)


class BudgetLine(BaseModel):
    """O linie de buget (capitol/indicator + sumă)."""

    label: str
    org_id: str | None = None
    period: str | None = None
    amount_ron: float | None = None
    sources: list[SourceRef] = Field(default_factory=list)


def _lower_row(row: dict) -> dict:
    return {(k or "").strip().lower(): v for k, v in row.items()}


def parse_salary_rows(
    rows: list[dict],
    org_id: str | None = None,
    period: str | None = None,
    source: SourceRef | None = None,
) -> list[SalaryRecord]:
    """Mapează rânduri → SalaryRecord. Sare rândurile fără funcție/sumă sau cu PII."""
    out: list[SalaryRecord] = []
    for row in rows:
        r = _lower_row(row)
        function = _first(r, _FUNCTION_KEYS)
        net = to_ron(_first(r, _NET_KEYS))
        gross = to_ron(_first(r, _GROSS_KEYS))
        if function is None or (net is None and gross is None):
            continue
        function = str(function).strip()
        if not function or find_pii(function):
            continue  # guard PII: nu publicăm un câmp cu CNP/telefon/CI
        out.append(
            SalaryRecord(
                function=function,
                org_id=org_id,
                period=period,
                net_ron=net,
                gross_ron=gross,
                sources=[source] if source else [],
            )
        )
    return out


def parse_budget_rows(
    rows: list[dict],
    org_id: str | None = None,
    period: str | None = None,
    source: SourceRef | None = None,
) -> list[BudgetLine]:
    """Mapează rânduri → BudgetLine (capitol/indicator + sumă)."""
    out: list[BudgetLine] = []
    for row in rows:
        r = _lower_row(row)
        label = _first(r, _BUDGET_LABEL_KEYS)
        amount = to_ron(_first(r, _BUDGET_AMOUNT_KEYS))
        if label is None or amount is None:
            continue
        label = str(label).strip()
        if not label or find_pii(label):
            continue
        out.append(
            BudgetLine(
                label=label, org_id=org_id, period=period,
                amount_ron=amount, sources=[source] if source else [],
            )
        )
    return out


def parse_salary_csv(csv_text: str, **kw) -> list[SalaryRecord]:
    return parse_salary_rows(list(csv.DictReader(io.StringIO(csv_text))), **kw)


def parse_budget_csv(csv_text: str, **kw) -> list[BudgetLine]:
    return parse_budget_rows(list(csv.DictReader(io.StringIO(csv_text))), **kw)


def salary_stats(records: list[SalaryRecord]) -> dict:
    """Statistici pe net (cine câștigă cât, fără nume)."""
    nets = [r.net_ron for r in records if r.net_ron is not None]
    if not nets:
        return {"count": len(records), "with_net": 0}
    return {
        "count": len(records),
        "with_net": len(nets),
        "min_ron": min(nets),
        "median_ron": median(nets),
        "max_ron": max(nets),
    }


def budget_total(lines: list[BudgetLine]) -> float:
    return sum(line.amount_ron for line in lines if line.amount_ron is not None)


class BudgetConnector:
    """Arhetip `bulk`. Descoperă dataset-urile salarii/buget prin CKAN, apoi le ingestează."""

    source_id = "budget"

    def __init__(self, client: Client | None = None) -> None:
        self.client = client or Client()
        self.ckan = CkanClient(self.client)

    def discover_salaries(self, rows: int = 20) -> list[dict]:
        return discover_datasets("drepturi-salariale", self.ckan, rows=rows)

    def discover_budgets(self, rows: int = 20) -> list[dict]:
        return discover_datasets("buget", self.ckan, rows=rows)

    def resources(self, package_id: str) -> list[dict]:
        """Resursele (name/url/format) ale unui dataset, pentru selecție XLSX/CSV."""
        return parse_resources(self.ckan.package_show(package_id))

    def read_resource(self, url: str, fmt: str) -> list[dict]:
        """Descarcă o resursă și o normalizează la list[dict] (XLSX sau CSV).

        XLS (legacy BIFF) necesită `xlrd` — neinstalat; ridicăm hint clar în loc să eșuăm opac.
        """
        fmt = (fmt or "").upper()
        r = self.client.get(url)
        r.raise_for_status()
        if fmt in ("XLSX",):
            return read_xlsx(r.content)
        if fmt in ("CSV", "TXT"):
            return list(csv.DictReader(io.StringIO(r.content.decode("utf-8", "replace"))))
        if fmt in ("XLS",):
            raise RuntimeError("format .xls legacy: pip install xlrd sau convertește în XLSX/CSV")
        raise RuntimeError(f"format neacceptat pentru ingest tabular: {fmt}")
