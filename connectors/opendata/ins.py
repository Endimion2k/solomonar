"""Connector opendata/ins — INS Tempo (statistici.insse.ro:8077, JSON). Enrichment statistic.

API public, HTTP (port 8077, fără TLS). Domenii → matrici → date. Vezi docs/03-SOURCES.md §K.
Notă: endpoint-ul poate fi restricționat din unele rețele; se validează pe runner.
"""

from __future__ import annotations

from romega_core.http import Client

BASE = "http://statistici.insse.ro:8077/tempo-ins"


class InsTempoClient:
    def __init__(self, client: Client | None = None) -> None:
        self.client = client or Client()

    def matrices(self, lang: str = "ro") -> object:
        r = self.client.get(f"{BASE}/matrix/matrices?lang={lang}")
        r.raise_for_status()
        return r.json()

    def matrix(self, code: str) -> object:
        r = self.client.get(f"{BASE}/matrix/{code}")
        r.raise_for_status()
        return r.json()


def matrix_count(matrices_json: object) -> int:
    """Numără matricile dintr-un răspuns INS (structură variabilă — tolerant)."""
    if isinstance(matrices_json, list):
        return len(matrices_json)
    if isinstance(matrices_json, dict):
        for key in ("matrices", "context", "children"):
            value = matrices_json.get(key)
            if isinstance(value, list):
                return len(value)
    return 0


class InsConnector:
    source_id = "ins_tempo"

    def __init__(self, client: Client | None = None) -> None:
        self.tempo = InsTempoClient(client)

    def list_matrices(self) -> object:
        return self.tempo.matrices()
