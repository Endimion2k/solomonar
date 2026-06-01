"""Teste INS Tempo — count tolerant (offline) + live (skip pe eroare)."""

from __future__ import annotations

import pytest

from connectors.opendata.ins import InsTempoClient, matrix_count


def test_matrix_count_tolerant():
    assert matrix_count([1, 2, 3]) == 3
    assert matrix_count({"matrices": [1, 2]}) == 2
    assert matrix_count({}) == 0


def test_ins_live():
    try:
        m = InsTempoClient().matrices()
    except Exception as e:  # pragma: no cover - rețea / firewall
        pytest.skip(f"INS Tempo indisponibil: {e}")
    assert matrix_count(m) > 0
