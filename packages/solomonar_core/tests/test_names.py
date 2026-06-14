"""Teste pentru normalizarea de nume RO."""

from __future__ import annotations

from solomonar_core.names import (
    canonical_name,
    name_key,
    name_similarity,
    split_name,
    strip_diacritics,
)


def test_strip_diacritics_comma_and_cedilla():
    # virgulă-jos (corect) și cedilă (variantă) trebuie pliate identic
    assert strip_diacritics("Țăndărică") == "Tandarica"
    assert strip_diacritics("Ţăndărică") == "Tandarica"  # ţ cedilă
    assert strip_diacritics("Șerban") == strip_diacritics("Şerban") == "Serban"
    assert strip_diacritics("Gheorghiță") == "Gheorghita"


def test_name_key_order_invariant():
    assert name_key("POPESCU Ion") == name_key("Ion Popescu")
    assert name_key("IONESCU Maria Elena") == name_key("Maria Elena Ionescu")


def test_name_key_strips_titles_and_diacritics():
    assert name_key("Dr. Ștefan Gheorghiu") == name_key("Stefan Gheorghiu")
    assert name_key("ing. Vasile Pop") == name_key("Vasile POP")


def test_name_key_hyphen_split():
    # numele compuse cu cratimă devin token-uri separate (matching robust)
    assert name_key("Popescu-Tăriceanu Călin") == name_key("Calin Popescu Tariceanu")


def test_split_name_caps_signal():
    assert split_name("POPESCU Ion Vasile") == ("Popescu", "Ion Vasile")
    # fără semnal de majuscule -> ambiguu -> (None, None)
    assert split_name("Ion Popescu") == (None, None)


def test_canonical_name_strips_titles():
    assert canonical_name("  Dr.  Ion   Popescu ") == "Ion Popescu"


def test_name_similarity():
    assert name_similarity("Ion Popescu", "POPESCU Ion") == 1.0
    assert name_similarity("Ștefan Gheorghiu", "Stefan Gheorghiu") == 1.0
    # persoane clar diferite -> scor mic
    assert name_similarity("Ion Popescu", "Maria Ionescu") < 0.4
    # typo în nume -> scor ridicat dar sub 1.0
    s = name_similarity("Gheorghe Popescu", "Gheorghe Popesco")
    assert 0.4 < s < 1.0
