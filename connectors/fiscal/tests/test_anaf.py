"""Teste connector ANAF — parsare răspuns (offline) + interogare reală (live, skip pe eroare)."""

from __future__ import annotations

import pytest

from connectors.fiscal.anaf import anaf_lookup, to_company

# Răspuns ANAF reprezentativ (forma reală a câmpurilor `found[i]`).
SAMPLE = {
    "date_generale": {
        "cui": 14056826,
        "denumire": "S.N.G.N. ROMGAZ S.A.",
        "nrRegCom": "J40/100/2001",
        "cod_CAEN": "0610",
        "stare_inregistrare": "INREGISTRAT",
    },
    "inregistrare_scop_Tva": {"scpTVA": True},
    "stare_inactiv": {"statusInactivi": False},
}


def test_to_company_from_anaf_response():
    c = to_company(SAMPLE, is_soe=True)
    assert c.cui == 14056826
    assert "ROMGAZ" in c.name.upper()
    assert c.reg_com == "J40/100/2001"
    assert c.caen == "0610"
    assert c.status == "active"
    assert c.vat_payer is True
    assert c.is_soe is True
    assert c.romega_id.startswith("c:")


def test_inactive_status():
    entry = {"date_generale": {"cui": 1}, "stare_inactiv": {"statusInactivi": True}}
    assert to_company(entry).status == "inactive"


def test_anaf_live_romgaz():
    """Interogare REALĂ ANAF pentru Romgaz (CUI 14056826). Skip dacă rețeaua e indisponibilă."""
    try:
        found = anaf_lookup([14056826], "2024-07-02")
    except Exception as e:  # pragma: no cover - depinde de rețea
        pytest.skip(f"ANAF live indisponibil: {e}")
    assert found, "ANAF nu a întors niciun rezultat pentru CUI 14056826"
    c = to_company(found[0])
    assert c.cui == 14056826
    assert "ROMGAZ" in c.name.upper()
