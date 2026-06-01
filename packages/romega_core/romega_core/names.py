"""Normalizare de nume românești pentru entity resolution.

Probleme reale rezolvate aici:
- **Diacritice cu cedilă vs virgulă-jos**: ș (U+0219) vs ş (U+015F), ț (U+021B) vs ţ (U+0163).
  Site-urile guvernamentale le amestecă — trebuie pliate amândouă la 's'/'t'.
- **Ordinea numelui**: "POPESCU Ion" (nume cu majuscule primul, uzual în acte oficiale) vs
  "Ion Popescu". Pentru MATCHING folosim o cheie invariantă la ordine (set de token-uri).
- **Titluri/onorifice**: dr., ing., prof., av., gen. etc.

API principal:
- strip_diacritics(s)   -> fără diacritice
- name_key(s)           -> cheie canonică invariantă la ordine (pt. blocking/matching)
- canonical_name(s)     -> formă de afișare (Title Case, fără titluri)
- split_name(s)         -> (nume_familie, prenume) best-effort (semnal majuscule)
- name_similarity(a, b) -> scor 0..1
"""

from __future__ import annotations

import re
import unicodedata

# Mapare explicită ÎNAINTE de NFKD (acoperă atât precompus cât și cedilă-vs-virgulă).
_RO_MAP = str.maketrans(
    {
        "ă": "a", "â": "a", "î": "i", "ș": "s", "ş": "s", "ț": "t", "ţ": "t",
        "Ă": "A", "Â": "A", "Î": "I", "Ș": "S", "Ş": "S", "Ț": "T", "Ţ": "T",
    }
)

# Titluri/onorifice de eliminat (normalizate, fără punct).
_TITLES: frozenset[str] = frozenset(
    {
        "dr", "drd", "prof", "conf", "lect", "asist", "ing", "ec", "av", "jr", "sr",
        "gen", "col", "mr", "cpt", "lt", "plt", "slt", "mp", "pr", "ps", "phd",
        "dl", "dna", "dna", "d-na", "dlui", "doamna", "domnul",
    }
)

_NONALPHA = re.compile(r"[^a-z]+")


def strip_diacritics(s: str) -> str:
    """Elimină diacriticele românești (cedilă ȘI virgulă-jos) + orice accent rezidual."""
    s = s.translate(_RO_MAP)
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


# Cedilă (ş/ţ) → virgulă-jos (ș/ț): standardul RO modern, PĂSTRÂND diacriticele.
_RO_DISPLAY_MAP = str.maketrans({"ş": "ș", "Ş": "Ș", "ţ": "ț", "Ţ": "Ț"})


def fix_ro_diacritics(s: str) -> str:
    """Normalizează forma diacriticelor pentru AFIȘARE (cedilă → virgulă-jos), păstrându-le.

    Opus lui strip_diacritics: aici păstrăm diacriticele, doar le standardizăm forma.
    cdep.ro/senat.ro servesc adesea formele vechi cu cedilă (ş/ţ).
    """
    return s.translate(_RO_DISPLAY_MAP)


def _tokens(s: str) -> list[str]:
    """Token-uri alfabetice normalizate (fără diacritice, lowercase, fără titluri, len>=2)."""
    flat = strip_diacritics(s).lower().replace("-", " ")
    raw = _NONALPHA.split(flat)
    return [t for t in raw if len(t) >= 2 and t not in _TITLES]


def name_key(s: str) -> str:
    """Cheie canonică invariantă la ordine: token-uri sortate, unice, fără diacritice/titluri.

    >>> name_key("POPESCU Ion") == name_key("Ion Popescu")
    True
    >>> name_key("Dr. Ștefan Gheorghiu") == name_key("Stefan Gheorghiu")
    True
    """
    return " ".join(sorted(set(_tokens(s))))


def canonical_name(s: str) -> str:
    """Formă de afișare: fără titluri, spații colapsate, Title Case, ordine păstrată."""
    flat = re.sub(r"\s+", " ", s.strip())
    parts = []
    for tok in flat.split(" "):
        bare = strip_diacritics(tok).lower().strip(".")
        if bare in _TITLES or not bare:
            continue
        parts.append(tok)
    return " ".join(p.capitalize() if not p.isupper() else p.title() for p in parts)


def split_name(s: str) -> tuple[str | None, str | None]:
    """Best-effort (nume_familie, prenume) pe baza semnalului de majuscule.

    Convenția în actele oficiale RO: numele de familie cu MAJUSCULE, primul.
    Dacă nu există semnal de majuscule, întoarce (None, None) — ambiguu pentru v0.

    >>> split_name("POPESCU Ion Vasile")
    ('Popescu', 'Ion Vasile')
    """
    flat = re.sub(r"\s+", " ", s.strip())
    toks = [t for t in flat.split(" ") if strip_diacritics(t).lower().strip(".") not in _TITLES]
    if not toks:
        return (None, None)
    upper = [t for t in toks if t.isupper() and len(t) >= 2]
    lower = [t for t in toks if not (t.isupper() and len(t) >= 2)]
    if upper and lower:
        surname = " ".join(t.capitalize() for t in upper)
        given = " ".join(t.capitalize() if not t.isupper() else t for t in lower)
        return (surname, given)
    return (None, None)


# --------------------------------------------------------------------------- #
# Similaritate                                                                 #
# --------------------------------------------------------------------------- #
def _jaro(s1: str, s2: str) -> float:
    if s1 == s2:
        return 1.0
    len1, len2 = len(s1), len(s2)
    if len1 == 0 or len2 == 0:
        return 0.0
    match_distance = max(0, max(len1, len2) // 2 - 1)
    m1 = [False] * len1
    m2 = [False] * len2
    matches = 0
    for i in range(len1):
        start = max(0, i - match_distance)
        end = min(i + match_distance + 1, len2)
        for j in range(start, end):
            if m2[j] or s1[i] != s2[j]:
                continue
            m1[i] = m2[j] = True
            matches += 1
            break
    if matches == 0:
        return 0.0
    transpositions = 0
    k = 0
    for i in range(len1):
        if not m1[i]:
            continue
        while not m2[k]:
            k += 1
        if s1[i] != s2[k]:
            transpositions += 1
        k += 1
    transpositions //= 2
    return (matches / len1 + matches / len2 + (matches - transpositions) / matches) / 3.0


def jaro_winkler(s1: str, s2: str, prefix_weight: float = 0.1) -> float:
    """Jaro-Winkler (pur Python, fără dependențe)."""
    j = _jaro(s1, s2)
    prefix = 0
    for a, b in zip(s1, s2):
        if a != b:
            break
        prefix += 1
        if prefix == 4:
            break
    return j + prefix * prefix_weight * (1 - j)


def name_similarity(a: str, b: str) -> float:
    """Scor 0..1 între două nume, robust la ordine și diacritice.

    - set de token-uri identic  -> 1.0
    - altfel: combinație Jaccard(token-uri) + Jaro-Winkler(cheie sortată)
    """
    ta, tb = set(_tokens(a)), set(_tokens(b))
    if not ta or not tb:
        return 0.0
    if ta == tb:
        return 1.0
    inter = len(ta & tb)
    union = len(ta | tb)
    jaccard = inter / union if union else 0.0
    jw = jaro_winkler(name_key(a), name_key(b))
    return round(0.6 * jaccard + 0.4 * jw, 4)
