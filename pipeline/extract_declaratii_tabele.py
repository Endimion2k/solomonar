"""Citește din PDF-urile de declarații (cele cu strat de text) data completării și tabelele de participații.

Rezultat: data/build/declaratii_detaliu.jsonl, un rând per PDF:
    {url, strat_text, an_document, participatii: [{sursa, entitate, calitate, nr, valoare}]}

  sursa = "avere_IV2"    plasamente: acțiuni / părți sociale / hârtii de valoare (declarația de avere)
          "interese_1"   asociat sau acționar la societăți (declarația de interese)
          "interese_2"   membru în organele de conducere, administrare și control

Împrumuturile acordate în nume personal (același tabel IV.2) NU se rețin: beneficiarii sunt de regulă
persoane fizice terțe. PDF-urile scanate sunt doar marcate `strat_text: false` — pentru ele e nevoie
de OCR, care nu păstrează structura de tabel.

    python -m pipeline.build_declaratii_detaliu extract                 # toate fișierele publicate
    python -m pipeline.build_declaratii_detaliu extract parlament soe   # doar fișierele care conțin aceste cuvinte

Reluabil: PDF-urile deja prezente în JSONL sunt sărite. `SOLOMONAR_EXTRACT_WORKERS` = procese (implicit 3).
"""

from __future__ import annotations

import glob
import json
import multiprocessing as mp
import os
import re
import sys
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V = os.path.join(ROOT, "data", "v1", "declaratii")
RAW = os.path.join(ROOT, "data", "raw")
OUT = os.path.join(ROOT, "data", "build", "declaratii_detaliu.jsonl")

MIN_TEXT = 200                       # sub atât, PDF-ul e scanat (fără strat de text)
MAX_CELL = 160                       # o celulă mai lungă e un paragraf prins greșit ca tabel
_RE_DATA = re.compile(r"Data\s+complet\w+[\s\S]{0,60}?(\d{1,2})\s?[.\-/]\s?(\d{1,2})\s?[.\-/]\s?(20\d{2})")
_GOL = {"", "-", "–", "—", "nu", "nu e cazul", "nu este cazul", "n/a"}


def _ascii(s) -> str:
    return unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()


def _compact(s) -> str:
    return re.sub(r"[^a-z0-9]", "", _ascii(s))


def _curat(s) -> str:
    return " ".join(str(s or "").split()).strip()


def an_din_text(text: str) -> int | None:
    """Anul din „Data completării … 30-12-2024” (ultima apariție: formularul are și date de exemplu)."""
    gasite = _RE_DATA.findall(text or "")
    return int(gasite[-1][2]) if gasite else None


def clasifica_antet(celule: list[str]) -> str | None:
    """Tipul tabelului după capul de coloane (fără diacritice și spații)."""
    antet = _compact(" ".join(celule))
    if "emitenttitlu" in antet:
        return "avere_IV2"
    if "calitateadetinuta" in antet and ("nrdeparti" in antet or "partisociale" in antet):
        return "interese_1"
    if "calitateadetinuta" in antet and "valoareabeneficiilor" in antet:
        return "interese_2"
    return None


def nume_entitate(text: str) -> str:
    """Doar denumirea: „MAXIMUS SRL - Sectorul 5 Bucuresti STR. X NR. 14, AP. 8” → „MAXIMUS SRL”.

    Formularul cere „denumirea și adresa”; la firmele mici sediul e adesea locuința persoanei, deci
    adresa nu se păstrează.
    """
    text = re.sub(r"^\s*\d\s*\.\s*\d{1,2}\.?\s*", "", _curat(text))      # „1 .1 TERMO…” → „TERMO…”
    nume = re.split(r"\s+[-–—]\s+", text, maxsplit=1)[0].strip(" ,.-")
    return nume if len(nume) >= 3 else text


def rand_participatie(sursa: str, celule: list[str]) -> dict | None:
    """Un rând de tabel → participație, sau None dacă e gol, e antet repetat ori e un împrumut personal."""
    c = [_curat(x) for x in celule if x is not None]
    c = [x for x in c if x != ""] if sursa != "avere_IV2" else c
    if len(c) < 2 or _ascii(c[0]) in _GOL or len(c[0]) > MAX_CELL:
        return None
    if clasifica_antet(c) or _compact(c[0]).startswith(("unitatea", "emitent")):
        return None
    if sursa == "avere_IV2":
        if "imprumut" in _compact(c[1]):
            return None                      # beneficiar persoană fizică: nu se publică
        return {"sursa": sursa, "entitate": nume_entitate(c[0]), "calitate": c[1],
                "nr": c[2] if len(c) > 2 else "", "valoare": c[3] if len(c) > 3 else ""}
    entitate = nume_entitate(c[0])
    if sursa == "interese_1":
        return {"sursa": sursa, "entitate": entitate, "calitate": c[1],
                "nr": c[2] if len(c) > 2 else "", "valoare": c[3] if len(c) > 3 else ""}
    return {"sursa": sursa, "entitate": entitate, "calitate": c[1], "nr": "",
            "valoare": c[2] if len(c) > 2 else ""}


