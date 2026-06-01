"""Seed ilustrativ de companii de stat majore (CUI + autoritate tutelară).

NU înlocuiește master list-ul AMEPIP (Anexa 1, ~1.320 SOE) — care se extrage din PDF pe runner.
Acest seed dă date reale pentru companiile mari (energie/transport) ca stratul de companii +
graful CONTROLS să fie populat și demonstrabil. CUI-urile se verifică LIVE prin ANAF la build.
"""

from __future__ import annotations

from romega_core.models import Company
from romega_core.provenance import SourceRef

SOE_SEED = [
    {"cui": 14056826, "name": "S.N.G.N. Romgaz S.A.", "tutelary": "Ministerul Energiei"},
    {"cui": 13267213, "name": "S.P.E.E.H. Hidroelectrica S.A.", "tutelary": "Ministerul Energiei"},
    {"cui": 10874881, "name": "S.N. Nuclearelectrica S.A.", "tutelary": "Ministerul Energiei"},
    {"cui": 13068733, "name": "S.N.T.G.N. Transgaz S.A.", "tutelary": "Ministerul Energiei"},
    {"cui": 13328043, "name": "C.N.T.E.E. Transelectrica S.A.", "tutelary": "Ministerul Energiei"},
    {"cui": 1350020, "name": "Conpet S.A.", "tutelary": "Ministerul Energiei"},
    {"cui": 1914163, "name": "Oil Terminal S.A.", "tutelary": "Ministerul Energiei"},
]


def seed_companies(source: SourceRef | None = None) -> list[Company]:
    return [
        Company(
            romega_id=Company.id_for_cui(s["cui"]),
            cui=s["cui"],
            name=s["name"],
            is_soe=True,
            tutelary_authority=s["tutelary"],
            sources=[source] if source else [],
        )
        for s in SOE_SEED
    ]
