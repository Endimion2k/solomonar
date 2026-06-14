"""Connector audit/curteadeconturi — Curtea de Conturi (rapoarte de audit → semnale).

Validat pe HTML REAL (curteadeconturi.ro, fetch live). Extrage linkurile de rapoarte de audit
(financiar / conformitate / performanță / public anual). Rapoartele leagă instituții & SOE de
constatări → semnale de risc pentru graf. Vezi docs/03-SOURCES.md §D4.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin

from solomonar_core.http import Client
from solomonar_core.parse import selector

BASE = "https://www.curteadeconturi.ro"
RE_REPORT = re.compile(r"/rapoarte-de-audit|/raport(?:-|/)", re.IGNORECASE)


def parse_audit_links(html: bytes | str, base: str = BASE) -> list[dict]:
    """Extrage linkurile de rapoarte de audit dintr-o pagină Curtea de Conturi → [{title, url}]."""
    sel = selector(html)
    out: list[dict] = []
    seen: set[str] = set()
    for a in sel.css("a"):
        href = a.attrib.get("href", "")
        if not href or not RE_REPORT.search(href):
            continue
        url = urljoin(base + "/", href)
        if url in seen:
            continue
        seen.add(url)
        title = " ".join(t.strip() for t in a.css("::text").getall() if t.strip())
        out.append({"title": title, "url": url})
    return out


class CurteaDeConturiConnector:
    source_id = "ccr"

    def __init__(self, client: Client | None = None) -> None:
        self.client = client or Client()

    def fetch_audit_links(self) -> list[dict]:
        content, _ = self.client.fetch(BASE, self.source_id, ext=".html")
        return parse_audit_links(content)
