"""Test DNA — extragere comunicate din URL-uri REALE (dna.ro, capturate live prin firecrawl)."""

from __future__ import annotations

from connectors.audit.dna import extract_comunicate

# Linkuri REALE de pe dna.ro/comunicate.xhtml (firecrawl, iunie 2026).
REAL_HREFS = [
    "https://www.dna.ro/index.xhtml",
    "https://www.dna.ro/comunicat.xhtml?id=13765",
    "https://www.dna.ro/comunicat.xhtml?id=13764",
    "https://www.dna.ro/comunicat.xhtml?id=13760",
    "https://www.dna.ro/comunicat.xhtml?id=13743",
    "https://www.dna.ro/comunicat.xhtml?id=13738",
    "https://www.dna.ro/contacts.xhtml",
    "https://www.dna.ro/comunicat.xhtml?id=13765",  # duplicat — deduplicat
]


def test_extract_comunicate():
    coms = extract_comunicate(REAL_HREFS)
    ids = {c["id"] for c in coms}
    assert ids == {13765, 13764, 13760, 13743, 13738}  # 5 unice, fără nav, dedup
    assert all(c["url"].startswith("https://www.dna.ro/comunicat.xhtml?id=") for c in coms)
