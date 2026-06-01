"""Orchestrator end-to-end: config + surse → gold → data/v1/*.json (API static publicat).

Publică: organizații (din config, 1.429), companii de stat (seed + ANAF live), graful
(SUBORDINATE_OF + CONTROLS coerent cu nodurile-Organization), status.json.
Pe runner, build_all se extinde cu persoane/declarații/contracte live.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from connectors.companii.registry import CompanyRegistry, control_edges
from connectors.companii.soe_seed import seed_companies
from connectors.institutie.generic import (
    build_deconcentrated_from_config,
    build_local_from_config,
    build_organizations,
    resolve_org_by_name,
    subordinate_edges,
)
from pipeline.config import iter_sources, load_sources
from romega_core.io import export_collection

DEFAULT_OUT = Path(__file__).resolve().parents[1] / "data" / "v1"


def build_all(
    output_dir: str | Path = DEFAULT_OUT, version: str = "0.1.0", enrich_live: bool = False
) -> dict:
    """Construiește și exportă stratul gold. enrich_live=True interoghează ANAF (necesită rețea)."""
    out = Path(output_dir)
    (out / "organizatii").mkdir(parents=True, exist_ok=True)
    (out / "companii").mkdir(parents=True, exist_ok=True)

    flat = iter_sources(load_sources())

    # --- Organizații (din config) ---
    centrale = build_organizations(flat)
    deconcentrate = build_deconcentrated_from_config(flat)
    locale = build_local_from_config(flat)
    all_orgs = centrale + deconcentrate + locale
    export_collection(out / "organizatii" / "_index.json", all_orgs, source_url="config/sources.yaml", version=version)
    export_collection(out / "organizatii" / "centrale.json", centrale, source_url="config/sources.yaml", version=version)

    # --- Companii de stat (seed + opțional ANAF live) ---
    creg = CompanyRegistry()
    for c in seed_companies():
        creg.upsert(c)
    if enrich_live:
        try:
            from connectors.fiscal.anaf import anaf_lookup, to_company

            cuis = [c.cui for c in creg.all()]
            for entry in anaf_lookup(cuis, "2024-07-02"):
                creg.upsert(to_company(entry))
        except Exception:  # pragma: no cover - rețea
            pass
    companies = creg.all()
    export_collection(out / "companii" / "_index.json", companies, source_url="AMEPIP seed + ANAF", version=version)

    # --- Graf: SUBORDINATE_OF + CONTROLS (coerent cu nodurile-Organization) ---
    sub_edges = subordinate_edges(flat)
    ctrl_edges = control_edges(companies, org_resolver=lambda n: resolve_org_by_name(n, centrale))
    all_edges = sub_edges + ctrl_edges
    (out / "graph_edges.json").write_text(
        json.dumps([e.model_dump(mode="json") for e in all_edges], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # --- Status ---
    status = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "version": version,
        "enriched_live": enrich_live,
        "collections": {
            "organizatii": len(all_orgs),
            "organizatii_centrale": len(centrale),
            "organizatii_deconcentrate": len(deconcentrate),
            "organizatii_locale": len(locale),
            "companii": len(companies),
            "graph_edges": len(all_edges),
        },
    }
    (out / "status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    return status
