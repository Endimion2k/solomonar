"""Connector parlament/cdep — portare a scraperului de deputați din cdep-api-poc pe romega_core.

Diferențe față de original (scrapers/deputati.py):
- folosește romega_core.http.Client (throttle per-host + bronze) în loc de _http global;
- mapează `Deputat` (model cdep) → `Person` canonic prin PersonRegistry (romega_id + crosswalk).

Regexurile și logica de parsare sunt păstrate fidel (parsare identică pe HTML-ul cdep.ro).
"""

from __future__ import annotations

import re
from datetime import date

from pydantic import BaseModel
from parsel import Selector

from romega_core.http import Client
from romega_core.models import Person
from romega_core.parse import selector
from romega_core.resolve import PersonRegistry

BASE = "https://www.cdep.ro"
LIST_URL = BASE + "/ords/pls/parlam/structura2015.de?cam={cam}&leg={leg}&idl=1"
PROFILE_URL = BASE + "/ords/pls/parlam/structura2015.mp?idm={idm}&cam={cam}&leg={leg}"

# --- Regex portate identic din scrapers/deputati.py ---
RE_BIRTH = re.compile(r"n\.\s*(\d{1,2})\s+([a-zăâîşţșț\.]+)\s+(\d{4})", re.IGNORECASE)
RE_CIRC = re.compile(
    r"circumscripti(?:a|ia|ţia|ția)\s+electoral(?:a|ă)\s+nr\.\s*(\d+)\s+"
    r"([A-ZĂÂÎȘŞȚŢ\- ]+?)(?=\s+data|\s+Grup|\s+Forma|$)",
    re.IGNORECASE,
)
RE_PARTY = re.compile(r"Forma[ţt]iunea politic[ăa]:\s*-?\s*(.+?)\s+Grup", re.IGNORECASE)
RE_GROUP = re.compile(
    r"Grupul parlamentar:\s*(.+?)(?=\s+Comisii\s+permanente|\s+Comisii\s+speciale|"
    r"\s+Delega[ţt]ii|\s+Grupuri\s+de\s+prietenie|\s+Activitatea\s+parlamentar)",
    re.IGNORECASE,
)

ROMANIAN_MONTHS = {
    "ian": 1, "ianuarie": 1, "feb": 2, "februarie": 2, "mar": 3, "mart": 3, "martie": 3,
    "apr": 4, "aprilie": 4, "mai": 5, "iun": 6, "iunie": 6, "iul": 7, "iulie": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "septembrie": 9, "oct": 10, "octombrie": 10,
    "noi": 11, "nov": 11, "noiembrie": 11, "dec": 12, "decembrie": 12,
}


class CdepDeputat(BaseModel):
    """Subset relevant pentru rezoluție + profil canonic (Popolo-aligned)."""

    cdep_idm: int
    name: str
    given_name: str | None = None
    family_name: str | None = None
    birth_date: date | None = None
    gender: str | None = None
    judet: str | None = None
    circumscriptie: int | None = None
    current_party: str | None = None
    current_group: str | None = None
    legislatura: int = 2024
    profile_url: str | None = None


def _parse_ro_date(day_str: str, month_str: str, year_str: str) -> date | None:
    m = month_str.rstrip(".").lower().replace("ş", "s").replace("ţ", "t").replace("ș", "s").replace("ț", "t")
    month = ROMANIAN_MONTHS.get(m) or ROMANIAN_MONTHS.get(m[:3])
    if month is None:
        return None
    try:
        return date(int(year_str), month, int(day_str))
    except (ValueError, TypeError):
        return None


def _clean_text(sel: Selector) -> str:
    return re.sub(r"\s+", " ", " ".join(sel.css("body *::text").getall())).strip()


def parse_profile(html: bytes | str, idm: int, leg: int = 2024, url: str | None = None) -> CdepDeputat:
    """Parsează o pagină de profil cdep.ro → CdepDeputat (portare fidelă)."""
    sel = selector(html)
    name = (sel.css("title::text").get() or "").strip()
    text = _clean_text(sel)

    birth_date = None
    if (m := RE_BIRTH.search(text)) is not None:
        birth_date = _parse_ro_date(*m.groups())

    judet = circumscriptie = None
    if (m := RE_CIRC.search(text)) is not None:
        circumscriptie = int(m.group(1))
        judet = m.group(2).strip().title()

    current_party = None
    if (m := RE_PARTY.search(text)) is not None:
        current_party = m.group(1).strip(" -")

    current_group = None
    if (m := RE_GROUP.search(text)) is not None:
        current_group = m.group(1).strip()

    gender = None
    low = text.lower()
    if re.search(r"\baleasa\b", low) or re.search(r"\baleas[ăa]\b", low):
        gender = "female"
    elif re.search(r"\bales\b", low):
        gender = "male"

    parts = name.split()
    family_name = parts[0] if parts else None
    given_name = " ".join(parts[1:]) if len(parts) > 1 else None

    return CdepDeputat(
        cdep_idm=idm,
        name=name,
        given_name=given_name,
        family_name=family_name,
        birth_date=birth_date,
        gender=gender,
        judet=judet,
        circumscriptie=circumscriptie,
        current_party=current_party,
        current_group=current_group,
        legislatura=leg,
        profile_url=url or PROFILE_URL.format(idm=idm, cam=2, leg=leg),
    )


def to_person(dep: CdepDeputat, registry: PersonRegistry) -> Person:
    """Mapează un Deputat cdep → Person canonic, atribuind romega_id + crosswalk cdep_idm."""
    match = registry.resolve(
        dep.name,
        birth_date=dep.birth_date,
        external_ids={"cdep": str(dep.cdep_idm)},
    )
    return Person(
        romega_id=match.romega_id,
        full_name=dep.name,
        aliases=[dep.name],
        birth_date=dep.birth_date,
        county=dep.judet,
        external_ids={"cdep": [str(dep.cdep_idm)]},
    )


class CdepConnector:
    """Arhetip `scrape`. fetch live (necesită runner self-hosted în RO; cdep.ro geo-blochează)."""

    source_id = "cdep"

    def __init__(self, client: Client | None = None, leg: int = 2024, cam: int = 2) -> None:
        self.client = client or Client()
        self.leg = leg
        self.cam = cam

    def list_deputies(self) -> list[dict]:
        content, _ = self.client.fetch(
            LIST_URL.format(cam=self.cam, leg=self.leg), self.source_id, ext=".html"
        )
        sel = selector(content)
        found: dict[int, dict] = {}
        for table in sel.css("table"):
            for row in table.css("tr"):
                cells = row.css("td")
                if len(cells) < 2:
                    continue
                for href in cells[1].css("a::attr(href)").getall():
                    if "structura2015.mp" not in href:
                        continue
                    params = dict(re.findall(r"(\w+)=(\d+)", href))
                    idm = int(params.get("idm", 0))
                    if idm > 0 and idm not in found:
                        name = " ".join(" ".join(cells[1].css("*::text").getall()).split())
                        found[idm] = {"idm": idm, "name": name, "href": href}
                    break
        return list(found.values())
