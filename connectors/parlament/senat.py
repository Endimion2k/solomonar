"""Connector parlament/senat — Senatul României (senat.ro).

Context (research iunie 2026): senat.ro e ASP.NET WebForms, chei GUID, FĂRĂ open data
(doar HTML) → scrape. NU împarte ID-uri cu cdep.ro → crosswalk pe nume + dată naștere.

`to_person` realizează **unificarea bicamerală**: o persoană care a fost și deputat și
senator se rezolvă la un singur `romega_id` (prin PersonRegistry), purtând ambele ID-uri
externe (cdep + senat).

ATENȚIE: selectorii reflectă structura cunoscută; de validat pe HTML live pe runner-ul RO.
Testele rulează pe fixture sintetic reprezentativ.
"""

from __future__ import annotations

import re
from datetime import date
from urllib.parse import parse_qs, urljoin, urlparse

from pydantic import BaseModel

from romega_core.dates import RE_BIRTH, parse_ro_date
from romega_core.http import Client
from romega_core.models import Person
from romega_core.names import fix_ro_diacritics
from romega_core.parse import selector
from romega_core.provenance import SourceRef
from romega_core.resolve import PersonRegistry

BASE = "https://www.senat.ro"
LIST_URL = BASE + "/FisaSenatori.aspx"
PROFILE_URL = BASE + "/FisaSenator.aspx?ParlamentarID={guid}"

# Grupul POLITIC: "Grupul parlamentar al [partid]" (real) sau "Grupul parlamentar: X" (fixture).
# Exclude grupurile "de prietenie" (cerând `al`/`:` imediat după "parlamentar").
RE_PARTY = re.compile(
    r"Grupul\s+parlamentar\s*(?:al\s+|:\s*)(.+?)"
    r"(?:\s+Biroul|\s+Comisii|\s+Istoric|\s+Delega|\s+Grupuri|\s{2,}|$)",
    re.IGNORECASE,
)
# senat.ro pune în <title> prefixul "Senatul României - Prenume NUME".
RE_TITLE_PREFIX = re.compile(r"^.*?Senatul\s+Rom[âa]niei\s*-\s*", re.IGNORECASE)


class SenatSenator(BaseModel):
    senat_guid: str
    name: str
    birth_date: date | None = None
    judet: str | None = None
    party: str | None = None
    legislatura: int = 2024
    profile_url: str | None = None


def _extract_guid(href: str) -> str | None:
    q = parse_qs(urlparse(href).query)
    for key in ("ParlamentarID", "parlamentarid", "ParlamentarId"):
        if key in q:
            return q[key][0]
    return None


def parse_senators(html: bytes | str, base: str = BASE) -> list[dict]:
    """Parsează lista de senatori → [{guid, name, profile_url}]."""
    sel = selector(html)
    out: list[dict] = []
    seen: set[str] = set()
    for a in sel.css("a"):
        href = a.attrib.get("href", "")
        if "FisaSenator.aspx" not in href:
            continue
        guid = _extract_guid(href)
        if not guid or guid in seen:
            continue
        name = " ".join(" ".join(a.css("::text").getall()).split())
        if not name:
            continue
        seen.add(guid)
        out.append({"guid": guid, "name": name, "profile_url": urljoin(base + "/", href)})
    return out


def parse_senator_profile(
    html: bytes | str, guid: str, leg: int = 2024, url: str | None = None
) -> SenatSenator:
    sel = selector(html)
    raw_title = (sel.css("title::text").get() or "").strip()
    name = fix_ro_diacritics(RE_TITLE_PREFIX.sub("", raw_title).strip() or raw_title)
    text = re.sub(r"\s+", " ", " ".join(sel.css("body *::text").getall())).strip()

    birth_date = None
    if (m := RE_BIRTH.search(text)) is not None:
        birth_date = parse_ro_date(*m.groups())

    party = None
    if (m := RE_PARTY.search(text)) is not None:
        party = fix_ro_diacritics(m.group(1).strip())

    return SenatSenator(
        senat_guid=guid,
        name=name,
        birth_date=birth_date,
        party=party,
        legislatura=leg,
        profile_url=url or PROFILE_URL.format(guid=guid),
    )


def to_person(
    sen: SenatSenator, registry: PersonRegistry, source: SourceRef | None = None
) -> Person:
    """Mapează un Senator → Person canonic. Unifică bicameral prin PersonRegistry."""
    match = registry.resolve(
        sen.name,
        birth_date=sen.birth_date,
        external_ids={"senat": sen.senat_guid},
    )
    return Person(
        romega_id=match.romega_id,
        full_name=sen.name,
        aliases=[sen.name],
        birth_date=sen.birth_date,
        county=sen.judet,
        external_ids={"senat": [sen.senat_guid]},
        sources=[source] if source else [],
    )


class SenatConnector:
    """Arhetip `scrape`. fetch live necesită runner self-hosted RO (senat.ro geo-blochează)."""

    source_id = "senat"

    def __init__(self, client: Client | None = None, leg: int = 2024) -> None:
        self.client = client or Client()
        self.leg = leg

    def list_senators(self) -> list[dict]:
        content, _ = self.client.fetch(LIST_URL, self.source_id, ext=".html")
        return parse_senators(content)
