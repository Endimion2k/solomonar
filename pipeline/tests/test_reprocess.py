"""Reprocesarea declarațiilor: PII mascat (nu blocat), plasa de siguranță, retry, acoperire care nu scade."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from connectors.ani.redaction import CNP_MASK
from connectors.ani.tests.test_redaction import synthetic_cnp
from pipeline import harvest_reprocess as hr

TEXT = "Declaratie de interese. " * 10


@pytest.fixture
def pdf(tmp_path):
    p = tmp_path / "d.pdf"
    p.write_bytes(b"%PDF-1.4")
    return str(p)


def _interese(entitati):
    return SimpleNamespace(text_extracted=True, has_any=True, actionariat_count=1, conducere_firme_count=0,
                           prof_sindicat_count=0, partid_count=0, contracte_count=0, valoare_actiuni_ron=0.0,
                           valoare_contracte_ron=0.0, entitati=entitati)


def _patch(monkeypatch, text, seen, entitati=("ROMGAZ SA",)):
    monkeypatch.setattr(hr, "extract_pdf_text", lambda data: text)
    monkeypatch.setattr(hr, "classify_declaration", lambda t: {"interese"})

    def parse(t):
        seen.append(t)
        return _interese(list(entitati))
    monkeypatch.setattr(hr, "parse_interese_text", parse)


def test_pii_is_masked_before_parsing_not_blocked(monkeypatch, pdf):
    cnp, seen = synthetic_cnp(), []
    _patch(monkeypatch, f"{TEXT} CNP {cnp} actionar la ROMGAZ SA", seen)
    rec = hr._process(("u1", pdf, "Inst", "auto"))
    assert rec["status"] == "ok" and rec["mascat"] is True
    assert cnp not in seen[0] and CNP_MASK in seen[0]          # parserul vede doar textul mascat
    assert cnp not in json.dumps(rec)


def test_clean_text_is_not_flagged(monkeypatch, pdf):
    seen = []
    _patch(monkeypatch, TEXT + " actionar la ROMGAZ SA", seen)
    rec = hr._process(("u1", pdf, "Inst", "auto"))
    assert rec["status"] == "ok" and "mascat" not in rec


def test_safety_net_blocks_pii_in_published_fields(monkeypatch, pdf):
    cnp = synthetic_cnp()
    _patch(monkeypatch, TEXT, [], entitati=(f"SC X SRL {cnp}",))   # ex. un parser care ar reintroduce PII
    rec = hr._process(("u1", pdf, "Inst", "auto"))
    assert rec == {"pdf_url": "u1", "status": "pii", "ocr": False}


def test_alias_host_is_fetched_via_alias_but_stored_under_original_url():
    orig = "https://www.rowater.ro/wp-content/uploads/avere_interese/x.pdf"
    assert hr._alias(orig) == "https://rowater.ro/wp-content/uploads/avere_interese/x.pdf"
    assert hr._alias("https://www.onrc.ro/a.pdf") is None

    class Client:
        def __init__(self):
            self.many, self.got = [], []

        def fetch_many(self, items, workers=8):
            self.many += [i[0] for i in items]

        def get(self, url):
            self.got.append(url)
            return SimpleNamespace(content=b"%PDF-1.4", raise_for_status=lambda: None)

    class Bronze:
        def __init__(self):
            self.put_urls = []

        def put(self, source_id, url, content, ext):
            self.put_urls.append(url)

    c, b = Client(), Bronze()
    hr._download(c, b, [orig, "https://www.onrc.ro/a.pdf"])
    assert c.many == ["https://www.onrc.ro/a.pdf"]
    assert c.got == [hr._alias(orig)] and b.put_urls == [orig]


def _jsonl(tmp_path, monkeypatch, rows):
    p = tmp_path / "r.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    monkeypatch.setattr(hr, "JSONL", str(p))


def test_latest_record_wins_but_never_drops_ok(tmp_path, monkeypatch):
    _jsonl(tmp_path, monkeypatch, [
        {"pdf_url": "a", "status": "pii"}, {"pdf_url": "a", "status": "ok", "it": {"pdf_url": "a"}},
        {"pdf_url": "b", "status": "ok", "av": {"pdf_url": "b"}}, {"pdf_url": "b", "status": "timeout"},
        {"pdf_url": "c", "status": "fail"}])
    last = hr._latest()
    assert last["a"]["status"] == "ok" and last["b"]["status"] == "ok" and last["c"]["status"] == "fail"


def test_retry_statuses_are_not_done(tmp_path, monkeypatch):
    _jsonl(tmp_path, monkeypatch, [{"pdf_url": "a", "status": "pii"}, {"pdf_url": "b", "status": "ok"},
                                   {"pdf_url": "c", "status": "timeout"}])
    assert hr._load_done() == {"a", "b", "c"}
    assert hr._load_done({"pii", "timeout"}) == {"b"}


def test_finalize_counts_each_pdf_once(tmp_path, monkeypatch):
    _jsonl(tmp_path, monkeypatch, [
        {"pdf_url": "a", "status": "pii"},
        {"pdf_url": "a", "status": "ok", "mascat": True, "av": {"pdf_url": "a"}, "it": {"pdf_url": "a"}},
        {"pdf_url": "b", "status": "empty"}])
    monkeypatch.setattr(hr, "OUT_AV", str(tmp_path / "av.json"))
    monkeypatch.setattr(hr, "OUT_IT", str(tmp_path / "it.json"))
    hr._finalize()
    av = json.loads((tmp_path / "av.json").read_text(encoding="utf-8"))
    it = json.loads((tmp_path / "it.json").read_text(encoding="utf-8"))
    assert av["total"] == 1 and av["pii_blocate"] == 0 and av["pii_mascate"] == 1 and it["total"] == 1


def test_finalize_adds_declarant_name_used_by_gold(tmp_path, monkeypatch):
    url = "https://x.ro/declaratii/POPESCU-I.-ION-DA-2025.pdf"
    _jsonl(tmp_path, monkeypatch, [{"pdf_url": url, "status": "ok", "av": {"pdf_url": url, "institutie": "X"},
                                    "it": {"pdf_url": "https://x.ro/da_ba.pdf", "institutie": "X"}}])
    monkeypatch.setattr(hr, "OUT_AV", str(tmp_path / "av.json"))
    monkeypatch.setattr(hr, "OUT_IT", str(tmp_path / "it.json"))
    hr._finalize()
    rec = json.loads((tmp_path / "av.json").read_text(encoding="utf-8"))["declaratii"][0]
    assert rec["nume"] == "POPESCU ION" and rec["nume_norm"] == "ION POPESCU"
    assert "nume" not in json.loads((tmp_path / "it.json").read_text(encoding="utf-8"))["declaratii"][0]
