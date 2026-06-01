"""Teste SICAP — parse contracte, agregate, muchii + interogarea follow-the-money (conflict)."""

from __future__ import annotations

from datetime import date

from connectors.achizitii.sicap import (
    awarded_contract_edges,
    parse_contracts_csv,
    total_by_supplier,
)
from pipeline.gold.graph import GraphStore
from romega_core.models import Company, EdgeType, make_id

CSV = (
    "autoritate_contractanta,cui_castigator,valoare_ron,obiect_contract,data_atribuire,cod_cpv\n"
    "Primaria Cluj,14056826,1500000,Servicii X,2024-03-15,79900000\n"
    "Ministerul Sanatatii,999888,250000,Echipamente,2024-05-20,33100000\n"
    "Primaria Cluj,14056826,500000,Servicii Y,2024-06-01,79900000\n"
)


def test_parse_contracts():
    cs = parse_contracts_csv(CSV)
    assert len(cs) == 3
    c0 = cs[0]
    assert c0.supplier_id == Company.id_for_cui(14056826)
    assert c0.amount == 1500000.0
    assert c0.award_date == date(2024, 3, 15)
    assert c0.contracting_authority_id == make_id("o", "Primaria Cluj")
    assert c0.cpv == "79900000"


def test_total_by_supplier():
    tot = total_by_supplier(parse_contracts_csv(CSV))
    assert tot[Company.id_for_cui(14056826)] == 2000000.0  # 1.5M + 0.5M


def test_awarded_edges():
    edges = awarded_contract_edges(parse_contracts_csv(CSV))
    assert len(edges) == 3
    assert all(e.type == EdgeType.AWARDED_CONTRACT for e in edges)


def test_conflict_follow_the_money():
    """Firma unui demnitar (membru CA) care câștigă contracte publice = red flag."""
    g = GraphStore()
    firm = Company.id_for_cui(14056826)
    g.add_edge("p:x", "o:guvern", "HOLDS_POSITION")   # p:x e demnitar
    g.add_edge("p:x", firm, "MEMBER_OF_BOARD")         # ...și membru CA la firmă
    for e in awarded_contract_edges(parse_contracts_csv(CSV)):
        g.add_edge(e.src, e.dst, e.type, e.props)      # contractele

    flagged = {row[0] for row in g.contracts_with_conflicted_suppliers()}
    assert firm in flagged                              # are contract + membru CA cu funcție
    assert Company.id_for_cui(999888) not in flagged    # are contract, dar fără conflict
    g.close()
