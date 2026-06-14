"""Teste pentru helpers de parsing + encoding."""

from __future__ import annotations

from solomonar_core.parse import all_texts, decode, first_text, selector

_HTML = "<table><tr><td class='n'>Ion Popescu</td><td class='n'>Maria Ionescu</td></tr></table>"


def test_decode_latin2():
    # ț/ș cu virgulă-jos NU există în Latin-2; 'ă' (breve, U+0103) DA -> round-trip valid
    raw = "Brăila".encode("iso-8859-2")
    assert decode(raw, "iso-8859-2") == "Brăila"


def test_decode_fallback_utf8():
    assert decode("Ștefan".encode("utf-8")) == "Ștefan"


def test_first_text():
    sel = selector(_HTML)
    assert first_text(sel, "td.n::text") == "Ion Popescu"
    assert first_text(sel, "td.missing::text", default="-") == "-"


def test_all_texts():
    sel = selector(_HTML)
    assert all_texts(sel, "td.n::text") == ["Ion Popescu", "Maria Ionescu"]
