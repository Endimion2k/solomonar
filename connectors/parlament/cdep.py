"""Connector parlament/cdep — portare a scraperului de deputați din cdep-api-poc pe solomonar_core.

Diferențe față de original (scrapers/deputati.py):
- folosește solomonar_core.http.Client (throttle per-host + bronze) în loc de _http global;
- mapează `Deputat` (model cdep) → `Person` canonic prin PersonRegistry (romega_id + crosswalk);
- parsarea de date RO e factorizată în solomonar_core.dates (partajat cu connectorul senat);
- normalizează diacriticele de afișare (cedilă → virgulă-jos) și atașează provenance (SourceRef).

Regexurile și logica de parsare sunt păstrate fidel (parsare identică pe HTML-ul cdep.ro).
"""

from __future__ import annotations

import re
from datetime import date

from parsel import Selector
from pydantic import BaseModel

from solomonar_core.dates import RE_BIRTH, parse_ro_date
from solomonar_core.http import Client
from solomonar_core.models import Person
from solomonar_core.names import fix_ro_diacritics
from solomonar_core.parse import selector
from solomonar_core.provenance import SourceRef
from solomonar_core.resolve import PersonRegistry

BASE = "https://www.cdep.ro"
LIST_URL = BASE + "/ords/pls/parlam/structura2015.de?cam={cam}&leg={leg}&idl=1"
PROFILE_URL = BASE + "/ords/pls/parlam/structura2015.mp?idm={idm}&cam={cam}&leg={leg}"

# --- Regex cdep-specifice (RE_BIRTH e în solomonar_core.dates) ---
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


def _clean_text(sel: Selector) -> str:
    return re.sub(r"\s+", " ", " ".join(sel.css("body *::text").getall())).strip()


def parse_profile(html: bytes | str, idm: int, leg: int = 2024, url: str | None = None) -> CdepDeputat:
    """Parsează o pagină de profil cdep.ro → CdepDeputat (portare fidelă)."""
    sel = selector(html)
    name = fix_ro_diacritics((sel.css("title::text").get() or "").strip())
    text = _clean_text(sel)

    birth_date = None
    if (m := RE_BIRTH.search(text)) is not None:
        birth_date = parse_ro_date(*m.groups())

    judet = circumscriptie = None
    if (m := RE_CIRC.search(text)) is not None:
        circumscriptie = int(m.group(1))
        judet = fix_ro_diacritics(m.group(2).strip().title())

    current_party = None
    if (m := RE_PARTY.search(text)) is not None:
        current_party = fix_ro_diacritics(m.group(1).strip(" -"))

    current_group = None
    if (m := RE_GROUP.search(text)) is not None:
        current_group = fix_ro_diacritics(m.group(1).strip())

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


def to_person(
    dep: CdepDeputat, registry: PersonRegistry, source: SourceRef | None = None
) -> Person:
    """Mapează un Deputat cdep → Person canonic, atribuind romega_id + crosswalk + provenance."""
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
        sources=[source] if source else [],
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
                        name = fix_ro_diacritics(
                            " ".join(" ".join(cells[1].css("*::text").getall()).split())
                        )
                        found[idm] = {"idm": idm, "name": name, "href": href}
                    break
        return list(found.values())
