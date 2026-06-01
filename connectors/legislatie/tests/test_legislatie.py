"""Teste legislatie — parsare referințe de acte + link + parse token SOAP."""

from __future__ import annotations

from connectors.legislatie.legislatie import (
    link_laws_to_bills,
    parse_law_references,
    parse_token,
)


def test_parse_law_references():
    text = "Conform Legea nr. 176/2010 și OUG 109/2011, precum și HG 617/2023 și Legea 187/2023."
    keys = {(r["tip"], r["numar"], r["an"]) for r in parse_law_references(text)}
    assert ("lege", 176, 2010) in keys
    assert ("oug", 109, 2011) in keys
    assert ("hg", 617, 2023) in keys
    assert ("lege", 187, 2023) in keys


def test_parse_law_references_dedup():
    refs = parse_law_references("Legea 176/2010 ... iar Legea nr.176/2010 din nou")
    assert len(refs) == 1


def test_link_laws_to_bills():
    laws = [{"tip": "lege", "numar": 176, "an": 2010}]
    bills = [
        {"numar": 176, "an": 2010, "titlu": "Lege integritate"},
        {"numar": 99, "an": 2020, "titlu": "Altă lege"},
    ]
    links = link_laws_to_bills(laws, bills)
    assert len(links) == 1
    assert links[0]["bill"]["titlu"] == "Lege integritate"


def test_parse_token():
    assert parse_token("<resp><TokenKey>ABC-123</TokenKey></resp>") == "ABC-123"
    assert parse_token("<resp></resp>") is None
