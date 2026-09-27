"""Test orchestrator build (gold → data/v1 JSON). Non-live (enrich_live=False)."""

from __future__ import annotations

import json

from connectors.companii.soe_seed import SOE_SEED
from connectors.institutie.generic import org_id
from pipeline.build import build_all
from solomonar_core.models import Company


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


def test_build_refuses_to_overwrite_enriched_outputs(tmp_path):
    """build_all e bootstrap: pe un data/v1 existent ar rescrie companiile îmbogățite cu seed-ul."""
    import pytest

    comp = tmp_path / "companii" / "_index.json"
    comp.parent.mkdir(parents=True)
    comp.write_text('{"data": ["1256 companii imbogatite"]}', encoding="utf-8")
    with pytest.raises(FileExistsError):
        build_all(tmp_path)
    assert "1256" in comp.read_text(encoding="utf-8")      # neatins
    assert not (tmp_path / "status.json").exists()        # nimic scris parțial

    build_all(tmp_path, force=True)                         # suprascriere explicită
    assert "1256" not in comp.read_text(encoding="utf-8")


def test_run_build_cli_exits_2_on_existing_output(tmp_path, capsys):
    from pipeline.run import main

    (tmp_path / "status.json").write_text("{}", encoding="utf-8")
    assert main(["--build", "--out", str(tmp_path)]) == 2
    assert "OPRIT" in capsys.readouterr().err


def test_build_control_edges_resolve_to_org_node(tmp_path):
    build_all(tmp_path)
    edges = json.loads((tmp_path / "graph_edges.json").read_text(encoding="utf-8"))
    romgaz = Company.id_for_cui(14056826)
    ctrl = next(e for e in edges if e["type"] == "CONTROLS" and e["dst"] == romgaz)
    # Romgaz e controlat de Ministerul Energiei → nodul-Organization REAL (org_id 'energie')
    assert ctrl["src"] == org_id("energie")


def test_control_chain_on_published_graph(tmp_path):
    """End-to-end: din graful PUBLICAT, 'ce controlează Ministerul Energiei?' → SOE-urile."""
    from pipeline.gold.graph import load_published_graph

    build_all(tmp_path)
    g = load_published_graph(tmp_path)
    controlled = {row[0] for row in g.control_chain(org_id("energie"))}
    assert Company.id_for_cui(14056826) in controlled  # Romgaz
    assert Company.id_for_cui(10874881) in controlled  # Nuclearelectrica
    g.close()
