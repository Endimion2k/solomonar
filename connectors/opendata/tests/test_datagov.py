"""Teste CKAN client — parse offline + descoperire live (skip pe eroare)."""

from __future__ import annotations

import pytest

from connectors.opendata.datagov import discover_datasets, parse_resources


def test_parse_resources():
    pkg = {
        "resources": [
            {"name": "Achizitii T1", "url": "http://a/x.xlsx", "format": "xlsx"},
            {"name": "Schema", "url": "http://a/s.csv", "format": "csv"},
        ]
    }
    res = parse_resources(pkg)
    assert len(res) == 2
    assert res[0]["format"] == "XLSX"
    assert res[1]["url"].endswith("s.csv")


def test_discover_budgets_live():
    try:
        ds = discover_datasets("buget")
    except Exception as e:  # pragma: no cover - depinde de rețea
        pytest.skip(f"data.gov.ro indisponibil: {e}")
    assert len(ds) > 0
    assert all("id" in d for d in ds)
