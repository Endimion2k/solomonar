"""Connector opendata/datagov — client CKAN reutilizabil pentru data.gov.ro.

Portalul național de date deschise (~5.000+ dataset-uri). API CKAN Action.
Folosit pentru bugete, salarii sector public, dump ONRC, situații financiare etc.
Vezi docs/03-SOURCES.md §K.
"""

from __future__ import annotations

from urllib.parse import urlencode

from solomonar_core.http import Client

BASE = "https://data.gov.ro/api/3/action"


class CkanClient:
    def __init__(self, client: Client | None = None) -> None:
        self.client = client or Client()

    def _get(self, action: str, **params) -> dict:
        url = f"{BASE}/{action}"
        if params:
            url += "?" + urlencode(params)
        r = self.client.get(url)
        r.raise_for_status()
        return r.json()

    def package_search(self, q: str, rows: int = 20) -> list[dict]:
        return (self._get("package_search", q=q, rows=rows).get("result") or {}).get("results", [])

    def package_show(self, package_id: str) -> dict:
        return self._get("package_show", id=package_id).get("result") or {}

    def organization_list(self) -> list[str]:
        return self._get("organization_list").get("result", [])


def parse_resources(package: dict) -> list[dict]:
    """Extrage resursele unui pachet CKAN (name, url, format normalizat)."""
    return [
        {
            "name": x.get("name"),
            "url": x.get("url"),
            "format": (x.get("format") or "").upper(),
        }
        for x in package.get("resources", [])
    ]


def discover_datasets(query: str, ckan: CkanClient | None = None, rows: int = 15) -> list[dict]:
    """Caută dataset-uri după cuvânt-cheie (ex. 'buget', 'salarii'). Întoarce id+titlu+nr resurse."""
    ckan = ckan or CkanClient()
    return [
        {"id": p.get("name"), "title": p.get("title"), "resources": len(p.get("resources", []))}
        for p in ckan.package_search(query, rows)
    ]
