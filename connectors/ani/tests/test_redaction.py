"""Teste pentru guard-ul de redactare (PII) — critic legal."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel

from connectors.ani.declaratii import parse_avere_text
from connectors.ani.redaction import assert_clean, find_pii

FIX = Path(__file__).parent / "fixtures"


def test_find_pii_detects_cnp():
    assert "CNP" in find_pii("declarantul cu CNP 1850101080012 a depus")


def test_find_pii_detects_phone():
    assert "telefon" in find_pii("contact 0721234567")


def test_clean_text_has_no_pii():
    assert find_pii("Popescu Ion, judet Cluj, 500 m², 150.000 RON") == []


def test_parsed_avere_passes_guard():
    text = (FIX / "declaratie_avere.txt").read_text(encoding="utf-8")
    assert_clean(parse_avere_text(text))  # output-ul publicat (agregate) e curat


def test_assert_clean_raises_on_leak():
    class Leaky(BaseModel):
        note: str

    with pytest.raises(ValueError):
        assert_clean(Leaky(note="ramas CNP 2920202125634 in text"))
