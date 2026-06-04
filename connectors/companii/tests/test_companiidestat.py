"""Test parser companiidestat (SOE central + local)."""

from __future__ import annotations

from connectors.companii.companiidestat import parse_companiidestat, to_companies


def test_parse_companiidestat():
    data = {
        "companii": {
            "524277": {"cui": "524277", "nume": "AGROPRODCOM SA", "judet_nume": "Harghita",
                       "tier": "3", "derived_status": "PIERDERE", "sector_label": "Agricultură",
                       "listat_bvb": "False"},
            "14056826": {"cui": "14056826", "nume": "ROMGAZ SA", "tier": "1", "listat_bvb": "True"},
        }
    }
    recs = parse_companiidestat(data)
    assert len(recs) == 2
    agro = next(r for r in recs if r["cui"] == 524277)
    assert agro["judet"] == "Harghita"
    assert agro["central"] is False           # tier 3 = local
    romgaz = next(r for r in recs if r["cui"] == 14056826)
    assert romgaz["central"] is True          # tier 1 = central
    assert romgaz["listat_bvb"] is True

    companies = to_companies(recs)
    assert all(c.is_soe for c in companies)
    assert len(companies) == 2
