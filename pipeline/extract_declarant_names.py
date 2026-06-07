"""Extrage NUMELE declarantului din numele fișierului PDF al declarației.

Multe surse numesc PDF-urile pe persoană: SINEA-D.-DUMITRU-ALEXANDRU.pdf, AVRAM-C.-LILIANA.pdf,
Albu-Mihaela-Maria-DA-A.pdf. Extragem numele (fără markeri DA/DI/an/inițiale) → declarațiile devin
person-linked → cross-ref cu directorii SOE și demnitarii. Ministere folosesc nume generice (da_ba)
→ fără nume (raportat onest).

Rulare: `python -m pipeline.extract_declarant_names [apply]`  (fără 'apply' = DRY-RUN).
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys
import unicodedata
from urllib.parse import unquote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DECL = os.path.join(ROOT, "data/v1/declaratii")

# markeri de eliminat (tip declarație, an, cuvinte de serviciu, sufixe de stare/dată)
_MARKERS = re.compile(
    r"\b(DA|DI|DAI|DAV|DAA|A|I|DECL|DECLARATIE|DECLARATIA|AVERE|AVERI|INTERESE|INTERES|"
    r"DE|SI|FINAL|FINALA|COPY|COPIE|SEMNAT|SEMNATA|ANONIM\w*|REDACT\w*|SCAN\w*|NR|SEM|"
    r"ACTUALIZ\w*|MODIF\w*|UPDATE|REV|VERSIUNE|FORMULAR|"
    r"ZILE|LA|DUPA|NUMIRE|NUMARE|INCETARE|INCEPERE|EXERCITARE|MANDAT|MANDATULUI|ANUAL\w*|"
    r"PANA|LUNA|LUNI|CONFORM|ART|LEGEA|DATA|"
    r"IANUARIE|FEBRUARIE|MARTIE|APRILIE|MAI|IUNIE|IULIE|AUGUST|SEPTEMBRIE|OCTOMBRIE|NOIEMBRIE|DECEMBRIE|"
    r"2\d{3}|20\d\d20\d\d|\d{1,2})\b",
    re.I,
)
# prefixe demnitate în câmpul institutie (numele e după prefix)
_INST_PREFIX = re.compile(r"^(Deputat(ul|a)?|Senator(ul|ul|ea|oarea)?)\b[:\s]*", re.I)
# cuvinte generice care arată că filename-ul NU e un nume de persoană
_GENERIC = {"DA BA", "DA", "DI", "FORMULAR", "DECLARATIE", "MODEL", "TEMPLATE", "ANONIM"}


def extract_name(url: str) -> str | None:
    fn = unquote(url.rsplit("/", 1)[-1])
    fn = re.sub(r"\.pdf$", "", fn, flags=re.I)
    s = re.sub(r"[._\-+]+", " ", fn)              # separatori → spațiu
    s = re.sub(r"\b([A-Za-zĂÂÎȘȚăâîșț])\b\.?", " ", s)  # inițiale o-literă (D., C.)
    s = _MARKERS.sub(" ", s)
    s = re.sub(r"\d", " ", s)                     # cifre rămase
    toks = [t for t in s.split() if len(t) >= 2 and re.match(r"[A-Za-zĂÂÎȘȚăâîșț]", t)]
    if len(toks) < 2:
        return None
    name = " ".join(toks).upper().strip()
    if name in _GENERIC or len(name) < 5:
        return None
    return name


def extract_from_institutie(inst: str) -> str | None:
    """Pt. parlamentari: institutie='Deputat {Nume}' / 'Senator {Nume}' → numele."""
    m = _INST_PREFIX.match(inst or "")
    if not m:
        return None
    rest = inst[m.end():].strip()
    toks = [t for t in re.split(r"\s+", rest) if len(t) >= 2 and re.match(r"[A-Za-zĂÂÎȘȚăâîșț]", t)]
    return " ".join(toks).upper() if len(toks) >= 2 else None


def norm_name(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().upper()
    return " ".join(sorted(re.findall(r"[A-Z]+", s)))


def main(apply: bool = False) -> dict:
    stats = {}
    for f in sorted(glob.glob(os.path.join(DECL, "*.json"))):
        b = os.path.basename(f)
        if b.startswith("_"):
            continue
        d = json.load(open(f, encoding="utf-8"))
        recs = d.get("declaratii", [])
        if not recs:
            continue
        hit = 0
        samples = []
        for r in recs:
            nm = extract_name(r.get("pdf_url", "")) or extract_from_institutie(r.get("institutie", ""))
            if nm:
                hit += 1
                if apply:
                    r["nume"] = nm
                    r["nume_norm"] = norm_name(nm)
                if len(samples) < 3:
                    samples.append((r["pdf_url"].rsplit("/", 1)[-1][:38], nm))
        stats[b] = (hit, len(recs))
        print(f"{b}: {hit}/{len(recs)} ({100*hit//max(len(recs),1)}%) cu nume")
        for fn, nm in samples:
            print(f"     {fn!r} → {nm}")
        if apply:
            json.dump(d, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    tot_hit = sum(h for h, _ in stats.values())
    tot = sum(t for _, t in stats.values())
    print(f"\nTOTAL: {tot_hit}/{tot} declarații cu nume extras ({100*tot_hit//max(tot,1)}%)"
          f"{' — SALVAT' if apply else ' — DRY-RUN (adaugă apply pt. salvare)'}")
    return {"cu_nume": tot_hit, "total": tot}


if __name__ == "__main__":
    main(apply=(len(sys.argv) > 1 and sys.argv[1] == "apply"))
