"""Teste pentru hardening: provenance atașat (#2) + diacritice de afișare (#3)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from connectors.parlament.cdep import parse_profile, to_person
from solomonar_core.names import fix_ro_diacritics
from solomonar_core.provenance import SourceRef
from solomonar_core.resolve import PersonRegistry

FIX = Path(__file__).parent / "fixtures"


def test_fix_ro_diacritics():
    assert fix_ro_diacritics("Bucureşti") == "București"  # ş cedilă -> ș virgulă
    assert fix_ro_diacritics("Dumitriţa") == "Dumitrița"  # ţ cedilă -> ț virgulă
    assert fix_ro_diacritics("Ștefan") == "Ștefan"  # deja corect, neschimbat


def test_county_diacritics_normalized():
    dep = parse_profile((FIX / "deputat_189.html").read_bytes(), idm=189)
    if dep.judet:  # dacă circumscripția a fost extrasă
        assert "ş" not in dep.judet and "ţ" not in dep.judet


def test_provenance_attached_when_source_given():
    dep = parse_profile((FIX / "deputat_189.html").read_bytes(), idm=189)
    reg = PersonRegistry()
    src = SourceRef(
        source_id="cdep",
        source_url="https://www.cdep.ro/...mp?idm=189",
        fetched_at=datetime(2026, 6, 1, 4, 0, 0),
        bronze_sha256="deadbeef",
    )
    p = to_person(dep, reg, source=src)
    assert len(p.sources) == 1
    assert p.sources[0].source_id == "cdep"
    assert p.sources[0].bronze_sha256 == "deadbeef"


def test_no_provenance_when_source_omitted():
    dep = parse_profile((FIX / "deputat_189.html").read_bytes(), idm=189)
    p = to_person(dep, PersonRegistry())
    assert p.sources == []
