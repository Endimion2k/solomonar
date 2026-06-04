"""Teste solver Turnstile (părțile construibile fără cheie/rețea)."""

from __future__ import annotations

import pytest

from connectors.ani.solver import ANI_SITEKEY, build_turnstile_task, solve_turnstile


def test_build_turnstile_task():
    t = build_turnstile_task("https://declaratii.integritate.eu", "0xABC")
    assert t == {
        "type": "AntiTurnstileTaskProxyLess",
        "websiteURL": "https://declaratii.integritate.eu",
        "websiteKey": "0xABC",
    }


def test_sitekey_present():
    assert ANI_SITEKEY.startswith("0x")


def test_solve_requires_key(monkeypatch):
    monkeypatch.delenv("CAPSOLVER_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="CAPSOLVER_API_KEY"):
        solve_turnstile(api_key=None)
