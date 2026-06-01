"""GraphStore — noduri + muchii în DuckDB, cu traversări recursive.

Activează exact interogările care diferențiază ROMEGA (vezi docs/02-DATA-MODEL.md §3):
- control_chain: lanțul de proprietate stat → SOE → subsidiare (recursiv);
- boards_with_public_office: persoane care sunt și membri CA și dețin funcție publică
  (semnal de potențial conflict de interese).
"""

from __future__ import annotations

import json

import duckdb

# Muchiile de proprietate, toate stocate owner → owned (src deține/controlează dst).
OWNERSHIP_EDGES = ("CONTROLS", "OWNS_SHARE", "SUBSIDIARY_OF")


class GraphStore:
    def __init__(self, database: str = ":memory:") -> None:
        self.con = duckdb.connect(database)
        self.con.execute(
            "CREATE TABLE IF NOT EXISTS node (id VARCHAR PRIMARY KEY, type VARCHAR, props VARCHAR)"
        )
        self.con.execute(
            "CREATE TABLE IF NOT EXISTS edge (src VARCHAR, dst VARCHAR, type VARCHAR, props VARCHAR)"
        )

    def add_node(self, node_id: str, node_type: str, props: dict | None = None) -> None:
        self.con.execute(
            "INSERT OR REPLACE INTO node VALUES (?, ?, ?)",
            [node_id, str(node_type), json.dumps(props or {}, ensure_ascii=False)],
        )

    def add_edge(self, src: str, dst: str, edge_type: str, props: dict | None = None) -> None:
        self.con.execute(
            "INSERT INTO edge VALUES (?, ?, ?, ?)",
            [src, dst, str(edge_type), json.dumps(props or {}, ensure_ascii=False)],
        )

    def control_chain(self, root_id: str, max_depth: int = 6) -> list[tuple[str, int]]:
        """Toate entitățile controlate (direct sau prin lanț) de `root_id`, cu adâncimea."""
        query = """
            WITH RECURSIVE chain AS (
                SELECT src, dst, 1 AS depth
                FROM edge
                WHERE type IN ('CONTROLS','OWNS_SHARE','SUBSIDIARY_OF') AND src = ?
                UNION ALL
                SELECT e.src, e.dst, c.depth + 1
                FROM edge e JOIN chain c ON e.src = c.dst
                WHERE e.type IN ('CONTROLS','OWNS_SHARE','SUBSIDIARY_OF') AND c.depth < ?
            )
            SELECT dst, min(depth) AS depth FROM chain GROUP BY dst ORDER BY depth, dst
        """
        return self.con.execute(query, [root_id, max_depth]).fetchall()

    def boards_with_public_office(self) -> list[tuple[str, str]]:
        """Persoane care sunt membri CA ȘI dețin funcție publică (semnal de conflict)."""
        query = """
            SELECT DISTINCT b.src AS person, b.dst AS company
            FROM edge b
            JOIN edge p ON p.src = b.src AND p.type = 'HOLDS_POSITION'
            WHERE b.type = 'MEMBER_OF_BOARD'
            ORDER BY person, company
        """
        return self.con.execute(query).fetchall()

    def close(self) -> None:
        self.con.close()
