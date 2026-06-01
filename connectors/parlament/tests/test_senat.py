"""Teste connector Senat — parsare listă/profil + UNIFICARE BICAMERALĂ (deputat = senator)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from connectors.parlament.cdep import parse_profile as cdep_parse
from connectors.parlament.cdep import to_person as cdep_to_person
from connectors.parlament.senat import (
    parse_senator_profile,
    parse_senators,
    to_person as senat_to_person,
)
from romega_core.resolve import MatchStatus, PersonRegistry

FIX = Path(__file__).parent / "fixtures"


def test_parse_senators_list():
    sens = parse_senators((FIX / "senat_list.html").read_text(encoding="utf-8"))
    guids = {s["guid"] for s in sens}
    assert guids == {
        "11111111-1111-1111-1111-111111111111",
        "22222222-2222-2222-2222-222222222222",
    }
    assert any(s["name"] == "POPESCU Ion" for s in sens)
    assert all(s["profile_url"].startswith("https://www.senat.ro/") for s in sens)


def test_parse_senator_profile():
    sen = parse_senator_profile(
        (FIX / "senat_profile.html").read_text(encoding="utf-8"), guid="S-189"
    )
    assert sen.name == "Mihaiu Radu-Nicolae"
    assert sen.birth_date == date(1977, 9, 8)
    assert sen.party == "USR"
    assert sen.senat_guid == "S-189"


def test_bicameral_unification():
    """Aceeași persoană, văzută ca deputat (cdep) ȘI senator (senat) -> UN singur romega_id."""
    reg = PersonRegistry()

    # 1) ca deputat (HTML real)
    dep = cdep_parse((FIX / "deputat_189.html").read_bytes(), idm=189)
    p_dep = cdep_to_person(dep, reg)

    # 2) ca senator (același nume + dată naștere, GUID diferit)
    sen = parse_senator_profile((FIX / "senat_profile.html").read_text(encoding="utf-8"), guid="S-189")
    p_sen = senat_to_person(sen, reg)

    # ACEEAȘI persoană — o singură entitate în registru
    assert p_dep.romega_id == p_sen.romega_id
    assert len(reg) == 1

    # Ambele ID-uri externe duc la același romega_id (crosswalk bicameral)
    assert reg.resolve("x", external_ids={"cdep": "189"}).status == MatchStatus.MATCHED
    assert reg.resolve("x", external_ids={"cdep": "189"}).romega_id == p_dep.romega_id
    assert reg.resolve("y", external_ids={"senat": "S-189"}).romega_id == p_dep.romega_id


def test_distinct_senators_stay_separate():
    reg = PersonRegistry()
    a = senat_to_person(
        parse_senator_profile("<title>POPESCU Ion</title><body>n. 1 ian. 1960</body>", "G1"), reg
    )
    b = senat_to_person(
        parse_senator_profile("<title>IONESCU Maria</title><body>n. 2 feb. 1975</body>", "G2"), reg
    )
    assert a.romega_id != b.romega_id
    assert len(reg) == 2
