"""Provenance: fiecare fapt publicat își cunoaște sursa.

- SourceRef  — atașat fiecărei entități (source_id + url + când + hash bronze).
- Meta       — metadata per fișier JSON (compatibil cu cdep-api-poc schemas/common.Meta).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SourceRef(BaseModel):
    """Referință de proveniență pentru un fapt sau o entitate."""

    model_config = ConfigDict(str_strip_whitespace=True)

    source_id: str = Field(..., description="ID-ul sursei din config/sources.yaml (ex. 'cdep', 'ani')")
    source_url: str = Field(..., description="URL-ul exact de unde provine faptul")
    fetched_at: datetime = Field(..., description="UTC la momentul fetch-ului")
    bronze_sha256: str | None = Field(
        default=None, description="Hash-ul artefactului bronze (data/raw/) pentru trasabilitate"
    )


class Meta(BaseModel):
    """Metadata atașată fiecărui fișier JSON generat (compat cdep-api-poc).

    Permite consumatorilor să știe când au fost colectate datele și din ce sursă.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    generated_at: datetime = Field(..., description="UTC timestamp la momentul build-ului")
    source_url: str = Field(..., description="URL-ul/sursa principală")
    scraper_version: str = Field(..., description="Versiunea connector-ului (semver)")
    count: int = Field(..., ge=0, description="Numărul de înregistrări din fișier")
