"""Procentul de stat BVB se atribuie doar companiei listate, cu numele BVB ca cuvinte întregi."""

from __future__ import annotations

import sys
from pathlib import Path

from pipeline.build_duckdb import _bvb_pentru

BVB = [
    {"nume": "Compa", "procent_stat": 1.0},
    {"nume": "Electrica", "procent_stat": 49.8},
    {"nume": "Nuclearelectrica", "procent_stat": 82.5},
    {"nume": "Oil Terminal", "procent_stat": 87.8},
]


def _c(name, listed=True):
    return {"name": name, "bvb_listed": listed}


def test_whole_words_only():
    # „Compa” (Compa SA) NU se lipește de „Compania Națională…”
    assert _bvb_pentru(_c('COMPANIA NATIONALA "LOTERIA ROMANA" SA'), BVB) == {}
    assert _bvb_pentru(_c("COMPA SA"), BVB)["procent_stat"] == 1.0


def test_longest_match_wins():
    # „Nuclearelectrica” conține „electrica” doar ca subșir, nu ca cuvânt → potrivire corectă
    assert _bvb_pentru(_c('SOCIETATEA NATIONALA "NUCLEARELECTRICA" SA'), BVB)["procent_stat"] == 82.5
    assert _bvb_pentru(_c("OIL TERMINAL SA"), BVB)["procent_stat"] == 87.8


def test_unlisted_subsidiary_gets_nothing():
    # filiala nelistată nu primește procentul companiei-mamă
    assert _bvb_pentru(_c("NUCLEARELECTRICA SERV S.R.L.", listed=False), BVB) == {}


def test_client_rule_is_identical():
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "web"))
    from app.data import bvb_pentru

    for name, listed in [("COMPANIA NATIONALA ROMARM SA", True), ("COMPA SA", True),
                         ('S.N. "NUCLEARELECTRICA" SA', True), ("NUCLEARELECTRICA SERV SRL", False)]:
        assert bvb_pentru(_c(name, listed), BVB) == _bvb_pentru(_c(name, listed), BVB)
