"""Gardă PII pe output-ul publicat: scrub_pii maschează corect și data/v1 e curat."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from connectors.ani.redaction import CNP_MASK, PHONE_MASK
from connectors.ani.tests.test_redaction import synthetic_cnp
from pipeline import scrub_pii

V1 = Path(scrub_pii.V1)


def _write(p: Path, obj, **kw) -> str:
    raw = json.dumps(obj, ensure_ascii=False, **kw)
    p.write_text(raw, encoding="utf-8", newline="")
    return raw


def test_scrub_masks_and_preserves_format(tmp_path):
    cnp = synthetic_cnp()
    obj = {
        "furnizori": {cnp: {"nume": "POPESCU ION"}, "14056826": {"nume": "ROMGAZ SA"}},
        "firme": [
            {"cui": int(cnp), "web": "0722123456", "reg_com": "J40/1/2020"},
            {"cui": 14056826, "web": "www.romgaz.ro"},
        ],
        "cv": [{"studii": f"{cnp} Educatie | Politehnica", "experienta": "referinta tel: 0744 111 222",
                "romega_id": "g:1900101400001"}],
        "pdf_url": "https://exemplu.ro/uploads/cv-0722123456.pdf",
    }
    fp = tmp_path / "x.json"
    _write(fp, obj, indent=2)

    rep = scrub_pii.process_file(str(fp), write=True)
    assert rep.changed and not rep.note          # formatarea (indent=2) s-a reprodus exact
    new = json.loads(fp.read_text(encoding="utf-8"))

    assert cnp not in new["furnizori"] and "pf:POPESCU ION" in new["furnizori"]   # cheie ca la harvestere
    assert new["furnizori"]["14056826"] == {"nume": "ROMGAZ SA"}
    assert new["firme"][0]["cui"] is None and new["firme"][0]["pf"] is True and new["firme"][0]["web"] == ""
    assert new["firme"][1] == {"cui": 14056826, "web": "www.romgaz.ro"}
    assert new["cv"][0]["studii"].startswith(CNP_MASK)
    assert PHONE_MASK in new["cv"][0]["experienta"]
    assert new["cv"][0]["romega_id"] == "g:1900101400001"          # câmp-ID: nu se atinge
    assert new["pdf_url"] == obj["pdf_url"]                          # URL: doar raportat
    assert any(h.action.startswith("URL") for h in rep.hits)
    # rezultatul trece garda, iar diff-ul e minim (+1 linie: flagul "pf" lângă cui-ul nulificat)
    assert not scrub_pii.blocking_hits([scrub_pii.process_file(str(fp), write=False)])
    assert len(fp.read_text(encoding="utf-8").splitlines()) == len(json.dumps(obj, indent=2).splitlines()) + 1


def test_scrub_edge_cases(tmp_path):
    cnp, cnp2 = synthetic_cnp(), synthetic_cnp("290010140000")
    obj = {
        "furnizori": {"pf-redactat-1": {"x": 1}, cnp: {"total": 5}},       # fără nume → pf-redactat-N
        "valori": [int(cnp), 1234567890123, 12.5],                          # CNP ca număr JSON
        "muchii": [{"src": "g:69b8c30722123456", "dst": "g:1234567890123abc"}],
        "text": "donator CI RD\n123456",                                     # \n escapat în JSON brut
        "web": ["office@firma-mica.ro", "PRIMARIA X", "https://www.ok.ro"],
        "cui": float(cnp2),
    }
    fp = tmp_path / "e.json"
    _write(fp, obj, indent=1)
    rep = scrub_pii.process_file(str(fp), write=True)
    new = json.loads(fp.read_text(encoding="utf-8"))
    assert new["furnizori"]["pf-redactat-1"] == {"x": 1}                    # neatins, fără coliziune
    assert new["furnizori"]["pf-redactat-2"] == {"total": 5}
    assert new["valori"] == [None, 1234567890123, 12.5]
    assert new["muchii"] == obj["muchii"]                                   # ID-uri hash intacte
    assert "123456" not in new["text"]
    assert new["web"] == ["", "", "https://www.ok.ro"]
    assert new["cui"] is None and new["pf"] is True
    kinds = {h.action for h in rep.hits}
    assert any(a.startswith("web →") for a in kinds) and any(a.startswith("web nevalid") for a in kinds)


def test_invalid_json_blocks_check(tmp_path):
    fp = tmp_path / "bad.json"
    fp.write_text('{"note": "tel: 0722 123 456", ', encoding="utf-8")
    reps = scrub_pii.scan(str(tmp_path), write=False)
    assert scrub_pii.blocking_hits(reps)


def test_check_mode_does_not_write(tmp_path):
    fp = tmp_path / "y.json"
    raw = _write(fp, {"note": "tel: 0722 123 456"})
    rep = scrub_pii.process_file(str(fp), write=False)
    assert rep.hits and not rep.changed and fp.read_text(encoding="utf-8") == raw


def test_clean_file_is_skipped_fast(tmp_path):
    fp = tmp_path / "z.json"
    _write(fp, {"cui": 14056826, "suma": 1234567890123, "sediu": "0213124567"})
    assert scrub_pii.process_file(str(fp), write=True).hits == []


@pytest.mark.skipif(not V1.is_dir(), reason="data/v1 lipsește")
def test_published_data_has_no_pii():
    """GARDĂ LEGALĂ: niciun CNP valid / telefon / serie CI în datele publicate (data/v1).

    Dacă pică: `python -m pipeline.scrub_pii` maschează, apoi `--check` trebuie să iasă 0.
    """
    blocking = scrub_pii.blocking_hits(scrub_pii.scan(str(V1), write=False))
    assert not blocking, "PII în data/v1: " + "; ".join(f"{f} {h.path} ({h.kind})" for f, h in blocking[:10])
