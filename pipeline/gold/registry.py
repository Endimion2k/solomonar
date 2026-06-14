"""SqlitePersonRegistry — entity resolution persistent.

Înfășoară solomonar_core.resolve.PersonRegistry și persistă starea în SQLite, astfel încât
`romega_id`-urile rămân STABILE între rulări (un URL public de persoană nu se schimbă).
Fișierul SQLite se comite în repo (vezi .gitignore — excepție registry.sqlite).
"""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from solomonar_core.resolve import MatchResult, PersonRegistry

_SCHEMA = """
CREATE TABLE IF NOT EXISTS person (
    romega_id TEXT PRIMARY KEY, name_key TEXT, canonical TEXT, birth_date TEXT
);
CREATE TABLE IF NOT EXISTS alias (romega_id TEXT, alias TEXT);
CREATE TABLE IF NOT EXISTS xwalk (
    system TEXT, ext_id TEXT, romega_id TEXT, PRIMARY KEY (system, ext_id)
);
"""


class SqlitePersonRegistry:
    def __init__(self, db_path: str | Path, high: float = 0.85, low: float = 0.62) -> None:
        self.path = str(db_path)
        self.con = sqlite3.connect(self.path)
        self.con.executescript(_SCHEMA)
        self.mem = PersonRegistry(high=high, low=low)
        self._load()

    def resolve(self, *args, **kwargs) -> MatchResult:
        return self.mem.resolve(*args, **kwargs)

    def __len__(self) -> int:
        return len(self.mem)

    def _load(self) -> None:
        aliases: dict[str, list[str]] = {}
        for rid, al in self.con.execute("SELECT romega_id, alias FROM alias"):
            aliases.setdefault(rid, []).append(al)
        xwalk: dict[str, list[tuple[str, str]]] = {}
        for system, ext, rid in self.con.execute("SELECT system, ext_id, romega_id FROM xwalk"):
            xwalk.setdefault(rid, []).append((system, ext))
        for rid, key, canon, bd in self.con.execute(
            "SELECT romega_id, name_key, canonical, birth_date FROM person"
        ):
            self.mem.seed(
                rid,
                key,
                canon,
                date.fromisoformat(bd) if bd else None,
                aliases.get(rid, []),
                xwalk.get(rid, []),
            )

    def flush(self) -> None:
        c = self.con
        c.execute("DELETE FROM person")
        c.execute("DELETE FROM alias")
        c.execute("DELETE FROM xwalk")
        for rec in self.mem.records():
            c.execute(
                "INSERT INTO person VALUES (?, ?, ?, ?)",
                [
                    rec.romega_id,
                    rec.key,
                    rec.canonical_name,
                    rec.birth_date.isoformat() if rec.birth_date else None,
                ],
            )
            for al in rec.aliases:
                c.execute("INSERT INTO alias VALUES (?, ?)", [rec.romega_id, al])
        for system, ext, rid in self.mem.crosswalk_items():
            c.execute("INSERT INTO xwalk VALUES (?, ?, ?)", [system, ext, rid])
        c.commit()

    def close(self) -> None:
        self.flush()
        self.con.close()
