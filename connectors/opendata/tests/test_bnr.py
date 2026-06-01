"""Teste connector BNR — parse XML (offline) + curs real (live, skip pe eroare)."""

from __future__ import annotations

import pytest

from connectors.opendata.bnr import BnrConnector, parse_bnr_rates

XML = """<?xml version="1.0" encoding="utf-8"?>
<DataSet xmlns="http://www.bnr.ro/xsd">
<Body><Cube date="2026-05-29">
<Rate currency="EUR">4.9776</Rate>
<Rate currency="USD">4.3812</Rate>
<Rate currency="HUF" multiplier="100">1.2345</Rate>
</Cube></Body></DataSet>"""


def test_parse_bnr_rates():
    d = parse_bnr_rates(XML)
    assert d["date"] == "2026-05-29"
    assert d["rates"]["EUR"] == 4.9776
    assert d["rates"]["USD"] == 4.3812
    assert round(d["rates"]["HUF"], 6) == round(1.2345 / 100, 6)  # multiplier aplicat


def test_bnr_live():
    try:
        d = BnrConnector().fetch_rates()
    except Exception as e:  # pragma: no cover - depinde de rețea
        pytest.skip(f"BNR live indisponibil: {e}")
    assert d["date"]
    assert d["rates"].get("EUR", 0) > 0
