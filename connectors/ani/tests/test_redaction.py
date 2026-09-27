"""Teste pentru guard-ul de redactare (PII) — critic legal."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel

from connectors.ani.declaratii import parse_avere_text
from connectors.ani.redaction import assert_clean, find_pii

FIX = Path(__file__).parent / "fixtures"


def test_find_pii_detects_cnp():
    assert "CNP" in find_pii("declarantul cu CNP 1850101080012 a depus")


def test_find_pii_detects_phone():
    assert "telefon" in find_pii("contact 0721234567")


def test_clean_text_has_no_pii():
    assert find_pii("Popescu Ion, judet Cluj, 500 m², 150.000 RON") == []


def test_parsed_avere_passes_guard():
    text = (FIX / "declaratie_avere.txt").read_text(encoding="utf-8")
    assert_clean(parse_avere_text(text))  # output-ul publicat (agregate) e curat


def test_assert_clean_raises_on_leak():
    class Leaky(BaseModel):
        note: str

    with pytest.raises(ValueError):
        assert_clean(Leaky(note="ramas CNP 2920202125634 in text"))


# --- detecție precisă + mascare (output publicat) -------------------------------------------

from connectors.ani.redaction import (  # noqa: E402
    CI_MASK, CNP_MASK, IBAN_MASK, PHONE_MASK, clean_cui, cnp_valid, iban_valid, is_pf_cnp, pii_kinds,
    redact_fields, redact_text,
)


def synthetic_cnp(prefix12: str = "190010140000") -> str:
    """CNP SINTETIC (calculat cu algoritmul oficial) — nu aparține unei persoane reale din date."""
    w = (2, 7, 9, 1, 4, 6, 3, 5, 8, 2, 7, 9)
    r = sum(int(d) * x for d, x in zip(prefix12, w)) % 11
    return prefix12 + str(1 if r == 10 else r)


def test_cnp_valid_checks_control_digit_and_date():
    cnp = synthetic_cnp()
    assert cnp_valid(cnp)
    assert not cnp_valid(cnp[:12] + str((int(cnp[12]) + 1) % 10))   # cifră de control greșită
    assert not cnp_valid("1901301400001")                            # luna 13
    assert not cnp_valid("9900101400001")                            # prima cifră 9
    assert not cnp_valid("123")


def test_pii_kinds_is_precise():
    assert pii_kinds(f"Educatie | {synthetic_cnp()} INGINER") == ["CNP"]
    assert pii_kinds("referinta: tel: 0722 123 456") == ["telefon"]
    assert pii_kinds("contact +40 745-123-456") == ["telefon"]
    assert pii_kinds("donator CI seria XB nr 123456") == ["serie/nr CI"]
    # fals-pozitive de evitat: sume, EUID ONRC, hash-uri, numere instituționale fără context, CUI
    assert pii_kinds("suma 1234567890123 lei, EUID ROONRC.J40/1234/2020, g:69b8c3b9248b26d5") == []
    assert pii_kinds("sediu 0213124567, hotel 0213124567, CUI 14056826") == []


def test_redact_text_masks_only_pii():
    t = f"{synthetic_cnp()} | tel: 0722 123 456 | Fax: 0351-403202 | CI seria XB nr 123456 | sediu 0213124567"
    out = redact_text(t)
    # fixul instituțional (Fax al companiei) rămâne: e public, fără câștig de confidențialitate
    assert out == f"{CNP_MASK} | tel: {PHONE_MASK} | Fax: 0351-403202 | {CI_MASK} | sediu 0213124567"
    assert pii_kinds(out) == []
    assert redact_text("") == "" and redact_text(None) is None


@pytest.mark.parametrize("text", [
    "mobil (0722) 123 456", "tel 07 22 12 34 56", "0722/123.456", "0722 - 123 456",
    "+40(0)722 123 456", "0040 722 123 456", "Telefon domiciliu: 0257 - 123456",
    "0232-240880 | 0722123456 | 0232-240885",           # antet Europass: fixele lipite de mobil
])
def test_phone_formats_are_masked(text):
    assert "telefon" in pii_kinds(text)
    assert pii_kinds(redact_text(text)) == []


@pytest.mark.parametrize("text", [
    "Candidat X | CI RD - 123456 | 1.000", "CI RD 123456", "C.I. seria RD 123456",
    "CI nr. 123456 seria RD", "donator CI seria XB nr 123456",
])
def test_ci_formats_are_masked(text):
    assert "serie/nr CI" in pii_kinds(text)
    assert pii_kinds(redact_text(text)) == []


@pytest.mark.parametrize("text", [
    "diploma seria MA nr. 123456", "bancnota seria CS 1234567", "Tel:0351-403201, Fax: 0351-403202",
    "g:69b8c30722123456 g:1234567890123abc", "10.723.456.789 lei, data 07.12.2020",
    "EUID J2021000123456", "cont RO49AAAA1B31007593841111",   # IBAN cu cifre de control greșite
])
def test_non_personal_values_are_left_alone(text):
    assert pii_kinds(text) == [] and redact_text(text) == text


def test_iban_is_masked():
    assert iban_valid("RO49AAAA1B31007593840000")
    assert redact_text("cont RO49AAAA1B31007593840000 CEC") == f"cont {IBAN_MASK} CEC"


def test_is_pf_cnp_only_for_valid_cnp():
    assert is_pf_cnp(synthetic_cnp())
    assert not is_pf_cnp("1234567890123") and not is_pf_cnp("14056826") and not is_pf_cnp(None)


def test_redact_fields_in_place():
    rec = {"studii": f"{synthetic_cnp()} Politehnica", "experienta": "tel 0744111222", "nume": "X"}
    assert redact_fields(rec) is rec
    assert rec["studii"].startswith(CNP_MASK) and PHONE_MASK in rec["experienta"] and rec["nume"] == "X"


def test_clean_cui_rejects_cnp():
    assert clean_cui("RO 14056826") == "14056826"
    assert clean_cui(14056826) == "14056826"
    assert clean_cui("00014056826") == "14056826"   # zerourile de la început nu fac un CUI invalid
    assert clean_cui(synthetic_cnp()) is None      # 13 cifre = nu e CUI
    assert clean_cui("") is None and clean_cui(None) is None and clean_cui("7") is None
