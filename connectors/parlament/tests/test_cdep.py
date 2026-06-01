"""Test de portare cdep — parsează HTML REAL (fixture deputat_189) și mapează la canonic."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from connectors.parlament.cdep import parse_profile, to_person
from romega_core.resolve import MatchStatus, PersonRegistry

FIX = Path(__file__).parent / "fixtures"


def test_parse_real_profile_fixture():
    html = (FIX / "deputat_189.html").read_bytes()
    dep = parse_profile(html, idm=189)
    assert dep.cdep_idm == 189
    assert dep.name == "Mihaiu Radu-Nicolae"
    assert dep.family_name == "Mihaiu"
    assert dep.given_name == "Radu-Nicolae"
    assert dep.birth_date == date(1977, 9, 8)  # "n. 8 sep. 1977"


def test_to_person_assigns_id_and_crosswalk():
    html = (FIX / "deputat_189.html").read_bytes()
    dep = parse_profile(html, idm=189)
    reg = PersonRegistry()

    p = to_person(dep, reg)
    assert p.romega_id.startswith("p:")
    assert p.full_name == "Mihaiu Radu-Nicolae"
    assert p.external_ids["cdep"] == ["189"]

    # Aceeași persoană văzută din altă sursă cu cdep_idm=189 -> match prin crosswalk
    again = reg.resolve("Nume Scris Complet Diferit", external_ids={"cdep": "189"})
    assert again.status == MatchStatus.MATCHED
    assert again.romega_id == p.romega_id
