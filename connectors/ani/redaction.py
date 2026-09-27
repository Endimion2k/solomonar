"""Guard de redactare — împiedică scurgerea de date personale în output.

Legea 176/2010 art. 6 + GDPR: CNP, adrese complete, semnături rămân redactate la sursă și
NU trebuie republicate. Acest guard scanează output-ul și EȘUEAZĂ build-ul dacă detectează
PII. Vezi docs/04-LEGAL-GDPR.md §2.

Două niveluri:
- find_pii / assert_clean: detecție grosieră (istorică), folosită de harvesterele de declarații
  ca să blocheze înregistrări întregi. Neschimbată, ca să nu se modifice comportamentul lor.
- pii_kinds / redact_text / cnp_valid / clean_cui: detecție PRECISĂ + mascare, pentru textul liber
  publicat în data/v1 (CV-uri, rapoarte RVC, …) și pentru garda pipeline/scrub_pii.py.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

# CNP = 13 cifre, prima 1-8 (sex/secol). Ex: 1850101080012.
RE_CNP = re.compile(r"\b[1-8]\d{12}\b")
# Telefon RO: 07xxxxxxxx / 02xx / 03xx (10 cifre).
RE_PHONE = re.compile(r"\b0[237]\d{8}\b")
# Serie+număr CI (ex: "seria XX nr 123456").
RE_CI = re.compile(r"\bseria\s+[A-Z]{2}\s+nr\.?\s*\d{6}\b", re.IGNORECASE)


def find_pii(text: str) -> list[str]:
    """Întoarce lista tipurilor de PII detectate (gol = curat)."""
    issues: list[str] = []
    if RE_CNP.search(text):
        issues.append("CNP")
    if RE_PHONE.search(text):
        issues.append("telefon")
    if RE_CI.search(text):
        issues.append("serie/nr CI")
    return issues


def assert_clean(model: BaseModel) -> None:
    """Ridică ValueError dacă serializarea modelului conține PII. De rulat înainte de export."""
    issues = find_pii(model.model_dump_json())
    if issues:
        raise ValueError(f"PII detectat în output (redactare obligatorie): {issues}")


# ---------------------------------------------------------------------------
# Detecție precisă + mascare (pentru output-ul publicat în data/v1).
#
# Politica (vezi docs/04-LEGAL-GDPR.md):
# - CNP: doar dacă trece cifra de control ȘI are lună/zi/județ plauzibile (altfel: EUID, sume, hash).
# - telefon MOBIL (07[2-9]…): oriunde, în orice format uzual.
# - telefon FIX (02x/03x): de regulă e al unei instituții (public) → mascat DOAR lângă o etichetă
#   personală („domiciliu”, „personal”…) sau lipit de un mobil deja mascat (antet Europass de CV).
# - serie/număr CI (inclusiv „CI RD - 123456”), exceptând diplome/certificate/bancnote.
# - IBAN RO valid (mod-97) în text liber.
# ---------------------------------------------------------------------------

_CNP_WEIGHTS = (2, 7, 9, 1, 4, 6, 3, 5, 8, 2, 7, 9)
# 13 cifre nelipite de alte cifre/litere (evită hash-uri hex), dar acceptă prefixul lipit „CNP”
_CNP_CANDIDATE = re.compile(r"(?:(?<=CNP)|(?<=cnp)|(?<![0-9A-Za-z]))[1-8]\d{12}(?!\d)")

_S = r"[\s.\-/]{0,2}"
_MOBILE = re.compile(
    # nu după „cifră.” (date: 01.07.2012 - 31.12…) și nu „07.2012” (lună.an)
    r"(?<![0-9A-Za-z+])(?<!\d[.\-/])(?!07[.\-/](?:19|20)\d\d(?!\d))(?:"
    r"(?:(?:\+|00)40" + _S + r"(?:\(0\)" + _S + r")?|0)7" + _S + r"[2-9]" + _S + r"\d"
    r"|\(07[2-9]\d\)"
    r")(?:[\s.\-/]{0,3}\d){6}(?![0-9A-Za-z])"
)
_FIX = r"(?<![0-9A-Za-z])(?:(?:\+|00)40" + _S + r"|\(?0)[23]\d\)?(?:[\s.\-/]{0,3}\d){7}(?![0-9A-Za-z])"
_FIX_RE = re.compile(_FIX)
_PERSONAL_LABEL = re.compile(r"(?i)(?:domiciliu|acas[aă]|personal|privat)[\s:.\-]{0,6}$")
_NEAR_MASK_SEP = re.compile(r"^\s*[|,/;]\s*$")

_CI = re.compile(
    r"(?i)(?:"
    r"(?<![A-Za-z])(?:C\.?\s?I\.?|B\.?\s?I\.?|carte\s+de\s+identitate|buletin)\s*[:\-]?\s*"
    r"(?:seria\s*)?(?-i:[A-Z]{2})\s*[-–,.:]?\s*(?:(?:nr\.?|num[aă]r(?:ul)?)\s*[:\-]?\s*)?\d{6}(?!\d)"
    r"|\bseri[ae]\s*:?\s*(?-i:[A-Z]{2})\s*,?\s*(?:nr\.?|num[aă]r(?:ul)?)\s*:?\s*\d{6}(?!\d)"
    r"|\b(?:nr\.?|num[aă]r(?:ul)?)\s*\d{6}\s*,?\s*seri[ae]\s*:?\s*(?-i:[A-Z]{2})\b"
    r")"
)
_CI_NOT_ID = re.compile(r"(?i)(?:diplom|certificat|atestat|brevet|bancnot|legitima)")
_IBAN = re.compile(r"(?<![A-Za-z0-9])RO\s?\d{2}\s?[A-Z]{4}(?:\s?[A-Z0-9]{4}){4}(?![A-Za-z0-9])")

CNP_MASK = "[CNP redactat]"
PHONE_MASK = "[telefon redactat]"
CI_MASK = "[CI redactat]"
IBAN_MASK = "[IBAN redactat]"


def cnp_valid(s: str) -> bool:
    """True dacă `s` (13 cifre) e un CNP plauzibil: cifra de control + lună/zi/județ valide."""
    if len(s) != 13 or not s.isdigit() or s[0] not in "12345678":
        return False
    month, day, county = int(s[3:5]), int(s[5:7]), int(s[7:9])
    if not (1 <= month <= 12 and 1 <= day <= 31 and (1 <= county <= 52 or county == 70)):
        return False
    r = sum(int(d) * w for d, w in zip(s[:12], _CNP_WEIGHTS)) % 11
    return int(s[12]) == (1 if r == 10 else r)


def iban_valid(s: str) -> bool:
    """Validare IBAN (ISO 13616, mod-97)."""
    s = re.sub(r"\s", "", s).upper()
    if len(s) < 15 or not s.isalnum():
        return False
    num = "".join(str(int(c, 36)) for c in s[4:] + s[:4])
    return int(num) % 97 == 1


def _ci_matches(text: str):
    for m in _CI.finditer(text):
        if not _CI_NOT_ID.search(text[max(0, m.start() - 30):m.start()]):
            yield m


def _personal_fixed(text: str):
    """Numere fixe care par personale: după o etichetă personală sau lipite de un mobil mascat."""
    for m in _FIX_RE.finditer(text):
        before, after = text[max(0, m.start() - 40):m.start()], text[m.end():m.end() + 40]
        if _PERSONAL_LABEL.search(before):
            yield m
            continue
        i = before.rfind(PHONE_MASK)
        if i >= 0 and _NEAR_MASK_SEP.match(before[i + len(PHONE_MASK):]):
            yield m
            continue
        j = after.find(PHONE_MASK)
        if j >= 0 and _NEAR_MASK_SEP.match(after[:j]):
            yield m


def pii_kinds(text: str) -> list[str]:
    """Tipurile de PII detectate PRECIS în text (gol = curat). Vezi redact_text."""
    kinds: list[str] = []
    if any(cnp_valid(m.group()) for m in _CNP_CANDIDATE.finditer(text)):
        kinds.append("CNP")
    masked_mobiles = _MOBILE.sub(PHONE_MASK, text)
    if masked_mobiles != text or any(True for _ in _personal_fixed(masked_mobiles)):
        kinds.append("telefon")
    if any(True for _ in _ci_matches(text)):
        kinds.append("serie/nr CI")
    if any(iban_valid(m.group()) for m in _IBAN.finditer(text)):
        kinds.append("IBAN")
    return kinds


def _sub_matches(text: str, matches, mask: str) -> str:
    out, last = [], 0
    for m in matches:
        out.append(text[last:m.start()])
        out.append(mask)
        last = m.end()
    out.append(text[last:])
    return "".join(out)


def redact_text(text: str) -> str:
    """Maschează CNP-uri valide, telefoane mobile (+ fixe personale), serii CI și IBAN-uri."""
    if not text:
        return text
    out = _CNP_CANDIDATE.sub(lambda m: CNP_MASK if cnp_valid(m.group()) else m.group(), text)
    out = _IBAN.sub(lambda m: IBAN_MASK if iban_valid(m.group()) else m.group(), out)
    out = _MOBILE.sub(PHONE_MASK, out)
    out = _sub_matches(out, list(_personal_fixed(out)), PHONE_MASK)
    return _sub_matches(out, list(_ci_matches(out)), CI_MASK)


def redact_fields(rec: dict, fields=("studii", "experienta")) -> dict:
    """Aplică redact_text in-place pe câmpurile text ale unei înregistrări (ex. CV) și o întoarce."""
    for f in fields:
        if isinstance(rec.get(f), str):
            rec[f] = redact_text(rec[f])
    return rec


def clean_cui(raw) -> str | None:
    """CUI românesc = 2-10 cifre (zerourile de la început nu contează). Altfel → None."""
    if raw is None:
        return None
    digits = re.sub(r"\D", "", str(raw)).lstrip("0")
    return digits if 2 <= len(digits) <= 10 else None


def is_pf_cnp(raw) -> bool:
    """True dacă identificatorul e de fapt CNP-ul unei persoane fizice (PFA/II) — nu se publică."""
    digits = re.sub(r"\D", "", str(raw or ""))
    return cnp_valid(digits)
