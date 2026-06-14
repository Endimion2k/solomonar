"""Test pentru export-ul JSON (plic meta + data)."""

from __future__ import annotations

import json

from solomonar_core.io import export_collection
from solomonar_core.models import Person


def test_export_collection(tmp_path):
    people = [
        Person(romega_id="p:1", full_name="Ion Popescu"),
        Person(romega_id="p:2", full_name="Maria Ionescu"),
    ]
    out = tmp_path / "persoane.json"
    meta = export_collection(out, people, source_url="cdep.ro", version="0.1.0")

    assert meta.count == 2
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["meta"]["count"] == 2
    assert doc["meta"]["scraper_version"] == "0.1.0"
    assert len(doc["data"]) == 2
    assert doc["data"][0]["full_name"] == "Ion Popescu"
