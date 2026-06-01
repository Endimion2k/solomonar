"""Test orchestrator build (gold → data/v1 JSON). Non-live (enrich_live=False)."""

from __future__ import annotations

import json

from connectors.companii.soe_seed import SOE_SEED
from connectors.institutie.generic import org_id
from pipeline.build import build_all
from romega_core.models import Company


def test_build_all(tmp_path):
    status = build_all(tmp_path)  # enrich_live=False implicit
    assert (tmp_path / "organizatii" / "_index.json").exists()
    assert (tmp_path / "companii" / "_index.json").exists()
    assert (tmp_path / "status.json").exists()
    assert (tmp_path / "graph_edges.json").exists()

    assert status["collections"]["organizatii"] >= 1000
    assert status["collections"]["companii"] == len(SOE_SEED)
    # 16 SUBORDINATE_OF (minister→guvern) + len(seed) CONTROLS
    assert status["collections"]["graph_edges"] == 16 + len(SOE_SEED)


def test_build_control_edges_resolve_to_org_node(tmp_path):
    build_all(tmp_path)
    edges = json.loads((tmp_path / "graph_edges.json").read_text(encoding="utf-8"))
    romgaz = Company.id_for_cui(14056826)
    ctrl = next(e for e in edges if e["type"] == "CONTROLS" and e["dst"] == romgaz)
    # Romgaz e controlat de Ministerul Energiei → nodul-Organization REAL (org_id 'energie')
    assert ctrl["src"] == org_id("energie")
