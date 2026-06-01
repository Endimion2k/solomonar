"""Test parser AMEPIP (master list SOE din Anexa 1)."""

from __future__ import annotations

from connectors.companii.amepip import parse_master_list
from romega_core.models import Company

CSV = (
    "cui,denumire,autoritate_tutelara\n"
    "14056826,SNGN ROMGAZ SA,Ministerul Energiei\n"
    "10874881,SN Nuclearelectrica SA,Ministerul Energiei\n"
    ",rand fara cui,Minister X\n"  # rând invalid — ignorat
)


def test_parse_master_list():
    companies = parse_master_list(CSV)
    assert len(companies) == 2  # rândul fără CUI e sărit
    assert all(c.is_soe for c in companies)
    romgaz = next(c for c in companies if c.cui == 14056826)
    assert romgaz.tutelary_authority == "Ministerul Energiei"
    assert romgaz.romega_id == Company.id_for_cui(14056826)
