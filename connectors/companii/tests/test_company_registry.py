"""Test CompanyRegistry (merge pe CUI) + muchii CONTROLS (stat → SOE)."""

from __future__ import annotations

from connectors.companii.amepip import parse_master_list
from connectors.companii.registry import CompanyRegistry, control_edges
from connectors.fiscal.anaf import to_company
from romega_core.models import Company, EdgeType, make_id


def test_merge_amepip_then_anaf_by_cui():
    reg = CompanyRegistry()
    # AMEPIP: is_soe + autoritate + nume
    soe = parse_master_list("cui,denumire,autoritate_tutelara\n14056826,ROMGAZ,Ministerul Energiei\n")[0]
    reg.upsert(soe)
    # ANAF: status + CAEN + TVA (același CUI)
    anaf = to_company(
        {
            "date_generale": {"cui": 14056826, "cod_CAEN": "0610", "stare_inregistrare": "INREGISTRAT"},
            "inregistrare_scop_Tva": {"scpTVA": True},
        }
    )
    merged = reg.upsert(anaf)
    assert len(reg) == 1  # același CUI → o singură companie
    assert merged.is_soe is True
    assert merged.tutelary_authority == "Ministerul Energiei"
    assert merged.caen == "0610"
    assert merged.status == "active"
    assert merged.vat_payer is True


def test_control_edges_state_to_soe():
    soe = parse_master_list("cui,denumire,autoritate_tutelara\n14056826,ROMGAZ,Ministerul Energiei\n")
    edges = control_edges(soe)
    assert len(edges) == 1
    e = edges[0]
    assert e.type == EdgeType.CONTROLS
    assert e.src == make_id("o", "Ministerul Energiei")
    assert e.dst == Company.id_for_cui(14056826)
