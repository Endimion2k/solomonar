"""Ținte și format pentru onrc/firme_relevante.json (fără rețea)."""

from pipeline import harvest_firme_relevante as h


def test_targets_union_and_keep_published():
    idx = {"data": [{"cui": 14056826}, {"cui": None}]}
    cf = {"firme": [{"cui": "999"}, {"cui": "abc"}]}
    pub = {"firme": [{"cui": 361757}]}
    assert h.tinte(idx, cf, pub) == {14056826, 999, 361757}
    assert h.tinte(None, None, None) == set()


def test_row_to_record():
    header = "DENUMIRE^CUI^COD_INMATRICULARE^DATA_INMATRICULARE^FORMA_JURIDICA^ADR_JUDET^ADR_LOCALITATE"
    idx = {c: i for i, c in enumerate(header.split("^"))}
    rand = "ROMGAZ SA^14056826^J32/1/2001^2001-01-01^SA^Sibiu^Mediaș".split("^")
    assert h.firma(rand, idx) == {"cui": 14056826, "denumire": "ROMGAZ SA", "reg_com": "J32/1/2001",
                                  "localitate": "Mediaș", "judet": "Sibiu", "forma_juridica": "SA"}
    assert h.firma(["X SRL", "5"], idx)["judet"] == ""   # rând scurt: coloanele lipsă rămân goale
