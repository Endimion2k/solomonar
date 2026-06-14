"""Teste pentru BronzeStore (cache content-addressed)."""

from __future__ import annotations

from solomonar_core.bronze import BronzeStore


def test_put_and_get(tmp_path):
    store = BronzeStore(tmp_path)
    art = store.put("cdep", "https://cdep.ro/x", b"<html>salut</html>", ext=".html")
    assert art.source_id == "cdep"
    assert store.get("cdep", art.sha256, ".html") == b"<html>salut</html>"
    assert store.count() == 1


def test_dedup_same_content(tmp_path):
    store = BronzeStore(tmp_path)
    a = store.put("cdep", "https://cdep.ro/x", b"same", ext=".html")
    b = store.put("cdep", "https://cdep.ro/y", b"same", ext=".html")  # alt URL, același conținut
    assert a.sha256 == b.sha256          # un singur fișier fizic (dedup pe conținut)
    assert store.count() == 2            # dar 2 URL-uri cache-uite (index pe URL)


def test_url_cache_and_reload(tmp_path):
    store = BronzeStore(tmp_path)
    store.put("ani", "https://x/d.pdf", b"%PDF-1.4 data", ext=".pdf")
    assert store.get_by_url("https://x/d.pdf") == b"%PDF-1.4 data"
    assert store.has_url("https://x/d.pdf")
    assert store.get_by_url("https://x/lipsa.pdf") is None
    # altă instanță pe același root -> indexul pe URL se reconstruiește din manifest (cache persistent)
    store2 = BronzeStore(tmp_path)
    assert store2.get_by_url("https://x/d.pdf") == b"%PDF-1.4 data"
    assert store2.artifact_for_url("https://x/d.pdf").source_id == "ani"


def test_put_same_url_twice_one_entry(tmp_path):
    store = BronzeStore(tmp_path)
    store.put("cdep", "https://cdep.ro/x", b"v1", ext=".html")
    store.put("cdep", "https://cdep.ro/x", b"v1", ext=".html")
    assert store.count() == 1  # același URL -> o singură intrare


def test_distinct_content(tmp_path):
    store = BronzeStore(tmp_path)
    store.put("cdep", "u1", b"one", ext=".html")
    store.put("cdep", "u2", b"two", ext=".html")
    assert store.count() == 2


def test_source_ref_from_artifact(tmp_path):
    store = BronzeStore(tmp_path)
    art = store.put("ani", "https://integritate.eu/d.pdf", b"%PDF-1.4", ext=".pdf")
    ref = art.source_ref()
    assert ref.source_id == "ani"
    assert ref.bronze_sha256 == art.sha256
    assert ref.source_url.endswith("d.pdf")
