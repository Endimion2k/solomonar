"""Connector audit/dna — DNA comunicate de presă (semnale anticorupție). dna.ro (JSF .xhtml).

Comunicatele (rechizitorii, trimiteri în judecată) sunt semnale pe persoane/instituții.
Structura validată pe URL-uri REALE (dna.ro): `comunicat.xhtml?id=N`.
Notă fetch: www.pna.ro dă SSL error la clientul standard; dna.ro (ținta redirect-ului) e ținta.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin

from romega_core.http import Client

BASE = "https://www.dna.ro"
LIST_URL = BASE + "/comunicate.xhtml"
RE_COM = re.compile(r"comunicat\.xhtml\?id=(\d+)")


def extract_comunicate(hrefs: list[str], base: str = BASE) -> list[dict]:
    """Din linkuri (firecrawl/HTML) → [{id, url}] pentru comunicatele DNA."""
    out: list[dict] = []
    seen: set[int] = set()
    for h in hrefs:
        m = RE_COM.search(h or "")
        if not m:
            continue
        cid = int(m.group(1))
        if cid in seen:
            continue
        seen.add(cid)
        out.append({"id": cid, "url": urljoin(base + "/", f"comunicat.xhtml?id={cid}")})
    return out


class DnaConnector:
    source_id = "dna"

    def __init__(self, client: Client | None = None) -> None:
        self.client = client or Client()

    def fetch_comunicate(self) -> list[dict]:  # pragma: no cover - live/SSL
        from romega_core.parse import selector

        content, _ = self.client.fetch(LIST_URL, self.source_id, ext=".html")
        hrefs = selector(content).css("a::attr(href)").getall()
        return extract_comunicate(hrefs)
