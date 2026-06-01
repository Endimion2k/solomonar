"""Guard de redactare — împiedică scurgerea de date personale în output.

Legea 176/2010 art. 6 + GDPR: CNP, adrese complete, semnături rămân redactate la sursă și
NU trebuie republicate. Acest guard scanează output-ul și EȘUEAZĂ build-ul dacă detectează
PII. Vezi docs/04-LEGAL-GDPR.md §2.
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
