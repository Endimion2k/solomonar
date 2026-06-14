"""Teste smoke pentru modelele canonice + provenance."""

from __future__ import annotations

from datetime import datetime

from solomonar_core.models import (
    Company,
    CompanyStatus,
    Edge,
    EdgeType,
    Organization,
    OrgType,
    Person,
    Tier,
    make_id,
)
from solomonar_core.provenance import SourceRef


def _src() -> SourceRef:
    return SourceRef(
        source_id="anaf_api",
        source_url="https://webservicesp.anaf.ro/...",
        fetched_at=datetime(2026, 6, 1, 4, 0, 0),
        bronze_sha256="abc123",
    )


def test_make_id_deterministic():
    assert make_id("c", 14056826) == make_id("c", 14056826)
    assert make_id("c", 1) != make_id("c", 2)
    assert make_id("c", 14056826).startswith("c:")


def test_company_id_for_cui():
    assert Company.id_for_cui(14056826) == make_id("c", 14056826)


def test_person_roundtrip_json():
    p = Person(
        romega_id="p:deadbeef",
        full_name="Ion Popescu",
        aliases=["POPESCU Ion"],
        external_ids={"cdep": ["123"]},
        sources=[_src()],
    )
    data = p.model_dump_json()
    again = Person.model_validate_json(data)
    assert again.romega_id == "p:deadbeef"
    assert again.external_ids["cdep"] == ["123"]
    assert again.sources[0].source_id == "anaf_api"


def test_company_and_org_enums():
    c = Company(
        romega_id=Company.id_for_cui(14056826),
        cui=14056826,
        name="S.N.G.N. ROMGAZ S.A.",
        is_soe=True,
        status=CompanyStatus.ACTIVE,
        sources=[_src()],
    )
    assert c.is_soe is True
    # use_enum_values=True -> serializat ca string
    assert c.status == "active"

    o = Organization(
        romega_id="o:energie",
        name="Ministerul Energiei",
        type=OrgType.MINISTRY,
        tier=Tier.CENTRAL,
        domain="energie.gov.ro",
    )
    assert o.type == "ministry"


def test_edge():
    e = Edge(src="o:stat", dst="c:romgaz", type=EdgeType.CONTROLS, props={"role": "APT"})
    assert e.type == "CONTROLS"
