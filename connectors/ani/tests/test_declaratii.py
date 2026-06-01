"""Teste pentru parserul de avere ANI + delta (portate din cdep, pe fixture template)."""

from __future__ import annotations

from pathlib import Path

from connectors.ani.declaratii import AvereParsed, compute_avere_delta, parse_avere_text

FIX = Path(__file__).parent / "fixtures"


def test_parse_avere_text():
    text = (FIX / "declaratie_avere.txt").read_text(encoding="utf-8")
    a = parse_avere_text(text)
    assert a.text_extracted is True
    assert a.terenuri_count == 2
    assert a.cladiri_count == 1
    assert a.suprafata_total_mp == 12575.0          # 500 + 12000 + 75
    assert a.conturi_total_ron == 251000.0          # 150.000 RON + 20.000 EUR * 5.05
    assert a.datorii_total_ron == 300000.0
    assert a.venituri_anuale_ron == 170000.0        # 120.000 + 50.000
    assert a.auto_count == 2


def test_needs_ocr_on_short_text():
    a = parse_avere_text("PDF scanat fara text")
    assert a.text_extracted is False
    assert a.needs_ocr is True


def test_compute_avere_delta():
    d1 = AvereParsed(text_extracted=True, conturi_total_ron=100000, terenuri_count=1, venituri_anuale_ron=80000)
    d2 = AvereParsed(
        text_extracted=True, conturi_total_ron=250000, terenuri_count=1, cladiri_count=1, venituri_anuale_ron=120000
    )
    delta = compute_avere_delta([d1, d2])
    assert delta.n_declaratii == 2
    assert delta.delta_conturi_ron == 150000
    assert delta.delta_imobile == 1                 # (1+1) - (1+0)
    assert delta.delta_venituri_ron == 40000
