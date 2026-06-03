"""Test parser dump ONRC (firme + reprezentanți legali)."""

from __future__ import annotations

from connectors.companii.onrc_dump import parse_firme, parse_reprezentanti, to_companies

FIRME = (
    "cui,denumire,cod_inmatriculare\n"
    "14056826,ROMGAZ SA,J40/100/2001\n"
    "999,Mica Firma SRL,J12/5/2010\n"
)
REPR = "cui,nume\n14056826,Popescu Ion\n14056826,Ionescu Maria\n"


def test_parse_and_merge():
    companies = to_companies(parse_firme(FIRME), parse_reprezentanti(REPR))
    assert len(companies) == 2
    romgaz = next(c for c in companies if c.cui == 14056826)
    assert romgaz.reg_com == "J40/100/2001"
    assert set(romgaz.legal_reps) == {"Popescu Ion", "Ionescu Maria"}


def test_parse_firme_caret_delimiter():
    """Dump-ul ONRC 2025 real folosește delimiter '^' + BOM + header MAJUSCULE."""
    txt = "﻿DENUMIRE^CUI^COD_INMATRICULARE\nROMGAZ SA^14056826^J40/100/2001\n"
    firme = parse_firme(txt)
    assert 14056826 in firme
    assert firme[14056826]["reg_com"] == "J40/100/2001"
    assert firme[14056826]["name"] == "ROMGAZ SA"
