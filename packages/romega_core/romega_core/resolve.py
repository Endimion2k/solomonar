"""Entity resolution v0 — PersonRegistry.

Problema: aceeași persoană apare în zeci de surse cu nume scrise diferit, fără un ID comun
(CNP-ul e redactat). Dezambiguizăm pe nume normalizat + dată naștere + ID-uri externe.

Algoritm (vezi docs/02-DATA-MODEL.md §2):
  1. external id hit  -> match decisiv (crosswalk)
  2. blocking         -> candidați care împart un prefix de token (ieftin, recall-friendly)
  3. matching         -> scor pe nume (Jaro-Winkler+Jaccard) modulat de dată naștere
  4. decizie          -> >=high: matched · >=low: review (homonim posibil) · altfel: new

v0 ține registrul în memorie. Persistarea în SQLite (romega_id stabil între rulări) vine în
pipeline/gold/resolve, refolosind exact această logică.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum

from romega_core.names import canonical_name, name_key, name_similarity


class MatchStatus(StrEnum):
    MATCHED = "matched"   # legat la o persoană existentă cu încredere mare
    REVIEW = "review"     # posibil match (homonim) — necesită revizuire umană
    NEW = "new"           # persoană nouă


@dataclass
class MatchResult:
    romega_id: str
    status: MatchStatus
    score: float
    canonical_name: str


@dataclass
class _Record:
    romega_id: str
    key: str
    canonical_name: str
    birth_date: date | None
    aliases: set[str] = field(default_factory=set)


class PersonRegistry:
    """Registru in-memory de persoane cu rezoluție de entități.

    Parametri:
        high: prag peste care match-ul e automat (default 0.85)
        low:  prag sub care e persoană nouă; între low și high -> review (default 0.62)
    """

    def __init__(self, high: float = 0.85, low: float = 0.62) -> None:
        self.high = high
        self.low = low
        self._records: dict[str, _Record] = {}
        self._token_index: dict[str, set[str]] = defaultdict(set)  # prefix(4) -> {romega_id}
        self._xwalk: dict[tuple[str, str], str] = {}               # (system, ext_id) -> romega_id

    # -- API public --------------------------------------------------------- #
    def resolve(
        self,
        name: str,
        birth_date: date | None = None,
        external_ids: dict[str, str] | None = None,
    ) -> MatchResult:
        """Rezolvă un nume la un romega_id (existent sau nou)."""
        # 1. Crosswalk: dacă vreun ID extern e deja cunoscut -> match decisiv.
        if external_ids:
            for system, ext_id in external_ids.items():
                hit = self._xwalk.get((system, str(ext_id)))
                if hit:
                    self._absorb(hit, name, birth_date, external_ids)
                    rec = self._records[hit]
                    return MatchResult(hit, MatchStatus.MATCHED, 1.0, rec.canonical_name)

        key = name_key(name)
        if not key:
            raise ValueError(f"Nume gol după normalizare: {name!r}")

        # 2 + 3. Blocking + scoring.
        best_id, best_score = self._best_candidate(name, key, birth_date)

        # 4. Decizie.
        if best_id is not None and best_score >= self.high:
            self._absorb(best_id, name, birth_date, external_ids)
            return MatchResult(best_id, MatchStatus.MATCHED, best_score, self._records[best_id].canonical_name)

        if best_id is not None and best_score >= self.low:
            # Posibil homonim — întoarce candidatul dar marchează pt. revizuire; NU absoarbe.
            return MatchResult(best_id, MatchStatus.REVIEW, best_score, self._records[best_id].canonical_name)

        # Persoană nouă.
        rid = self._mint(key, birth_date)
        self._add(rid, key, name, birth_date, external_ids)
        return MatchResult(rid, MatchStatus.NEW, best_score, self._records[rid].canonical_name)

    def get(self, romega_id: str) -> _Record | None:
        return self._records.get(romega_id)

    def __len__(self) -> int:
        return len(self._records)

    # -- persistență (folosit de pipeline/gold/registry.py — SQLite) -------- #
    def records(self) -> list[_Record]:
        return list(self._records.values())

    def crosswalk_items(self) -> list[tuple[str, str, str]]:
        return [(system, ext, rid) for (system, ext), rid in self._xwalk.items()]

    def seed(
        self,
        romega_id: str,
        key: str,
        canonical: str,
        birth_date: date | None,
        aliases: list[str] | None = None,
        external_ids: list[tuple[str, str]] | None = None,
    ) -> None:
        """Reconstruiește un record dintr-un store persistent (NU re-mint-uiește ID-ul)."""
        rec = _Record(romega_id, key, canonical, birth_date, set(aliases or []))
        self._records[romega_id] = rec
        for tok in key.split(" "):
            if tok:
                self._token_index[tok[:4]].add(romega_id)
        if external_ids:
            for system, ext in external_ids:
                self._xwalk[(system, str(ext))] = romega_id

    # -- intern ------------------------------------------------------------- #
    def _best_candidate(
        self, name: str, key: str, birth_date: date | None
    ) -> tuple[str | None, float]:
        candidates: set[str] = set()
        for tok in key.split(" "):
            candidates |= self._token_index.get(tok[:4], set())

        best_id: str | None = None
        best_score = 0.0
        for cid in candidates:
            rec = self._records[cid]
            score = name_similarity(name, rec.canonical_name)
            score = self._apply_birthdate(score, birth_date, rec.birth_date)
            if score > best_score:
                best_score, best_id = score, cid
        return best_id, round(best_score, 4)

    @staticmethod
    def _apply_birthdate(score: float, a: date | None, b: date | None) -> float:
        """Data nașterii modulează scorul de nume.

        - ambele prezente și EGALE   -> boost (aproape decisiv)
        - ambele prezente și DIFERITE-> penalizare puternică (homonimi)
        - cel puțin una lipsă        -> neschimbat
        """
        if a is not None and b is not None:
            if a == b:
                return min(1.0, score + 0.3)
            return score * 0.3
        return score

    def _mint(self, key: str, birth_date: date | None) -> str:
        year = birth_date.year if birth_date else ""
        raw = f"{key}|{year}"
        return f"p:{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"

    def _add(
        self,
        rid: str,
        key: str,
        name: str,
        birth_date: date | None,
        external_ids: dict[str, str] | None,
    ) -> None:
        rec = _Record(rid, key, canonical_name(name), birth_date, {name})
        self._records[rid] = rec
        for tok in key.split(" "):
            self._token_index[tok[:4]].add(rid)
        if external_ids:
            for system, ext_id in external_ids.items():
                self._xwalk[(system, str(ext_id))] = rid

    def _absorb(
        self,
        rid: str,
        name: str,
        birth_date: date | None,
        external_ids: dict[str, str] | None,
    ) -> None:
        """Îmbogățește un record existent cu alias/dată/ID-uri externe noi."""
        rec = self._records[rid]
        rec.aliases.add(name)
        if rec.birth_date is None and birth_date is not None:
            rec.birth_date = birth_date
        if external_ids:
            for system, ext_id in external_ids.items():
                self._xwalk.setdefault((system, str(ext_id)), rid)
