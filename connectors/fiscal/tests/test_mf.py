"""Test parser bilanțuri MF (situații financiare)."""

from __future__ import annotations

from connectors.fiscal.mf import parse_financials_rows


def test_parse_financials_rows():
    rows = [
        {"cui": "14056826", "cifra_afaceri": "7000000000", "profit_net": "2000000000", "nr_mediu_salariati": "5000"},
        {"cui": "999", "cifra_afaceri": "1.500.000", "profit_net": "100.000", "nr_mediu_salariati": "12"},
        {"cui": "", "cifra_afaceri": "0"},  # fără CUI — ignorat
    ]
    fin = parse_financials_rows(rows, 2024)
    assert len(fin) == 2
    big = fin[14056826]
    assert big.year == 2024
    assert big.turnover_ron == 7_000_000_000.0
    assert big.employees == 5000
    assert fin[999].turnover_ron == 1_500_000.0  # format RO cu puncte ca mii
