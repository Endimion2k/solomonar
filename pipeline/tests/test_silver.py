"""Test pentru staging-ul silver (DuckDB)."""

from __future__ import annotations

import duckdb

from pipeline.silver import stage
from solomonar_core.models import Person


def test_stage_inserts_models():
    con = duckdb.connect()
    n = stage(con, "person", [Person(romega_id="p:1", full_name="Ion"), Person(romega_id="p:2", full_name="Maria")])
    assert n == 2
    rid = con.execute("SELECT romega_id FROM person ORDER BY romega_id").fetchall()
    assert rid == [("p:1",), ("p:2",)]
