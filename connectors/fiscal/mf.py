"""Connector fiscal/mf — situații financiare (bilanțuri) bulk de pe data.gov.ro.

Sursa gratuită pentru financiarele companiilor la scară (alternativă la scraping MFinante).
Format: TXT (date) + CSV (schema coloane), keyed pe CUI. Vezi docs/03-SOURCES.md §F2.
Discovery prin CKAN (live); parserul e tolerant (numele exact al coloanelor vine din schema CSV).
"""

from __future__ import annotations

from connectors.opendata.datagov import CkanClient
from solomonar_core.models import FinancialYear


def _to_int(v) -> int | None:
    try:
        return int(float(str(v).strip().replace(" ", "").replace(",", ".")))
    except (ValueError, TypeError):
        return None


def _to_float(v) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(" ", "")
    if not s:
        return None
    if "." in s and "," in s:
        s = s.replace(".", "").replace(",", ".") if s.rindex(",") > s.rindex(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".") if len(s.split(",")[-1]) <= 2 else s.replace(",", "")
    elif "." in s:
        parts = s.split(".")
        if len(parts) > 2 or (len(parts) == 2 and len(parts[-1]) == 3):
            s = s.replace(".", "")  # puncte = separator de mii
    try:
        return float(s)
    except ValueError:
        return None


def parse_financials_rows(rows: list[dict], year: int, cui_key: str = "cui") -> dict[int, FinancialYear]:
    """Mapează rânduri de bilanț → {cui: FinancialYear} (tolerant la denumiri de coloane)."""
    out: dict[int, FinancialYear] = {}
    for row in rows:
        r = {(k or "").strip().lower(): v for k, v in row.items()}
        cui = _to_int(r.get(cui_key) or r.get("cui"))
        if not cui:
            continue
        out[cui] = FinancialYear(
            year=year,
            turnover_ron=_to_float(r.get("cifra_afaceri") or r.get("cifra_de_afaceri") or r.get("turnover")),
            profit_ron=_to_float(r.get("profit_net") or r.get("profit") or r.get("rezultat_net")),
            employees=_to_int(r.get("nr_mediu_salariati") or r.get("numar_salariati") or r.get("employees")),
        )
    return out


class MfConnector:
    source_id = "mf_bilanturi"

    def __init__(self, ckan: CkanClient | None = None) -> None:
        self.ckan = ckan or CkanClient()

    def discover(self, year: int) -> list[dict]:
        """Caută dataset-urile situatii_financiare_{an} (live, prin CKAN)."""
        return self.ckan.package_search(f"situatii financiare {year}", rows=5)
