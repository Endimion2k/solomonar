"""Orchestrator end-to-end: config + surse → gold → data/v1/*.json (API static publicat).

v0 publică stratul de organizații (din config: 1.429 instituții) + graful de subordonare +
status.json. Pe măsură ce connectoarele rulează live (pe runner), build_all se extinde cu
persoane/companii/declarații/contracte.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from connectors.institutie.generic import (
    build_deconcentrated_from_config,
    build_local_from_config,
    build_organizations,
    subordinate_edges,
)
from pipeline.config import iter_sources, load_sources
from romega_core.io import export_collection

DEFAULT_OUT = Path(__file__).resolve().parents[1] / "data" / "v1"


def build_all(output_dir: str | Path = DEFAULT_OUT, version: str = "0.1.0") -> dict:
    """Construiește și exportă stratul gold în `output_dir`. Întoarce status-ul."""
    out = Path(output_dir)
    (out / "organizatii").mkdir(parents=True, exist_ok=True)

    flat = iter_sources(load_sources())

    # --- Organizații (din config) ---
    centrale = build_organizations(flat)
    deconcentrate = build_deconcentrated_from_config(flat)
    locale = build_local_from_config(flat)
    all_orgs = centrale + deconcentrate + locale

    export_collection(
        out / "organizatii" / "_index.json",
        all_orgs,
        source_url="config/sources.yaml",
        version=version,
    )
    export_collection(
        out / "organizatii" / "centrale.json",
        centrale,
        source_url="config/sources.yaml",
        version=version,
    )

    # --- Graf (muchii) ---
    edges = subordinate_edges(flat)
    (out / "graph_edges.json").write_text(
        json.dumps([e.model_dump(mode="json") for e in edges], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # --- Status (machine-readable) ---
    status = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "version": version,
        "collections": {
            "organizatii": len(all_orgs),
            "organizatii_centrale": len(centrale),
            "organizatii_deconcentrate": len(deconcentrate),
            "organizatii_locale": len(locale),
            "graph_edges": len(edges),
        },
    }
    (out / "status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return status
