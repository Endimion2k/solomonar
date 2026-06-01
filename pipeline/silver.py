"""Silver — încarcă modele Pydantic în tabele staging DuckDB (schema-on-read v0).

v0 stochează fiecare entitate ca JSON + romega_id, pentru flexibilitate cât timp modelul
încă evoluează. Gold (graph/registry) extrage din aceste tabele.
"""

from __future__ import annotations

from typing import Iterable

import duckdb
from pydantic import BaseModel


def stage(con: duckdb.DuckDBPyConnection, table: str, models: Iterable[BaseModel]) -> int:
    """Inserează modele într-o tabelă staging. Întoarce numărul total de rânduri."""
    rows = [(getattr(m, "romega_id", None), m.model_dump_json()) for m in models]
    con.execute(f'CREATE TABLE IF NOT EXISTS "{table}" (romega_id VARCHAR, data VARCHAR)')
    if rows:
        con.executemany(f'INSERT INTO "{table}" VALUES (?, ?)', rows)
    return con.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
