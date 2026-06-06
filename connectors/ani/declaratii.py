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

import os
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


class InteresParsed(BaseModel):
    """Declarație de INTERESE structurată (cele 5 secțiuni standard). Best-effort, tolerant OCR."""
    text_extracted: bool = False
    actionariat_count: int = 0      # 1. asociat/acționar la societăți
    conducere_firme_count: int = 0  # 2. membru organe conducere/administrare/control
    prof_sindicat_count: int = 0    # 3. asociații profesionale / sindicale
    partid_count: int = 0           # 4. organe de conducere ale partidelor politice
    contracte_count: int = 0        # 5. contracte din fonduri publice / cu firme de stat
    valoare_actiuni_ron: float = 0.0
    valoare_contracte_ron: float = 0.0
    entitati: list[str] = []        # nume entități extrase (firme/ONG/partide) — pt. graf
    has_any: bool = False


# secțiune interese -> fraze distinctive (pe text normalizat fără spații, robust la OCR)
_INT_SECTIONS = [
    ("actionariat", ["asociatsauactionar", "asociatsiactionar"]),
    ("conducere", ["organeledeconducere", "calitateademembruinorganele"]),
    ("prof_sindicat", ["asociatiilorprofesionale", "profesionalesi", "sindicale"]),
    ("partid", ["partidelorpolitice", "partiduluipolitic"]),
    ("contracte", ["contracteinclusiv", "contracte,inclusiv", "asistentajuridica", "finantatedela"]),
]
_INT_BOILER = (
    "unitatea", "denumireasiadresa", "calitateadetinuta", "nrdepartisociale", "valoareatotala",
    "tipulcontractului", "dataincheierii", "duratacontractului", "persoanelecucare", "sevordeclara",
    "beneficiaruldecontract", "institutiacontractanta", "proceduraprin", "nota", "prinrude",
    "numelepersoanei", "denumireasiadresa", "valoareabeneficiului",
)
_RE_ENTITY = re.compile(
    r"(S\.?\s?C\.?\s|\bS\.?\s?R\.?\s?L\.?\b|\bS\.?\s?A\.?\b|\bP\.?\s?F\.?\s?A\.?\b|"
    r"asocia[tţț]i|funda[tţț]i|\bpartidul\b|\bP\.?N\.?L\b|\bP\.?S\.?D\b|\bU\.?S\.?R\b|"
    r"sindicat|federa[tţț]i|uniune|cooperativ|regia\b|compania\b|\bONG\b)",
    re.IGNORECASE,
)


def _norm_ns(s: str) -> str:
    """Normalizare agresivă pt. detecție markeri: fără diacritice, lower, fără spații."""
    from romega_core.names import strip_diacritics
    return strip_diacritics(s).lower().replace(" ", "")


def _norm_sp(s: str) -> str:
    """Normalizare pt. potrivire linii boilerplate: fără diacritice, lower, spații colapsate."""
    from romega_core.names import strip_diacritics
    return " ".join(strip_diacritics(s).lower().split())


_RE_SUBROW = re.compile(r"^\s*\d{1,2}\.\d{1,2}\b")  # rând real numerotat: 1.1, 3.1, 5.1...
_SENT_CONNECTORS = ("precum si", "sau alte", "ori ale", "in cadrul exercitarii", "denumirea si adresa",
                    "se vor declara", "obtinute ori aflate")
_INT_BOILER_SET = None


def _boiler_set() -> set:
    """Liniile-șablon ale formularului (învățate din corpus) — de scăzut la numărarea intrărilor."""
    global _INT_BOILER_SET
    if _INT_BOILER_SET is None:
        import json
        import os
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        p = os.path.join(root, "data", "v1", "declaratii", "_interese_boilerplate.json")
        try:
            _INT_BOILER_SET = set(json.load(open(p, encoding="utf-8")))
        except Exception:
            _INT_BOILER_SET = set()
    return _INT_BOILER_SET


def classify_declaration(text: str) -> set[str]:
    """Ce tipuri conține documentul: {'avere'}, {'interese'} sau ambele (doc combinat)."""
    ns = _norm_ns(text)
    kinds = set()
    if "declaratiedeavere" in ns or "bunuriimobile" in ns or "activefinanciare" in ns:
        kinds.add("avere")
    if ("declaratiedeinterese" in ns or "asociatsauactionar" in ns
            or "organeledeconducere" in ns):
        kinds.add("interese")
    return kinds


