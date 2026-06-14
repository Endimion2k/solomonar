"""Teste connector generic institutie — config → Organization + subordonare + declaratii links."""

from __future__ import annotations

from connectors.institutie.generic import (
    COUNTIES,
    build_deconcentrated_from_config,
    build_local_from_config,
    build_organizations,
    find_declaration_links,
    find_institution_sections,
    generate_deconcentrated,
    org_id,
    resolve_org_by_name,
    subordinate_edges,
)
from pipeline.config import iter_sources, load_sources
from solomonar_core.models import EdgeType


def _flat():
    return iter_sources(load_sources())


def test_build_organizations_from_config():
    orgs = build_organizations(_flat())
    by = {o.romega_id: o for o in orgs}
    assert by[org_id("mae")].type == "ministry"
    assert by[org_id("mae")].domain == "mae.ro"
    assert by[org_id("asf")].type == "agency"
    assert by[org_id("gov")].type == "government"
    assert by[org_id("cdep")].type == "parliament_chamber"
    # grupurile umbrelă / templated NU devin organizații
    assert org_id("ministere") not in by
    assert org_id("agentii_centrale") not in by
    assert org_id("deconcentrate") not in by
    assert len(orgs) >= 30


def test_subordinate_edges_ministry_to_gov():
    edges = subordinate_edges(_flat())
    gov = org_id("gov")
    assert any(
        e.src == org_id("mae") and e.dst == gov and e.type == EdgeType.SUBORDINATE_OF
        for e in edges
    )
    assert len(edges) == 16  # cele 16 ministere


def test_counties_count():
    assert len(COUNTIES) == 42  # 41 județe + București
    assert "Cluj" in COUNTIES and "București" in COUNTIES


def test_generate_deconcentrated():
    orgs = generate_deconcentrated({"sanatate": ["DSP", "CAS"]}, ["Cluj", "București"])
    assert len(orgs) == 4  # 2 servicii × 2 județe
    names = {o.name for o in orgs}
    assert "DSP Cluj" in names and "CAS București" in names
    assert all(o.type == "deconcentrated" for o in orgs)
    dsp_cluj = next(o for o in orgs if o.name == "DSP Cluj")
    assert dsp_cluj.short_name == "DSP" and dsp_cluj.county == "Cluj"


def test_build_deconcentrated_from_config():
    orgs = build_deconcentrated_from_config(_flat())
    # 29 tipuri de servicii × 42 unități ≈ 1218
    assert len(orgs) >= 1000
    assert all(o.type == "deconcentrated" for o in orgs)


def test_build_local_from_config():
    orgs = build_local_from_config(_flat())
    assert len(orgs) >= 100  # ~4 servicii × 42 unități
    assert all(o.tier == "local_autonomy" and o.type == "local_council_body" for o in orgs)


def test_resolve_org_by_name():
    orgs = build_organizations(_flat())
    assert resolve_org_by_name("Ministerul Energiei", orgs) == org_id("energie")
    assert resolve_org_by_name("Ministerul Finanțelor", orgs) == org_id("mf")
    assert resolve_org_by_name("Institutie Inexistenta XYZ", orgs) is None


def test_find_institution_sections():
    html = (
        '<a href="/minister/conducere/">Conducere</a>'
        '<a href="/node/5104">Declarații avere-interese</a>'
        '<a href="/contact">Contact</a>'
    )
    s = find_institution_sections(html, "https://mae.ro")
    assert s["conducere"] == "https://mae.ro/minister/conducere/"
    assert s["declaratii"] == "https://mae.ro/node/5104"
    assert "transparenta" not in s


def test_find_declaration_links():
    html = (
        '<a href="/docs/Declaratie_avere_2024.pdf">Declaratie de avere</a>'
        '<a href="/contact">Contact</a>'
        '<a href="/rapoarte/raport.pdf">Raport anual</a>'
    )
    links = find_declaration_links(html, "https://ms.ro")
    assert links == ["https://ms.ro/docs/Declaratie_avere_2024.pdf"]
