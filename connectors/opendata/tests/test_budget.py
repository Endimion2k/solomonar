"""Teste buget & salarii — parse tolerant + guard PII (offline) + descoperire live (skip)."""

from __future__ import annotations

import pytest

from connectors.opendata.budget import (
    BudgetConnector,
    budget_total,
    parse_budget_rows,
    parse_salary_rows,
    salary_stats,
    to_ron,
)


def test_to_ron_ro_format():
    assert to_ron("1.234,56") == pytest.approx(1234.56)
    assert to_ron("12.500") == pytest.approx(12500.0)   # mii, fără zecimale
    assert to_ron("4500,00") == pytest.approx(4500.0)
    assert to_ron(3200) == 3200.0
    assert to_ron("") is None
    assert to_ron("-") is None


def test_parse_salary_rows_tolerant():
    rows = [
        {"Functia": "Consilier", "Salariu net": "4.500,00", "Salariu brut": "7.700,00"},
        {"Denumire functie": "Director", "Venit net": "9.200"},
        {"Functia": "", "Salariu net": "1000"},          # fără funcție → sărit
        {"Functia": "Sofer"},                             # fără sumă → sărit
    ]
    recs = parse_salary_rows(rows, org_id="o:test", period="2026-03")
    assert len(recs) == 2
    assert recs[0].function == "Consilier"
    assert recs[0].net_ron == pytest.approx(4500.0)
    assert recs[0].org_id == "o:test"
    assert recs[1].function == "Director"


def test_salary_rows_pii_guard():
    # un câmp funcție cu CNP nu trebuie publicat
    rows = [{"Functia": "Director 1850101080012", "Salariu net": "9000"}]
    assert parse_salary_rows(rows) == []


def test_salary_stats():
    rows = [
        {"Functia": "A", "Salariu net": "3000"},
        {"Functia": "B", "Salariu net": "5000"},
        {"Functia": "C", "Salariu net": "7000"},
    ]
    st = salary_stats(parse_salary_rows(rows))
    assert st["count"] == 3 and st["with_net"] == 3
    assert st["min_ron"] == 3000 and st["max_ron"] == 7000 and st["median_ron"] == 5000


def test_parse_budget_rows_and_total():
    rows = [
        {"Capitol": "Cheltuieli de personal", "Suma": "1.250.000,00"},
        {"Indicator": "Bunuri si servicii", "Valoare": "350000"},
        {"Capitol": "", "Suma": "999"},  # fără label → sărit
    ]
    lines = parse_budget_rows(rows, org_id="o:minister")
    assert len(lines) == 2
    assert budget_total(lines) == pytest.approx(1_600_000.0)


def test_discover_salaries_live():
    try:
        ds = BudgetConnector().discover_salaries(rows=5)
    except Exception as e:  # pragma: no cover - depinde de rețea
        pytest.skip(f"data.gov.ro indisponibil: {e}")
    assert len(ds) > 0
    assert all("id" in d for d in ds)
