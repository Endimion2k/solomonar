"""Teste pentru GraphStore (DuckDB): lanț de control recursiv + semnal de conflict."""

from __future__ import annotations

from pipeline.gold.graph import GraphStore


def test_control_chain_recursive():
    g = GraphStore()
    g.add_node("o:stat", "Organization")
    g.add_node("c:romgaz", "Company")
    g.add_node("c:filiala", "Company")
    g.add_edge("o:stat", "c:romgaz", "CONTROLS")
    g.add_edge("c:romgaz", "c:filiala", "OWNS_SHARE", {"percent": 60})

    chain = g.control_chain("o:stat")
    assert chain == [("c:romgaz", 1), ("c:filiala", 2)]
    g.close()


def test_boards_with_public_office_signal():
    g = GraphStore()
    # p:x — și demnitar (HOLDS_POSITION) și membru CA (MEMBER_OF_BOARD) -> semnal de conflict
    g.add_edge("p:x", "o:minister", "HOLDS_POSITION")
    g.add_edge("p:x", "c:firma", "MEMBER_OF_BOARD")
    # p:y — doar membru CA, fără funcție publică -> NU e semnalat
    g.add_edge("p:y", "c:firma2", "MEMBER_OF_BOARD")

    signals = g.boards_with_public_office()
    assert signals == [("p:x", "c:firma")]
    g.close()