def parse_interese_text(text: str) -> InteresParsed:
    """Parsează declarația de interese → cele 5 secțiuni (counts + entități). Tolerant la OCR."""
    if len(text.strip()) < 80:
        return InteresParsed(text_extracted=False)
    res = InteresParsed(text_extracted=True)
    lines = [ln.strip(" -•\t|") for ln in text.splitlines()]

    # localizează începutul fiecărei secțiuni (în ordinea documentului)
    starts: dict[str, int] = {}
    for i, ln in enumerate(lines):
        ns = _norm_ns(ln)
        if not ns:
            continue
        for key, phrases in _INT_SECTIONS:
            if key not in starts and any(p in ns for p in phrases):
                starts[key] = i
    order = sorted(starts.items(), key=lambda kv: kv[1])

    boiler = _boiler_set()
    entities: list[str] = []
    for idx, (key, s) in enumerate(order):
        end = order[idx + 1][1] if idx + 1 < len(order) else len(lines)
        body = lines[s + 1:end]
        n = 0
        for ln in body:
            sp = _norm_sp(ln)
            if len(sp) < 4 or sp in boiler:            # scade liniile-șablon ale formularului
                continue
            if any(b in sp.replace(" ", "") for b in _INT_BOILER):
                continue
            long_sentence = len(sp.split()) > 12 or any(c in sp for c in _SENT_CONNECTORS)
            numbered = bool(_RE_SUBROW.match(ln))      # rând real 1.1/3.1...
            has_entity = bool(_RE_ENTITY.search(ln))
            if numbered or (has_entity and not long_sentence):
                n += 1
                if has_entity and not long_sentence and len(entities) < 60:
                    entities.append(ln.strip()[:80])
        section_amt = _sum_amounts(" ".join(body))
        if key == "actionariat":
            res.actionariat_count = n
            res.valoare_actiuni_ron = section_amt
        elif key == "conducere":
            res.conducere_firme_count = n
        elif key == "prof_sindicat":
            res.prof_sindicat_count = n
        elif key == "partid":
            res.partid_count = n
        elif key == "contracte":
            res.contracte_count = n
            res.valoare_contracte_ron = section_amt
    res.entitati = sorted(set(entities))
    res.has_any = bool(res.actionariat_count or res.conducere_firme_count or res.prof_sindicat_count
                       or res.partid_count or res.contracte_count)
    return res


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


_OCR_ENGINE = None


_OCR_CUDA = None  # True dacă sesiunea OCR rulează efectiv pe GPU


def _add_cuda_dlls() -> None:
    """Pune DLL-urile CUDA din wheel-urile nvidia-*-cu12 (fără admin) în calea de căutare.

    Atât add_dll_directory CÂT ȘI PATH: onnxruntime rezolvă dependențele tranzitive (cublasLt,
    cudnn) prin search-ul clasic, care onorează PATH; add_dll_directory singur nu e suficient.
    """
    try:
        import nvidia
        base = os.path.dirname(nvidia.__file__)
        dirs = []
        for sub in os.listdir(base):
            bindir = os.path.join(base, sub, "bin")
            if os.path.isdir(bindir):
                dirs.append(bindir)
                try:
                    os.add_dll_directory(bindir)
                except Exception:
                    pass
        if dirs:
            os.environ["PATH"] = os.pathsep.join(dirs) + os.pathsep + os.environ.get("PATH", "")
    except Exception:
        pass


def _ocr_engine():
    """Singleton RapidOCR per proces. Folosește GPU (CUDA) dacă e disponibil, altfel CPU 1-thread.

    Pe GPU (RTX) OCR-ul e ~10-30× mai rapid → fezabil pe zeci de mii de scanate. Pe CPU forțăm
    1 thread/proces ca paralelismul pe procese să fie real (altfel suprasubscriere pe 16 core-uri).
    """
    global _OCR_ENGINE, _OCR_CUDA
    if _OCR_ENGINE is None:
        for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
            os.environ.setdefault(_v, "1")
        _add_cuda_dlls()
        import onnxruntime as _ort
        _OCR_CUDA = "CUDAExecutionProvider" in _ort.get_available_providers()
        if not getattr(_ort.InferenceSession, "_romega_patch", False):
            _orig = _ort.InferenceSession.__init__

            def _patched(self, *a, **k):
                so = k.get("sess_options")
                if so is not None:
                    so.intra_op_num_threads = 1
                    so.inter_op_num_threads = 1
                if _OCR_CUDA:  # GPU cu PLAFON pe arenă (gpu_mem_limit): cache rapid SUB plafon,
                    # 6000MB: suficient ca detectorul să NU se înfometeze (3300 era prea mic → 0 boxe
                    # = empty). 1 worker la 6000 = sigur (6.5GB<8); 2 workeri ar depăși 8GB → thrash.
                    _mem = int(os.environ.get("ROMEGA_GPU_MEM_MB", "6000")) * 1024 * 1024
                    k["providers"] = [   # fără kSameAsRequested (ăla dezactiva cache-ul → lent)
                        ("CUDAExecutionProvider", {"gpu_mem_limit": _mem}),
                        "CPUExecutionProvider",
                    ]
                _orig(self, *a, **k)

            _patched._romega_patch = True
            _ort.InferenceSession.__init__ = _patched
            _ort.InferenceSession._romega_patch = True
        from rapidocr_onnxruntime import RapidOCR
        _OCR_ENGINE = RapidOCR()
    return _OCR_ENGINE


