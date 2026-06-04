"""Connector companii/companiidestat — agregator independent (1.247 SOE, central + LOCAL).

Sursa care ACOPERĂ și companiile de stat LOCALE (pe care AMEPIP nu le listează individual).
API JSON: companiidestat.ro/api/v1/companii_search.json (keyed pe CUI). Complementează AMEPIP.
Tier (clasificarea lor): 1 ≈ central; 2–4 ≈ local. Conține județ, sector, status, listare BVB.
"""

from __future__ import annotations

import json

from romega_core.http import Client
from romega_core.models import Company
from romega_core.provenance import SourceRef

URL = "https://companiidestat.ro/api/v1/companii_search.json"


def _to_int(v) -> int | None:
    try:
        return int(str(v).strip())
    except (ValueError, TypeError):
        return None


def parse_companiidestat(data: dict) -> list[dict]:
    """Parsează răspunsul API → înregistrări SOE (cui, nume, județ, sector, status, central/local)."""
    out: list[dict] = []
    for key, c in (data.get("companii") or {}).items():
        if not isinstance(c, dict):
            continue
        cui = _to_int(c.get("cui") or key)
        if not cui:
            continue
        tier = str(c.get("tier") or "")
        out.append({
            "cui": cui,
            "nume": (c.get("nume") or "").strip(),
            "judet": c.get("judet_nume"),
            "sector": c.get("sector_label"),
            "status": c.get("derived_status"),
            "listat_bvb": str(c.get("listat_bvb")) in ("True", "true", "1"),
            "tier_cds": tier,
            "central": tier == "1",
        })
    return out


def to_companies(records: list[dict], source: SourceRef | None = None) -> list[Company]:
    return [
        Company(
            romega_id=Company.id_for_cui(r["cui"]),
            cui=r["cui"],
            name=r["nume"],
            is_soe=True,
            sources=[source] if source else [],
        )
        for r in records
    ]


class CompaniiDeStatConnector:
    source_id = "companiidestat"

    def __init__(self, client: Client | None = None) -> None:
        self.client = client or Client()

    def fetch_all(self) -> list[dict]:
        content, _ = self.client.fetch(URL, self.source_id, ".json")
        return parse_companiidestat(json.loads(content))
