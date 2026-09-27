"""Cititorul SICAP comun: dialectele CSV de pe data.gov.ro, coloanele, grupurile de variante."""

from __future__ import annotations

import csv

from pipeline import sicap_io as S
from pipeline.harvest_achizitii_directe import COL_CUI, COL_NUME, COL_VAL


def _parse(lines):
    return list(csv.reader(lines, **S.csv_dialect(lines[0])))


def test_pipe_quoted_comma_csv_2021_2022():
    # achiziții directe 2021 T2 → 2022 T4: câmpuri între | separate prin virgulă (split naiv pe | le strica)
    rows = _parse(['|NUMAR|,|DENUMIRE_AC|,|VALOARE_ATRIBUITA_RON|,|OFERTANT|,|CUI_OFERTANT|',
                   '|DA1|,|Liceul X, Braila|,645.5,|SELGROS SRL|,|11805367|'])
    assert rows[1] == ["DA1", "Liceul X, Braila", "645.5", "SELGROS SRL", "11805367"]
    assert (S.pick(rows[0], COL_CUI), S.pick(rows[0], COL_VAL), S.pick(rows[0], COL_NUME)) == (4, 2, 3)


def test_unquoted_caret_csv_keeps_quotes_in_names():
    rows = _parse(['Castigator^CastigatorCUI^ValoareRON', 'SC "ALFA" SRL^123^100.5'])
    assert rows[1] == ['SC "ALFA" SRL', "123", "100.5"]


def test_recent_xlsx_column_names():
    header = ["Denumire AC", "CUI ofertant castigator", "Valoare achizitie (RON)", "Ofertant castigator"]
    assert (S.pick(header, COL_CUI), S.pick(header, COL_VAL), S.pick(header, COL_NUME)) == (1, 2, 3)


def test_awarded_value_preferred_over_estimate():
    header = ["VALOARE_ESTIMATA_RON", "VALOARE_ATRIBUITA_RON"]
    assert S.pick(header, COL_VAL) == 1


def test_find_header_skips_banners():
    rows = iter([["Raport achizitii directe"], [], ["CUI ofertant castigator", "Valoare achizitie (RON)"], ["1", "2"]])
    assert S.find_header(rows, [COL_CUI, COL_VAL]) == ["CUI ofertant castigator", "Valoare achizitie (RON)"]
    assert next(rows) == ["1", "2"]


def test_variants_of_same_quarter_grouped_xls_first():
    a = {"an": 2023, "tip": "directe", "perioada": "T3", "format": "CSV", "url": "a"}
    b = {"an": 2023, "tip": "directe", "perioada": "T3", "format": "XLS", "url": "b"}
    c = {"an": 2023, "tip": "directe", "perioada": "T4", "format": "CSV", "url": "c"}
    assert S.group_key(a) == S.group_key(b) != S.group_key(c)
    assert [r["url"] for r in S.order_variants([a, b])] == ["b", "a"]
