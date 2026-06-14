"""Teste pentru parsarea de date RO."""

from __future__ import annotations

from datetime import date

from solomonar_core.dates import RE_BIRTH, parse_ro_date


def test_parse_ro_date_variants():
    assert parse_ro_date("8", "sep.", "1977") == date(1977, 9, 8)
    assert parse_ro_date("15", "august", "1970") == date(1970, 8, 15)
    assert parse_ro_date("1", "mart", "1965") == date(1965, 3, 1)
    assert parse_ro_date("3", "luna_inexistenta", "2000") is None
    assert parse_ro_date("31", "feb.", "2001") is None  # dată invalidă


def test_re_birth_search():
    m = RE_BIRTH.search("Domnul X, n. 12 mar. 1965, ales în ...")
    assert m is not None
    assert parse_ro_date(*m.groups()) == date(1965, 3, 12)
