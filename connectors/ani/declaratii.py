"""Connector ani/declaratii — parser declarații de avere/interese (integritate.eu).

Parserul de AVERE e portat din cdep-api-poc/scripts/analiza_avere_pdf.py (cod funcțional pe
template-ul standardizat ANI, secțiuni I–VII). Lucrează pe TEXT (extras din PDF) — extracția
PDF (pdfplumber) + headless (Playwright pentru SPA) + OCR (pre-2022) sunt separate.

Componente:
- parse_avere_text  : text declarație → AvereParsed (agregate: imobile, conturi, venituri...)
- parse_interese    : text → InteresePozitii (board-uri / acționariat — best-effort)
- compute_avere_delta: variația averii între prima și ultima declarație
- AniConnector      : skeleton headless (necesită Playwright; se validează pe runner)

ATENȚIE: extragerea e BEST-EFFORT; PDF-urile scanate (pre-2022) necesită OCR. Guard de
redactare (CNP/telefon) în connectors/ani/redaction.py.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from romega_core.http import Client

# --- Regex & rate (portate din analiza_avere_pdf.py) ---
RE_AMOUNT = re.compile(
    r"(\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)\s*"
    r"(RON|EUR|EURO|USD|GBP|CHF|lei|euro|dolari)\b",
    re.IGNORECASE,
)
RE_MP = re.compile(r"(\d{1,5}(?:[.,]\d+)?)\s*m\s*²?", re.IGNORECASE)

RATES_TO_RON = {
    "RON": 1.0, "LEI": 1.0, "EUR": 5.05, "EURO": 5.05,
    "USD": 4.50, "DOLARI": 4.50, "GBP": 5.80, "CHF": 5.40,
}

# Secțiunile standardizate ANI (numerotare romană).
MARKERS = [
    "I. Bunuri imobile", "II. Bunuri mobile", "III. Bunuri mobile",
    "IV. Active financiare", "V. Datorii", "VI. Cadouri", "VII. Venituri",
]


class AvereParsed(BaseModel):
    text_extracted: bool = False
    needs_ocr: bool = False
    terenuri_count: int = 0
    cladiri_count: int = 0
    suprafata_total_mp: float = 0.0
    conturi_total_ron: float = 0.0
    venituri_anuale_ron: float = 0.0
    datorii_total_ron: float = 0.0
    auto_count: int = 0


class AvereDelta(BaseModel):
    n_declaratii: int = 0
    delta_conturi_ron: float = 0.0
    delta_venituri_ron: float = 0.0
    delta_imobile: int = 0


def _parse_amount(num_str: str) -> float | None:
    """'150.000', '75.500,50' → float (format românesc)."""
    s = num_str.replace(" ", "")
    if "." in s and "," in s:
        if s.rindex(",") > s.rindex("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        parts = s.split(",")
        s = s.replace(",", ".") if len(parts[-1]) <= 2 else s.replace(",", "")
    elif "." in s:
        parts = s.split(".")
        if len(parts[-1]) == 3 and len(parts) >= 2:
            s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def _to_ron(amount: float, currency: str) -> float:
    return amount * RATES_TO_RON.get(currency.upper(), 1.0)


def _extract_section(text: str, marker: str, next_markers: list[str]) -> str:
    start = text.find(marker)
    if start < 0:
        return ""
    end = len(text)
    for nm in next_markers:
        idx = text.find(nm, start + len(marker))
        if 0 < idx < end:
            end = idx
    return text[start:end]


def _sum_amounts(section: str, threshold: float = 100.0) -> float:
    total = 0.0
    for m in RE_AMOUNT.finditer(section):
        num = _parse_amount(m.group(1))
        if num and num > threshold:
            total += _to_ron(num, m.group(2))
    return total


def parse_avere_text(text: str) -> AvereParsed:
    """Parsează textul unei declarații de avere → agregate (portare din cdep)."""
    if len(text.strip()) < 100:
        return AvereParsed(text_extracted=False, needs_ocr=True)

    res = AvereParsed(text_extracted=True)

    # I — Bunuri imobile (terenuri + clădiri); formularul cere m², nu RON.
    sec_imobile = _extract_section(text, "I. Bunuri imobile", MARKERS)
    sec_terenuri = _extract_section(sec_imobile, "1. Terenuri", ["2. Clădiri", "II. Bunuri mobile"])
    sec_cladiri = _extract_section(sec_imobile, "2. Clădiri", ["II. Bunuri mobile"])
    for sec_text, count_attr in [(sec_terenuri, "terenuri_count"), (sec_cladiri, "cladiri_count")]:
        matches = list(RE_MP.finditer(sec_text))
        setattr(res, count_attr, len(matches))
        for m in matches:
            mp = _parse_amount(m.group(1))
            if mp and mp > 5:
                res.suprafata_total_mp += mp

    # IV — Active financiare · V — Datorii · VII — Venituri
    res.conturi_total_ron = _sum_amounts(_extract_section(text, "IV. Active financiare", MARKERS))
    res.datorii_total_ron = _sum_amounts(_extract_section(text, "V. Datorii", MARKERS))
    sec_venituri = _extract_section(text, "VII. Venituri", MARKERS) or _extract_section(
        text, "Venituri ale declarantului", MARKERS
    )
    res.venituri_anuale_ron = _sum_amounts(sec_venituri)

    # II — Bunuri mobile: nr. autovehicule
    sec_mobile = _extract_section(text, "II. Bunuri mobile", MARKERS)
    res.auto_count = len(
        re.findall(
            r"\b(autoturism|autovehicul|motociclet|tractor|remorc|iaht|şalup|salup)\w*",
            sec_mobile,
            re.IGNORECASE,
        )
    )
    return res


def parse_interese(text: str) -> list[str]:
    """Best-effort: liniile din secțiunea 'organe de conducere' (board-uri) → graf MEMBER_OF_BOARD.

    Pe template real, de rafinat. v0 extrage liniile de sub markerul cunoscut.
    """
    sec = _extract_section(
        text,
        "organele de conducere",
        ["calitatea de membru în", "alte contracte", "Prezenta declaratie", "VII."],
    )
    lines = [ln.strip(" -•\t") for ln in sec.splitlines()[1:] if ln.strip(" -•\t")]
    return [ln for ln in lines if len(ln) > 3]


def compute_avere_delta(declaratii: list[AvereParsed]) -> AvereDelta:
    """Variația averii între prima și ultima declarație (declaratii sortate cronologic)."""
    valid = [d for d in declaratii if d.text_extracted]
    if not valid:
        return AvereDelta()
    first, last = valid[0], valid[-1]
    return AvereDelta(
        n_declaratii=len(valid),
        delta_conturi_ron=last.conturi_total_ron - first.conturi_total_ron,
        delta_venituri_ron=last.venituri_anuale_ron - first.venituri_anuale_ron,
        delta_imobile=(last.terenuri_count + last.cladiri_count)
        - (first.terenuri_count + first.cladiri_count),
    )


def extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extrage text dintr-un PDF (pdfplumber). Lazy import — instalează cu `pip install pdfplumber`."""
    import io

    try:
        import pdfplumber
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("pdfplumber necesar: pip install pdfplumber") from e
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


class AniConnector:
    """Arhetip `headless`. declaratii.integritate.eu e SPA JS → necesită Playwright.

    Flux (pe runner): headless drive search form → index declarații + URL-uri PDF →
    fetch PDF (bronze) → extract_pdf_text (sau OCR pre-2022) → parse_avere_text → link Person.
    """

    source_id = "ani"
    BASE = "https://declaratii.integritate.eu"
    ARCHIVE = "https://old-declaratii.integritate.eu"

    def __init__(self, client: Client | None = None) -> None:
        self.client = client or Client()

    def search(self, **filters) -> list[dict]:  # pragma: no cover
        raise NotImplementedError(
            "ANI e SPA JS — necesită Playwright (headless). "
            "Instalează: pip install playwright && playwright install chromium. "
            "Se validează pe runner-ul self-hosted RO."
        )
