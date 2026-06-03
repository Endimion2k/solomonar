"""Test Curtea de Conturi — parsare rapoarte de audit pe HTML REAL (fixture live)."""

from __future__ import annotations

from pathlib import Path

from connectors.audit.curteadeconturi import parse_audit_links

FIX = Path(__file__).parent / "fixtures"


def test_parse_audit_links_real_fixture():
    links = parse_audit_links((FIX / "ccr_home.html").read_bytes())
    assert len(links) >= 5
    titles = " ".join(link["title"] for link in links).lower()
    assert "audit" in titles
    assert any("/rapoarte-de-audit" in link["url"] for link in links)
    assert all(link["url"].startswith("https://www.curteadeconturi.ro") for link in links)
