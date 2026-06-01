"""Teste pentru entity resolution (PersonRegistry)."""

from __future__ import annotations

from datetime import date

import pytest

from romega_core.resolve import MatchStatus, PersonRegistry


def test_same_person_different_order_same_id():
    reg = PersonRegistry()
    a = reg.resolve("Ion Popescu")
    b = reg.resolve("POPESCU Ion")
    assert a.status == MatchStatus.NEW
    assert b.status == MatchStatus.MATCHED
    assert a.romega_id == b.romega_id
    assert len(reg) == 1


def test_diacritics_variant_matches():
    reg = PersonRegistry()
    a = reg.resolve("Ștefan Gheorghiu")
    b = reg.resolve("Stefan Gheorghiu")
    assert a.romega_id == b.romega_id
    assert b.status == MatchStatus.MATCHED


def test_homonyms_with_different_birthdate_are_separated():
    reg = PersonRegistry()
    a = reg.resolve("Ion Popescu", birth_date=date(1970, 1, 1))
    b = reg.resolve("Ion Popescu", birth_date=date(1985, 5, 5))
    assert a.romega_id != b.romega_id
    assert a.status == MatchStatus.NEW
    assert b.status == MatchStatus.NEW
    assert len(reg) == 2


def test_same_name_same_birthdate_matches():
    reg = PersonRegistry()
    a = reg.resolve("Maria Ionescu", birth_date=date(1980, 3, 3))
    b = reg.resolve("IONESCU Maria", birth_date=date(1980, 3, 3))
    assert a.romega_id == b.romega_id
    assert b.status == MatchStatus.MATCHED


def test_external_id_crosswalk_is_decisive():
    reg = PersonRegistry()
    a = reg.resolve("Ion Popescu", external_ids={"cdep": "123"})
    # nume scris diferit, dar același ID extern -> match decisiv
    b = reg.resolve("Ioan Popescu", external_ids={"cdep": "123"})
    assert a.romega_id == b.romega_id
    assert b.status == MatchStatus.MATCHED
    assert len(reg) == 1


def test_extra_middle_name_lands_in_review_band():
    reg = PersonRegistry()
    reg.resolve("Ion Popescu")
    r = reg.resolve("Ion Vasile Popescu")  # superset de token-uri, fără dată naștere
    assert r.status == MatchStatus.REVIEW
    assert len(reg) == 1  # review NU adaugă o persoană nouă


def test_empty_name_raises():
    reg = PersonRegistry()
    with pytest.raises(ValueError):
        reg.resolve("   .  ")


def test_id_is_stable_across_registries():
    # același nume+an -> același romega_id chiar și în registre diferite (determinist)
    r1 = PersonRegistry().resolve("Ion Popescu", birth_date=date(1970, 1, 1))
    r2 = PersonRegistry().resolve("POPESCU Ion", birth_date=date(1970, 1, 1))
    assert r1.romega_id == r2.romega_id
