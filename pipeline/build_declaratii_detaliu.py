"""Detalii derivate pentru declarațiile publicate: anul și rolurile din declarațiile de interese.

Adnotează pe loc data/v1/declaratii/avere_*.json și interese_*.json:

  an, an_sursa      anul declarației — din data completării citită din document (dacă există în
                    data/build/declaratii_detaliu.jsonl), altfel din numele fișierului PDF, altfel
                    din calea de încărcare. `an_sursa` spune de unde vine, ca să știi cât e de sigur.
  roluri            (doar interese) entitățile declarate, cu secțiunea formularului din care provin:
                    1 = asociat/acționar, 2 = organe de conducere, 3 = asociații profesionale/sindicate,
                    4 = funcții în partid. Se deduce din numerotarea rândului („1.1 …”, „4.2 …”).
  participatii      (doar unde tabelele au putut fi citite din PDF) rândurile de acțiuni / părți sociale.

    python -m pipeline.build_declaratii_detaliu            # adnotează fișierele publicate
    python -m pipeline.build_declaratii_detaliu extract    # citește tabelele din PDF-urile cu strat de text

Pasul e idempotent și nu șterge nimic: recalculează doar câmpurile de mai sus.
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys
from datetime import datetime, timezone
from urllib.parse import unquote, urlsplit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V = os.path.join(ROOT, "data", "v1", "declaratii")
RAW = os.path.join(ROOT, "data", "raw")
DETALIU = os.path.join(ROOT, "data", "build", "declaratii_detaliu.jsonl")

PRIMUL_AN = 2008          # Legea 176/2010 și formularele ei; mai devreme = cifre întâmplătoare din URL
_RE_AN = re.compile(r"(?<!\d)(20[0-3]\d)(?!\d)")
_RE_ROL = re.compile(r"^\s*([1-4])\.(\d{1,2})\.?\s+(.{2,})$")
ROLURI = {1: "asociat sau acționar", 2: "membru în organele de conducere",
          3: "asociație profesională sau sindicat", 4: "funcție în partid"}


def _ani_valizi(text: str, an_curent: int) -> list[int]:
    return [int(a) for a in _RE_AN.findall(text) if PRIMUL_AN <= int(a) <= an_curent]


def an_din_url(url: str, an_curent: int | None = None) -> tuple[int | None, str | None]:
    """Anul declarației dedus din adresa PDF-ului: întâi numele fișierului, apoi calea de încărcare.

    „…/uploads/2023/03/Declaratie-avere-…-25.02.2022.pdf” → (2022, "nume_fisier");
    „…/deputati/2024/avere/153a.pdf” → (2024, "cale"). Anul din cale e anul publicării, de regulă
    același cu al declarației, dar mai puțin sigur.
    """
    an_curent = an_curent or datetime.now(timezone.utc).year
    cale = unquote(urlsplit(url or "").path)
    director, _, fisier = cale.rpartition("/")
    ani = _ani_valizi(fisier, an_curent)
    if ani:
        return max(ani), "nume_fisier"
    ani = _ani_valizi(director, an_curent)
    if ani:
        return ani[-1], "cale"
    return None, None


def roluri_din_entitati(entitati: list | None) -> list[dict]:
    """„1.1 TERMO PLOIESTI SRL - Ploiesti” → {sectiune: 1, rol: "asociat sau acționar", entitate: …}.

    Rândurile fără numerotare (fragmente de adresă, nume rupte) sunt lăsate deoparte: nu se poate
    spune din ce secțiune vin.
    """
    out, vazute = [], set()
    for e in entitati or []:
        m = _RE_ROL.match(str(e))
        if not m:
            continue
        sectiune, entitate = int(m.group(1)), " ".join(m.group(3).split()).strip(" .-")
        cheie = (sectiune, entitate.lower())
        if len(entitate) < 3 or cheie in vazute:
            continue
        vazute.add(cheie)
        out.append({"sectiune": sectiune, "rol": ROLURI[sectiune], "entitate": entitate})
    return out


def _detalii_extrase() -> dict:
    """pdf_url -> rândul din data/build/declaratii_detaliu.jsonl (gol dacă extragerea n-a rulat)."""
    out = {}
    if os.path.exists(DETALIU):
        with open(DETALIU, encoding="utf-8") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                out[r.get("url")] = r
    return out


def adnoteaza(rec: dict, tip: str, extras: dict | None, an_curent: int) -> None:
    """Completează pe loc `an`, `an_sursa`, `roluri` și `participatii` într-o înregistrare."""
    an, sursa = an_din_url(rec.get("pdf_url") or "", an_curent)
    if extras and extras.get("an_document") and PRIMUL_AN <= extras["an_document"] <= an_curent:
        an, sursa = extras["an_document"], "document"
    rec["an"], rec["an_sursa"] = an, sursa
    if tip == "interese":
        rec["roluri"] = roluri_din_entitati(rec.get("entitati"))
    if extras and extras.get("participatii"):
        rec["participatii"] = extras["participatii"]
    else:
        rec.pop("participatii", None)


def main() -> dict:
    an_curent = datetime.now(timezone.utc).year
    extrase = _detalii_extrase()
    stat = {"declaratii": 0, "cu_an": 0, "an_din_document": 0, "cu_roluri": 0, "roluri": 0, "cu_participatii": 0}
    for path in sorted(glob.glob(os.path.join(V, "*.json"))):
        nume = os.path.basename(path)
        tip = nume.split("_")[0]
        if tip not in ("avere", "interese"):
            continue
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
        recs = payload.get("declaratii")
        if not isinstance(recs, list):
            continue
        for rec in recs:
            adnoteaza(rec, tip, extrase.get(rec.get("pdf_url")), an_curent)
            stat["declaratii"] += 1
            stat["cu_an"] += rec["an"] is not None
            stat["an_din_document"] += rec["an_sursa"] == "document"
            stat["cu_roluri"] += bool(rec.get("roluri"))
            stat["roluri"] += len(rec.get("roluri") or [])
            stat["cu_participatii"] += bool(rec.get("participatii"))
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
    print(f"ADNOTAT declarații: {stat}", flush=True)
    return stat


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "extract":
        from pipeline.extract_declaratii_tabele import main as extract_main
        extract_main(sys.argv[2:])
    else:
        main()
