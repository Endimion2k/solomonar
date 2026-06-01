"""Teste pentru loader-ul de config + CLI runner (offline)."""

from __future__ import annotations

from pipeline.config import find_source, iter_sources, load_sources
from pipeline.run import main


def test_load_real_sources():
    doc = load_sources()
    assert "sources" in doc
    assert find_source(doc, "cdep") is not None
    assert find_source(doc, "ani")["access"] == "headless"


def test_flatten_includes_items():
    doc = load_sources()
    ids = {s["id"] for s in iter_sources(doc)}
    # ministerele și agențiile sunt în `items` -> trebuie să apară individual
    assert {"mae", "energie", "ms"} <= ids
    assert "asf" in ids
    # iar sursa-părinte rămâne și ea
    assert "ministere" in ids


def test_item_inherits_and_overrides():
    doc = load_sources()
    mae = find_source(doc, "mae")
    assert mae["domain"] == "mae.ro"
    assert mae["parent_group"] == "ministere"
    assert mae["access"] == "scrape"  # moștenit de la părinte


def test_cli_list(capsys):
    assert main(["--list"]) == 0
    out = capsys.readouterr().out
    assert "cdep" in out and "ani" in out


def test_cli_unknown_source():
    assert main(["--source", "nu_exista_asa_ceva"]) == 2


def test_cli_known_source_cdep(capsys):
    assert main(["--source", "cdep"]) == 0
    assert "cdep" in capsys.readouterr().out
