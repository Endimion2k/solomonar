"""harvest_guvernanta.build: normalizare + legare de graf + comparație ONRC, pe un registru sintetic."""

from __future__ import annotations

import pytest

from pipeline import harvest_guvernanta as hg

REG = {
    "generated_at": "2026-09-25T12:00:00Z", "published_at": "2026-09-25T14:00:00Z",
    "institutions": [
        {"id": "i1", "name": "Alfa SA", "cui": "RO111", "supervising_authority": "Ministerul X",
         "website_url": "https://alfa.ro",
         "assets": {"annual_remuneration_reports": [{"name": "RAR Alfa.pdf", "url": "CUI/111/RAR Alfa.pdf"}]}},
        {"id": "i2", "name": "Beta SA", "cui": "222", "supervising_authority": "Ministerul Y", "assets": {}},
    ],
    "people": [
        {"id": "p1", "full_name": "Ion Popescu"},       # în graf la Alfa → confirmat
        {"id": "p2", "full_name": "Maria Ionescu"},     # în graf, dar la altă firmă → candidat
        {"id": "p3", "full_name": "Dan Vasile"},        # doi omonimi în graf → nelegat
    ],
    "appointments": [
        {"id": "a1", "institution_id": "i1", "person_id": "p1",
         "role": {"label": "Președintele CA", "category": "board_chair"},
         "political_affiliation": "Fără apartenenţă politică",
         "compensation": {"gross_ron": 15000}, "mandate_end_date": "2027-01-01",
         "cv": {"local_url": "CUI/111/CV Ion Popescu.pdf"}},
        {"id": "a2", "institution_id": "i2", "person_id": "p1",
         "role": {"label": "Membru CA", "category": "board_member"}, "political_affiliation": "PSD",
         "compensation": {"gross_ron": 10000}, "cv": {}},
        {"id": "a3", "institution_id": "i1", "person_id": "p2",
         "role": {"label": "Director General", "category": "executive_director"},
         "political_affiliation": None, "compensation": {}, "cv": {}},
        {"id": "a4", "institution_id": "i2", "person_id": "p3",
         "role": {"label": "Membru CA", "category": "board_member"}, "political_affiliation": "PNL",
         "compensation": {"gross_ron": 9000}, "cv": {}},
    ],
}

GOLD = {"persoane": [
    {"romega_id": "g:1", "nume_key": "ion popescu", "companii": [{"cui": 111}]},
    {"romega_id": "g:2", "nume_key": "ionescu maria", "companii": [{"cui": 999}]},
    {"romega_id": "g:3", "nume_key": "dan vasile", "companii": []},
    {"romega_id": "g:4", "nume_key": "vasile dan", "companii": [{"cui": 5}]},
]}
ONRC = {"companii": [{"cui": 111, "reprezentanti": [
    {"nume": "POPESCU ION", "calitate": "administrator"},
    {"nume": "GEORGESCU ANA", "calitate": "administrator"},
    {"nume": "CONTINSOLV SPRL", "calitate": "lichidator"},
]}]}


@pytest.fixture
def out(monkeypatch):
    files = {"graf/persoane_gold.json": GOLD, "companii/reprezentanti.json": ONRC,
             "companii/_index.json": {"data": [{"cui": 111, "name": "ALFA SA"}]}}
    monkeypatch.setattr(hg, "_load", lambda rel: files.get(rel, {}))
    return hg.build(REG)


def test_counts_and_meta(out):
    assert (out["n_companii"], out["n_numiri"], out["n_persoane"]) == (2, 4, 3)
    assert out["source_generated_at"] == "2026-09-25T12:00:00Z"


def test_person_matching(out):
    by = {n["id"]: n for n in out["numiri"]}
    assert (by["a1"]["romega_id"], by["a1"]["potrivire"]) == ("g:1", "confirmat")   # nume + aceeași firmă
    assert (by["a3"]["romega_id"], by["a3"]["potrivire"]) == ("g:2", "candidat")    # nume unic, altă firmă
    assert by["a4"]["romega_id"] is None and by["a4"]["n_omonimi_graf"] == 2         # omonimi → nelegat


def test_normalization(out):
    by = {n["id"]: n for n in out["numiri"]}
    assert by["a1"]["partid"] == hg.FARA_PARTID                    # cedilă → virgulă
    assert by["a1"]["cui"] == 111                                    # „RO111” → 111
    assert by["a1"]["cv_url"] == "https://guvernanta.gov.ro/CUI/111/CV%20Ion%20Popescu.pdf"
    alfa = next(c for c in out["companii"] if c["cui"] == 111)
    assert alfa["in_solomonar"] and alfa["rapoarte_remunerare"][0]["url"].endswith("RAR%20Alfa.pdf")
    assert out["afiliere_politica"]["PSD"] == 1 and out["afiliere_politica"]["nedeclarat"] == 1


def test_onrc_comparison_and_cumul(out):
    alfa = next(c for c in out["companii"] if c["cui"] == 111)
    cmp = alfa["comparatie_onrc"]
    assert cmp["comune"] == 1                                        # Popescu (ordine inversă a numelui)
    assert cmp["doar_oficial"] == ["Maria Ionescu"]
    assert cmp["doar_onrc"] == ["Georgescu Ana"]                     # lichidatorul SPRL e exclus
    assert [c["nume"] for c in out["cumul"]] == ["Ion Popescu"]
    assert out["cumul"][0]["brut_lunar_total_ron"] == 25000
