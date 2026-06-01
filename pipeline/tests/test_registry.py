"""Teste pentru SqlitePersonRegistry (persistență + stabilitate romega_id între rulări)."""

from __future__ import annotations

from pipeline.gold.registry import SqlitePersonRegistry
from romega_core.resolve import MatchStatus


def test_registry_persists_and_matches_after_reopen(tmp_path):
    db = tmp_path / "registry.sqlite"

    r1 = SqlitePersonRegistry(db)
    a = r1.resolve("Ion Popescu")
    r1.resolve("Maria Ionescu")
    r1.close()  # flush pe disc

    # „Rulare nouă": reîncarcă din SQLite
    r2 = SqlitePersonRegistry(db)
    assert len(r2) == 2  # starea s-a reîncărcat
    b = r2.resolve("POPESCU Ion")  # variantă -> trebuie să se lege la persoana persistată
    assert b.status == MatchStatus.MATCHED
    assert b.romega_id == a.romega_id


def test_registry_crosswalk_persists(tmp_path):
    db = tmp_path / "registry.sqlite"
    r1 = SqlitePersonRegistry(db)
    a = r1.resolve("Ion Popescu", external_ids={"cdep": "7"})
    r1.close()

    r2 = SqlitePersonRegistry(db)
    # nume complet diferit, dar același ID extern -> match prin crosswalk persistat
    b = r2.resolve("Cu Totul Alt Nume", external_ids={"cdep": "7"})
    assert b.status == MatchStatus.MATCHED
    assert b.romega_id == a.romega_id
