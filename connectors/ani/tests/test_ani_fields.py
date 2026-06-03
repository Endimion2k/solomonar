"""Test normalizare fields ANI (API deschis — organizații care depun declarații)."""

from __future__ import annotations

from connectors.ani.declaratii import normalize_ani_organizations


def test_normalize_ani_organizations():
    raw = [
        {"id": 11341, "numeOrganizatie": "A.D.P.P. CARACAL SRL"},
        {"id": 1, "numeOrganizatie": ""},          # gol — ignorat
        {"id": 2, "numeOrganizatie": "  Primaria X  "},  # trim
    ]
    out = normalize_ani_organizations(raw)
    assert len(out) == 2
    assert out[0] == {"ani_id": 11341, "name": "A.D.P.P. CARACAL SRL"}
    assert out[1]["name"] == "Primaria X"
