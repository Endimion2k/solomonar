"""Teste offline pentru HTTP (doar throttle-ul per-host; fără rețea)."""

from __future__ import annotations

import time

from romega_core.http import HostThrottle


def test_throttle_same_host_waits():
    t = HostThrottle(seconds=0.15)
    start = time.monotonic()
    t.wait("cdep.ro")
    t.wait("cdep.ro")  # al doilea trebuie să aștepte ~0.15s
    elapsed = time.monotonic() - start
    assert elapsed >= 0.14


def test_throttle_different_hosts_independent():
    t = HostThrottle(seconds=0.30)
    start = time.monotonic()
    t.wait("cdep.ro")
    t.wait("senat.ro")  # host diferit -> nu așteaptă
    elapsed = time.monotonic() - start
    assert elapsed < 0.20
