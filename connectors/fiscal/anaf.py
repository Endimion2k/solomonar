"""Connector fiscal/anaf — API public ANAF (date firmă după CUI).

Arhetip `api`. Endpoint REST, POST, JSON, fără auth. Limite: 100 CUI/request, 1 req/s.
Doc: https://static.anaf.ro/static/10/Anaf/Informatii_R/Servicii_web/doc_WS_V8.txt

Întoarce, per CUI: denumire, nrRegCom, CAEN, status TVA, inactiv, e-Factura etc.
Sursă gratuită și programatică — coloana vertebrală pentru îmbogățirea companiilor (Faza 3).
"""

from __future__ import annotations

from solomonar_core.http import Client
from solomonar_core.models import Company, CompanyStatus
from solomonar_core.provenance import SourceRef

# Endpoint v9 (verificat live iunie 2026). Atenție: calea v8 documentată dă 404 — v9 are
# structură diferită: /api/PlatitorTvaRest/v9/tva (nu /PlatitorTvaRest/api/v8/ws/tva).
URL = "https://webservicesp.anaf.ro/api/PlatitorTvaRest/v9/tva"


def anaf_lookup(cuis: list[int], data: str, client: Client | None = None) -> list[dict]:
    """Interoghează ANAF pentru o listă de CUI-uri la o dată dată. Întoarce lista `found`."""
    if len(cuis) > 100:
        raise ValueError("ANAF acceptă maxim 100 CUI per request")
    client = client or Client()
    payload = [{"cui": int(c), "data": data} for c in cuis]
    resp = client.post(URL, json=payload)
    resp.raise_for_status()
    return resp.json().get("found", [])


def _status(entry: dict) -> CompanyStatus:
    inactiv = entry.get("stare_inactiv") or {}
    if inactiv.get("statusInactivi"):
        return CompanyStatus.INACTIVE
    stare = ((entry.get("date_generale") or {}).get("stare_inregistrare") or "").upper()
    if "RADIAT" in stare:
        return CompanyStatus.RADIATA
    if "INREGISTRAT" in stare or "INREGISTRARE" in stare:
        return CompanyStatus.ACTIVE
    return CompanyStatus.UNKNOWN


def to_company(entry: dict, *, is_soe: bool = False, source: SourceRef | None = None) -> Company:
    """Mapează un răspuns ANAF `found[i]` → Company canonic (cheie naturală CUI)."""
    dg = entry.get("date_generale") or {}
    tva = entry.get("inregistrare_scop_Tva") or {}
    cui = int(dg.get("cui"))
    return Company(
        romega_id=Company.id_for_cui(cui),
        cui=cui,
        name=(dg.get("denumire") or "").strip(),
        reg_com=(dg.get("nrRegCom") or "").strip() or None,
        caen=(dg.get("cod_CAEN") or "").strip() or None,
        status=_status(entry),
        vat_payer=tva.get("scpTVA"),
        is_soe=is_soe,
        sources=[source] if source else [],
    )


class AnafConnector:
    """Arhetip `api`. Îmbogățește companii după CUI (status, CAEN, TVA, inactiv)."""

    source_id = "anaf_api"

    def __init__(self, client: Client | None = None, snapshot_date: str = "2024-07-02") -> None:
        self.client = client or Client()
        self.date = snapshot_date

    def enrich(self, cuis: list[int]) -> list[Company]:
        out: list[Company] = []
        for i in range(0, len(cuis), 100):  # batch de 100 (limita ANAF)
            out.extend(to_company(e) for e in anaf_lookup(cuis[i : i + 100], self.date, self.client))
        return out
