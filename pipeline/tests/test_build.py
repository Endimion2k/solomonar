"""Test orchestrator build (gold → data/v1 JSON)."""

from __future__ import annotations

import json

from pipeline.build import build_all


def test_build_all(tmp_path):
    status = build_all(tmp_path)
    assert (tmp_path / "organizatii" / "_index.json").exists()
    assert (tmp_path / "status.json").exists()
    assert (tmp_path / "graph_edges.json").exists()

    assert status["collections"]["organizatii"] >= 1000
    assert status["collections"]["graph_edges"] == 16  # 16 ministere → guvern

    doc = json.loads((tmp_path / "organizatii" / "_index.json").read_text(encoding="utf-8"))
    assert doc["meta"]["count"] == status["collections"]["organizatii"]
    assert doc["data"][0]["romega_id"].startswith("o:")
