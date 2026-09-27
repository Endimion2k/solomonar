"""Orchestratorul de refresh: ordinea pașilor, selecția (--groups/--only/--from), gărzile."""

from __future__ import annotations

import argparse

import pytest

from pipeline import refresh


def _args(**kw):
    base = {"groups": refresh.GROUPS, "only": None, "from_step": None}
    return argparse.Namespace(**{**base, **kw})


def _ids(steps):
    return [s[0] for s in steps]


def test_order_respects_dependencies():
    ids = _ids(refresh.STEPS)
    before = [("comisii", "plx_initiatori"), ("plx_initiatori", "comisii_recent"),
              ("achizitii_directe", "reprezentanti"), ("reprezentanti", "gold"), ("bilanturi", "gold"),
              ("gold", "splink_apply"), ("splink_apply", "opensanctions"), ("gold", "guvernanta"),
              ("alerte", "feeds"), ("search", "stats"), ("stats", "pii_check"), ("pii_scrub", "pii_check")]
    for a, b in before:
        assert ids.index(a) < ids.index(b), f"{a} trebuie să ruleze înainte de {b}"
    assert ids[-1] == "pii_check"                     # garda PII e ultimul pas
    assert len(ids) == len(set(ids))


def test_select_groups_only_from():
    assert {s[1] for s in refresh.select(_args(groups=["surse"]))} == {"surse"}
    assert _ids(refresh.select(_args(only="dna,feeds"))) == ["dna", "feeds"]
    sel = _ids(refresh.select(_args(from_step="gold")))
    assert sel[0] == "gold" and "parlament" not in sel and sel[-1] == "pii_check"


def test_select_rejects_unknown_steps():
    with pytest.raises(SystemExit):
        refresh.select(_args(only="nu_exista"))
    with pytest.raises(SystemExit):
        refresh.select(_args(from_step="nu_exista"))


def test_gates_flag_big_and_invalid_files(tmp_path, monkeypatch):
    monkeypatch.setattr(refresh, "V", str(tmp_path))
    monkeypatch.setattr(refresh, "MAX_MIB", 0.001)
    (tmp_path / "ok.json").write_text('{"a": 1}', encoding="utf-8")
    (tmp_path / "nd.json").write_text('{"a": 1}\n{"b": 2}\n', encoding="utf-8")   # NDJSON acceptat
    (tmp_path / "bad.json").write_text('{"a": ', encoding="utf-8")
    (tmp_path / "big.json").write_text('{"x": "' + "a" * 5000 + '"}', encoding="utf-8")
    assert [b.split("bad.json")[-1] == "" for b in refresh._json_gate()] == [True]
    assert any("big.json" in b for b in refresh._size_gate())
