"""Contractul comun de connector.

Fiecare connector: fetch (→ bronze) și parse (bronze/HTML → modele canonice). Configurat
din config/sources.yaml. Trei arhetipuri (api/bulk/scrape/headless) implementează același
protocol — vezi docs/01-ARCHITECTURE.md §3.2.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from solomonar_core.bronze import BronzeArtifact


@runtime_checkable
class Connector(Protocol):
    source_id: str

    def fetch(self) -> list[BronzeArtifact]:
        """Descarcă din sursă → artefacte bronze (cache content-addressed)."""
        ...

    def parse(self, artifacts: list[BronzeArtifact]) -> list[BaseModel]:
        """Transformă artefactele brute → modele tipizate (silver)."""
        ...