def extract_pdf_text_ocr(pdf_bytes: bytes, dpi: int = 200, max_pages: int = 14,
                         max_px: int = 2400) -> str:
    """OCR pentru PDF-uri SCANATE (fără strat de text). PyMuPDF randează → RapidOCR (română+latină).

    Lazy import (pip install pymupdf rapidocr-onnxruntime). max_pages limitează scanele uriașe.
    max_px PLAFONEAZĂ latura lungă: scanele la rezoluție enormă (ex. DSVSA Constanța 2016 =
    5167×7307 = 37.8MP) ar depăși memoria GPU → OOM. Le reducem la ~max_px (suficient pt. OCR).
    """
    import fitz  # PyMuPDF
    import numpy as np

    eng = _ocr_engine()
    out: list[str] = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for i, page in enumerate(doc):
            if i >= max_pages:
                break
            long_pts = max(page.rect.width, page.rect.height) or 1.0
            zoom = min(dpi / 72.0, max_px / long_pts)  # 200dpi normal, dar plafon pe pagini uriașe
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
            if pix.n == 4:
                img = img[:, :, :3]
            res, _ = eng(img, use_cls=False)  # formularele-s drepte → sar clasificarea unghiului
            if res:
                out.append("\n".join(r[1] for r in res))
    return "\n".join(out)


FIELDS_BASE = "https://declaratii.integritate.eu/api/fields"


def normalize_ani_organizations(raw: list[dict]) -> list[dict]:
    """Normalizează lista de organizații ANI (entități care depun declarații)."""
    return [
        {"ani_id": o.get("id"), "name": (o.get("numeOrganizatie") or "").strip()}
        for o in raw
        if (o.get("numeOrganizatie") or "").strip()
    ]


def fetch_ani_fields(client: Client | None = None) -> dict:
    """Harvest API-ul DESCHIS de fields ANI (judete, functii, organizations).

    Acesta NU e Turnstile-gated (spre deosebire de căutarea de declarații). 11.700 organizații,
    1.109 funcții, 42 județe — registrul entităților care depun declarații la ANI.
    """
    client = client or Client()
    out: dict = {}
    for field in ("judete", "functii", "organizations"):
        r = client.get(f"{FIELDS_BASE}/{field}")
        r.raise_for_status()
        out[field] = r.json()
    return out


class AniConnector:
    """Arhetip `headless`. declaratii.integritate.eu — confirmat DRIVABLE cu Playwright (iunie 2026).

    DESCOPERIRE VALIDATĂ (probe Playwright live):
    - Portal nou (BASE): SPA Angular Material. Title "Declaratii de avere si interese".
      Căutare simplă = PRIMUL `input` (formControl ssidLastName). Buton submit: text "Cauta".
      Căutare avansată: Instituție, Funcție, Localitate, Județ, Data, Tip declarație.
      RĂMAS DE FĂCUT: extragerea rezultatelor — sunt în componente Angular custom (NU `<a href>`);
      accesul la PDF pare a fi prin acțiune JS (download/blob), de reverse-engineering.
    - Portal vechi (ARCHIVE, 2008–2022): server-rendered DAR ICEfaces JSF (ice.captureSubmit) —
      căutare prin Ajax stateful (view-state + token), de asemenea non-trivial.

    Flux țintă (pe runner): headless → search → result component → PDF URL/blob → fetch (bronze)
    → extract_pdf_text (sau OCR pre-2022) → parse_avere_text → redaction.assert_clean → link Person.
    Parserul + guard-ul + delta sunt GATA (Faza 2); rămâne doar driverul de rezultate.
    """

    source_id = "ani"
    BASE = "https://declaratii.integritate.eu"
    ARCHIVE = "https://old-declaratii.integritate.eu"
    SEARCH_INPUT = "input"          # primul input = nume (căutare simplă)
    SEARCH_BUTTON = "Cauta"          # text buton submit

    def __init__(self, client: Client | None = None) -> None:
        self.client = client or Client()

    def search(self, last_name: str, **filters) -> list[dict]:  # pragma: no cover - SPA live
        raise NotImplementedError(
            "ANI confirmat drivable cu Playwright (vezi DESCOPERIRE în docstring): "
            "search input = primul input, buton 'Cauta'. RĂMAS: extragerea rezultatelor din "
            "componenta Angular custom + mecanismul de acces PDF (acțiune JS). Subproiect dedicat."
        )
