"""Connector opendata/bnr — curs valutar BNR (enrichment).

Arhetip `api` / XML. Cea mai curată sursă: fișiere XML statice, fără auth.
`https://curs.bnr.ro/nbrfxrates.xml` (azi), arhivă din 2005. Vezi docs/03-SOURCES.md §K.
Vechea adresă de pe www.bnr.ro întoarce acum pagina de start a site-ului (HTML, cod 200).

Folosit pentru normalizarea sumelor în valută (ex. depozite EUR în declarații → RON).
"""

from __future__ import annotations

import re

from solomonar_core.http import Client

URL = "https://curs.bnr.ro/nbrfxrates.xml"

_RE_RATE = re.compile(
    r'<Rate\s+currency="([A-Z]{3})"(?:\s+multiplier="(\d+)")?\s*>([\d.]+)</Rate>'
)
_RE_DATE = re.compile(r'<Cube\s+date="(\d{4}-\d{2}-\d{2})"')


def parse_bnr_rates(xml: bytes | str) -> dict:
    """Parsează XML-ul BNR → {'date': 'YYYY-MM-DD', 'rates': {CUR: rata_per_1_unitate}}."""
    text = xml.decode("utf-8", "replace") if isinstance(xml, (bytes, bytearray)) else xml
    rates: dict[str, float] = {}
    for currency, multiplier, value in _RE_RATE.findall(text):
        rate = float(value)
        if multiplier:  # ex. HUF multiplier=100 → rata per 1 unitate
            rate /= int(multiplier)
        rates[currency] = rate
    m = _RE_DATE.search(text)
    return {"date": m.group(1) if m else None, "rates": rates}


def cere_curs(d: dict) -> dict:
    """Refuză un răspuns fără dată sau fără cursuri (ex. o pagină HTML servită cu cod 200)."""
    if not d.get("date") or not d.get("rates"):
        raise ValueError(f"Răspunsul BNR de la {URL} nu conține cursul valutar (nu e XML-ul așteptat).")
    return d


class BnrConnector:
    source_id = "bnr"

    def __init__(self, client: Client | None = None) -> None:
        self.client = client or Client()

    def fetch_rates(self) -> dict:
        content, _ = self.client.fetch(URL, self.source_id, ext=".xml")
        return cere_curs(parse_bnr_rates(content))
