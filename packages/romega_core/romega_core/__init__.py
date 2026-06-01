"""romega_core — biblioteca partajată ROMEGA.

Extrasă și generalizată din cdep-api-poc. Module:
- names      — normalizare nume RO (diacritice, ordine, titluri) + similaritate
- resolve    — entity resolution v0 (PersonRegistry: blocking, matching, romega_id)
- provenance — SourceRef (provenance pe fiecare fapt) + Meta (compat cdep export)
- models     — modele Pydantic canonice (Person, Organization, Company, ...)
"""

from __future__ import annotations

from romega_core.names import (
    canonical_name,
    fix_ro_diacritics,
    name_key,
    name_similarity,
    split_name,
    strip_diacritics,
)
from romega_core.provenance import Meta, SourceRef
from romega_core.resolve import MatchResult, MatchStatus, PersonRegistry

__all__ = [
    "strip_diacritics",
    "fix_ro_diacritics",
    "name_key",
    "canonical_name",
    "split_name",
    "name_similarity",
    "SourceRef",
    "Meta",
    "PersonRegistry",
    "MatchResult",
    "MatchStatus",
]

__version__ = "0.1.0"