def _celule(page, rand) -> list[str]:
    """Textul celulelor citit pe zona fiecăreia (păstrează spațiile, spre deosebire de extract())."""
    out = []
    for bbox in rand.cells:
        out.append(page.get_textbox(bbox) if bbox else "")
    return out


def extrage_pdf(path: str) -> dict:
    """Detaliile unui PDF local. Nu aruncă excepții: erorile ajung în câmpul `eroare`."""
    import pymupdf

    try:
        doc = pymupdf.open(path)
        texte = [pg.get_text() for pg in doc]
    except Exception as e:  # PDF corupt sau protejat
        return {"strat_text": False, "eroare": f"{type(e).__name__}: {str(e)[:80]}"}
    intreg = "\n".join(texte)
    if len(intreg.strip()) < MIN_TEXT:
        return {"strat_text": False}
    participatii = []
    for page, text in zip(doc, texte):
        t = _compact(text)
        if not ("emitenttitlu" in t or "calitateadetinuta" in t):
            continue                          # recunoașterea de tabele e scumpă: doar pe paginile relevante
        try:
            tabele = page.find_tables().tables
        except Exception:
            continue
        for tb in tabele:
            randuri = [_celule(page, r) for r in tb.rows]
            sursa = None
            for celule in randuri:
                tip = clasifica_antet(celule)
                if tip:
                    sursa = tip
                    continue
                if sursa:
                    p = rand_participatie(sursa, celule)
                    if p:
                        participatii.append(p)
    return {"strat_text": True, "an_document": an_din_text(intreg), "participatii": participatii}


def _lucru(arg: tuple) -> dict:
    url, rel = arg
    return {"url": url, **extrage_pdf(os.path.join(RAW, rel.replace("\\", os.sep)))}


def _manifest() -> dict:
    """url -> cale relativă în data/raw, pentru PDF-uri."""
    out = {}
    with open(os.path.join(RAW, "manifest.jsonl"), encoding="utf-8") as fh:
        for line in fh:
            try:
                m = json.loads(line)
            except ValueError:
                continue
            if str(m.get("path", "")).lower().endswith(".pdf"):
                out[m["url"]] = m["path"]
    return out


def main(filtre: list[str] | None = None) -> dict:
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    facute = set()
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as fh:
            for line in fh:
                try:
                    facute.add(json.loads(line).get("url"))
                except ValueError:
                    pass
    manifest = _manifest()
    de_facut, fara_fisier = [], 0
    for path in sorted(glob.glob(os.path.join(V, "*.json"))):
        nume = os.path.basename(path)
        if nume.split("_")[0] not in ("avere", "interese") or (filtre and not any(f in nume for f in filtre)):
            continue
        with open(path, encoding="utf-8") as fh:
            recs = json.load(fh).get("declaratii") or []
        for r in recs:
            url = r.get("pdf_url")
            if not url or url in facute:
                continue
            facute.add(url)
            if url in manifest:
                de_facut.append((url, manifest[url]))
            else:
                fara_fisier += 1
    print(f"extragere: {len(de_facut)} PDF-uri de citit | fără fișier local: {fara_fisier}", flush=True)
    stat = {"citite": 0, "cu_text": 0, "cu_an": 0, "cu_participatii": 0, "participatii": 0}
    procese = int(os.environ.get("SOLOMONAR_EXTRACT_WORKERS", "3"))
    with open(OUT, "a", encoding="utf-8") as out, mp.Pool(procese) as pool:
        for rez in pool.imap_unordered(_lucru, de_facut, chunksize=4):
            out.write(json.dumps(rez, ensure_ascii=False) + "\n")
            stat["citite"] += 1
            stat["cu_text"] += bool(rez.get("strat_text"))
            stat["cu_an"] += bool(rez.get("an_document"))
            stat["cu_participatii"] += bool(rez.get("participatii"))
            stat["participatii"] += len(rez.get("participatii") or [])
            if stat["citite"] % 500 == 0:
                out.flush()
                print(f"   {stat['citite']}/{len(de_facut)} | {stat}", flush=True)
    print(f"EXTRAS declarații: {stat}", flush=True)
    return stat


if __name__ == "__main__":
    main(sys.argv[1:])
