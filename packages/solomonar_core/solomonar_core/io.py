"""Export — gold → fișiere JSON statice (stratul public/API).

Format de fișier (compatibil cu filozofia cdep-api-poc): un plic cu `meta` (provenance per
fișier) + `data` (lista de entități). Servit prin GitHub Pages CDN.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from pydantic import BaseModel

from solomonar_core.provenance import Meta


def export_collection(
    path: str | Path,
    items: Iterable[BaseModel],
    *,
    source_url: str,
    version: str,
    generated_at: datetime | None = None,
) -> Meta:
    """Scrie o colecție de modele într-un fișier JSON cu plic `meta` + `data`."""
    items = list(items)
    meta = Meta(
        generated_at=generated_at or datetime.now(timezone.utc),
        source_url=source_url,
        scraper_version=version,
        count=len(items),
    )
    payload = {
        "meta": meta.model_dump(mode="json"),
        "data": [m.model_dump(mode="json") for m in items],
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta
