"""Harvest contracte SICAP de la data.gov.ro, agregat pe CUI furnizor (parametrizabil pe an).

Sursa: data.gov.ro -- dataset "raport contracte publicate" (export SICAP). Pentru 2023 e
expus trimestrul III ("t-iii-2023"), CSV cu delimitator '|' si quotechar '"' (campurile pot
contine '|' si '""' escapat -> NU se face split naiv; folosim csv.reader).

STREAMING: fisierul NU se incarca tot in RAM. Liniile sunt citite incremental dintr-un
generator care decodeaza UTF-8 (cu BOM strip) pe masura ce sosesc chunk-urile de retea; daca
conexiunea cade la mijloc (data.gov.ro inchide adesea stream-ul devreme), reluam de la ultimul
octet confirmat via header HTTP Range. Singura structura care creste in memorie e dict-ul de
agregare pe CUI (cardinalitate mica: ~7k CUI pentru un trimestru), nu randurile CSV.

Coloane (antet cu nume; 27 coloane in t-iii-2023):
  cui        = CUI_OF                (CUI furnizor/ofertant; prefixe gen 'RO 8955860')
  nume       = OFERTANT              (denumire furnizor)
  autoritate = DENUMIRE_AC           (autoritatea contractanta)
  suma       = VALOARE_CONTRACT_RON  (RON; format RO -> clean_suma)

ATENTIE la semantica valorilor: fiecare rand = (anunt atribuire x lot x OFERTANT).
VALOARE_CONTRACT_RON se repeta pe FIECARE ofertant participant la lot (nu doar castigatorul).
Deci 'total_ron' per furnizor e BRUT (supraestimeaza). Pastram suma bruta per CUI (cum cere
agregarea), DAR raportam si:
  - total_ron_brut  = suma tuturor randurilor (cu duplicarea pe ofertanti)
  - total_ron_real  = suma deduplicata pe (anunt_atribuire, lot) -> valoarea reala a pietei
Pentru t-iii-2023: brut ~544 mld RON vs real ~134 mld RON.

Agregare pe CUI ofertant (normalizat): pentru fiecare CUI ->
  {nume, total_ron, nr_contracte, top_autoritati (3)}
unde top_autoritati = top 3 autoritati dupa total_ron contractat cu acel furnizor
  [{autoritate, total_ron, nr}].

Output: data/v1/achizitii/_sicap_<an>.json
  {... metadate ..., "furnizori": {cui: {nume, total_ron, nr_contracte, top_autoritati}}}

Rulare:
  python pipeline/harvest_sicap_an.py            # default 2023
  python pipeline/harvest_sicap_an.py --an 2023
  python pipeline/harvest_sicap_an.py --an 2023 --url <csv>
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from typing import Iterator

import requests
import urllib3

urllib3.disable_warnings()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

OUT_DIR = os.path.join(ROOT, "data/v1/achizitii")

# Resurse CSV per an (an -> url). Extinde pe masura ce apar trimestre/ani noi pe data.gov.ro.
RESOURCES: dict[int, str] = {
    2023: (
        "https://data.gov.ro/dataset/07234a4a-8315-4ad5-b761-813a9671a851/"
        "resource/6ccf50f4-2862-4d32-b616-39e05faa0ee6/download/"
        "datagov-raport-contracte-publicate-t-iii-2023.csv"
    ),
}

# Numele exacte ale coloanelor folosite (indexam dupa antet, nu pozitional).
COL_CUI = "CUI_OF"
COL_NUME = "OFERTANT"
COL_AUTORITATE = "DENUMIRE_AC"
COL_SUMA = "VALOARE_CONTRACT_RON"
COL_ANUNT_ATRIB = "NUMAR_ANUNT_ATRIBUIRE"
COL_LOT = "NUMAR_LOT"

DELIMITER = "|"
QUOTECHAR = '"'
TOP_N_AUTORITATI = 3

TIMEOUT = 300
CHUNK = 65536
USER_AGENT = "Mozilla/5.0 (SOLOMONAR-bot; transparenta date publice)"


def _stream_lines(url: str) -> Iterator[str]:
    """Generator de linii (str) dintr-un CSV remote, STREAMING + resilient la drop de conexiune.

    Citeste chunk-uri de octeti; daca stream-ul se inchide inainte de final (data.gov.ro o face
    frecvent), reia via header Range de la ultimul octet primit. BOM strip pe primul chunk.
    Nu tine niciodata tot fisierul in memorie -- doar buffer-ul pana la urmatorul \\n.
    """
    pos = 0  # octeti consumati cu succes (offset pentru Range la reconectare)
    total: int | None = None
    buf = b""
    bom_stripped = False
    attempts = 0
    max_attempts = 8

    while True:
        headers = {"User-Agent": USER_AGENT}
        if pos:
            headers["Range"] = f"bytes={pos}-"
        try:
            resp = requests.get(
                url, verify=False, stream=True, timeout=TIMEOUT, headers=headers
            )
            resp.raise_for_status()
            cr = resp.headers.get("content-range")
            if total is None and cr and "/" in cr:
                try:
                    total = int(cr.rsplit("/", 1)[-1])
                except ValueError:
                    total = None
            for chunk in resp.iter_content(CHUNK):
                if not chunk:
                    continue
                pos += len(chunk)
                if not bom_stripped:
                    if chunk.startswith(b"\xef\xbb\xbf"):
                        chunk = chunk[3:]
                    bom_stripped = True
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    yield line.rstrip(b"\r").decode("utf-8", errors="replace")
            resp.close()
            if total is not None and pos < total:
                attempts += 1
                if attempts > max_attempts:
                    raise RuntimeError(
                        f"stream incomplet dupa {attempts} incercari ({pos}/{total} octeti)"
                    )
                print(
                    f"  ! stream intrerupt la {pos}/{total} octeti -> reiau via Range "
                    f"(incercare {attempts})",
                    flush=True,
                )
                continue
            if buf:
                yield buf.rstrip(b"\r").decode("utf-8", errors="replace")
            return
        except (requests.exceptions.RequestException, RuntimeError) as exc:
            attempts += 1
            if attempts > max_attempts:
                raise
            print(
                f"  ! eroare retea la {pos} octeti ({exc!r}) -> reiau via Range "
                f"(incercare {attempts})",
                flush=True,
            )
            continue


_NUM_RE = re.compile(r"\d")


def clean_suma(raw: str) -> float:
    """Curata o suma in format RO -> float lei (gol/invalid -> 0.0).

    Format RO complet: '.' = separator de mii, ',' = zecimal (ex '1.234.567,89' -> 1234567.89).
    In t-iii-2023 valorile sunt intregi simpli ('22357'), dar tratam robust si:
      - doar ',' -> zecimal RO ('1234,50' -> 1234.50)
      - doar '.' ambiguu -> daca toate grupurile de dupa au exact 3 cifre = separator de mii,
        altfel zecimal (un singur '.').
    """
    if raw is None:
        return 0.0
    s = raw.strip().strip('"').strip()
    if not s or not _NUM_RE.search(s):
        return 0.0
    neg = s.startswith("-")
    s = s.lstrip("+-").strip()
    has_comma = "," in s
    has_dot = "." in s
    if has_comma and has_dot:
        s = s.replace(".", "").replace(",", ".")
    elif has_comma:
        s = s.replace(",", ".")
    elif has_dot:
        parts = s.split(".")
        if len(parts) > 1 and all(len(p) == 3 for p in parts[1:]):
            s = "".join(parts)  # separator de mii
        # altfel: un singur '.' tratat ca zecimal
    try:
        val = float(s)
    except ValueError:
        return 0.0
    return -val if neg else val


_CUI_CLEAN_RE = re.compile(r"[^0-9A-Za-z]")


def normalize_cui(raw: str) -> str | None:
    """Normalizeaza CUI ofertant: scoate prefix 'RO', spatii, separatori; uppercase.

    'RO 8955860' -> '8955860'; 'RO31647962' -> '31647962'; '3572074' -> '3572074'.
    CUI strain (alt prefix de tara, ex 'BG103029862') ramane cu prefixul ca sa nu se confunde
    cu un CUI RO. Daca dupa curatare nu ramane nimic -> None.
    """
    if raw is None:
        return None
    s = _CUI_CLEAN_RE.sub("", str(raw)).upper()
    if not s:
        return None
    if s.startswith("RO"):
        rest = s[2:]
        if rest.isdigit() or rest == "":  # 'RO' + cifre = CUI romanesc; altfel alt prefix
            s = rest
    if s.isdigit():
        s = s.lstrip("0") or "0"  # normalizeaza zerourile de inceput
    return s or None


def harvest_year(an: int, url: str | None = None) -> dict:
    url = url or RESOURCES.get(an)
    if not url:
        raise SystemExit(
            f"Niciun URL configurat pentru anul {an}. Ani disponibili: {sorted(RESOURCES)}. "
            f"Foloseste --url <csv>."
        )

    print(f"== SICAP an {an} ==", flush=True)
    print(f"GET (stream) {url}", flush=True)

    # Agregare pe CUI. Per CUI: nume, total_ron (brut), nr_contracte + Counters pe autoritate.
    agg: dict[str, dict] = {}
    proc_val: dict[tuple, float] = {}  # (anunt_atribuire, lot) -> valoare, pt. total real

    nr_contracte = 0  # randuri de date (linii contract/ofertant), exclus antet
    nr_cu_cui = 0
    nr_fara_cui = 0
    nr_cu_valoare = 0
    nr_malformate = 0
    total_brut = 0.0

    reader = csv.reader(_stream_lines(url), delimiter=DELIMITER, quotechar=QUOTECHAR)
    header = next(reader, None)
    if header is None:
        raise RuntimeError("CSV gol")
    header = [h.lstrip("﻿").strip() for h in header]
    idx = {c: i for i, c in enumerate(header)}
    for col in (COL_CUI, COL_NUME, COL_AUTORITATE, COL_SUMA, COL_ANUNT_ATRIB, COL_LOT):
        if col not in idx:
            raise RuntimeError(f"Coloana '{col}' lipseste din antet: {header}")
    ncols = len(header)
    i_cui = idx[COL_CUI]
    i_nume = idx[COL_NUME]
    i_aut = idx[COL_AUTORITATE]
    i_suma = idx[COL_SUMA]
    i_aa = idx[COL_ANUNT_ATRIB]
    i_lot = idx[COL_LOT]
    print(
        f"  header: {ncols} coloane (CUI={i_cui}, OFERTANT={i_nume}, AC={i_aut}, VAL={i_suma})",
        flush=True,
    )

    for row in reader:
        if not row:
            continue
        nr_contracte += 1
        if len(row) != ncols:
            nr_malformate += 1
            continue
        cui = normalize_cui(row[i_cui])
        if not cui:
            nr_fara_cui += 1
            continue
        nr_cu_cui += 1
        suma = clean_suma(row[i_suma])
        if suma:
            nr_cu_valoare += 1
            total_brut += suma
        # total real: o singura valoare per (anunt_atribuire, lot)
        pk = (row[i_aa].strip(), row[i_lot].strip())
        if pk != ("", ""):
            proc_val[pk] = suma
        nume = (row[i_nume] or "").strip().strip('"').strip()
        autoritate = (row[i_aut] or "").strip().strip('"').strip()

        entry = agg.get(cui)
        if entry is None:
            entry = {
                "nume": nume,
                "total_ron": 0.0,
                "nr_contracte": 0,
                "_aut_total": Counter(),
                "_aut_nr": Counter(),
            }
            agg[cui] = entry
        if nume:  # pastram ultima denumire nevida (varianta cu diacritice/SRL e mai recenta)
            entry["nume"] = nume
        entry["total_ron"] += suma
        entry["nr_contracte"] += 1
        if autoritate:
            entry["_aut_total"][autoritate] += suma
            entry["_aut_nr"][autoritate] += 1

        if nr_contracte % 50000 == 0:
            print(
                f"  ... {nr_contracte:,} randuri | {len(agg):,} CUI | "
                f"{total_brut/1e9:.3f} mld RON (brut)",
                flush=True,
            )

    # Finalizare: top 3 autoritati dupa total_ron + rotunjire.
    furnizori: dict[str, dict] = {}
    for cui, entry in agg.items():
        aut_total: Counter = entry["_aut_total"]
        aut_nr: Counter = entry["_aut_nr"]
        top = [
            {"autoritate": name, "total_ron": round(val, 2), "nr": int(aut_nr[name])}
            for name, val in aut_total.most_common(TOP_N_AUTORITATI)
        ]
        furnizori[cui] = {
            "nume": entry["nume"],
            "total_ron": round(entry["total_ron"], 2),
            "nr_contracte": int(entry["nr_contracte"]),
            "top_autoritati": top,
        }

    total_real = sum(proc_val.values())
    nota = (
        "Fiecare rand = (anunt atribuire x lot x OFERTANT); VALOARE_CONTRACT_RON se repeta "
        "pe fiecare ofertant participant la lot. total_ron per furnizor e BRUT (supraestimeaza: "
        "toti ofertantii, nu doar castigatorul). total_ron_brut = suma tuturor randurilor; "
        "total_ron_real = suma deduplicata pe (anunt_atribuire, lot)."
    )
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "an": an,
        "sursa": "data.gov.ro -- raport contracte publicate (SICAP export), trimestrul III 2023",
        "source_url": url,
        "metoda": "stream CSV (iter_content + csv.reader, delimitator '|') -> agregare per CUI ofertant",
        "nota_valori": nota,
        "nr_contracte": nr_contracte,
        "nr_contracte_cu_cui": nr_cu_cui,
        "nr_contracte_cu_valoare": nr_cu_valoare,
        "nr_randuri_fara_cui": nr_fara_cui,
        "nr_randuri_malformate": nr_malformate,
        "nr_proceduri_lot_distincte": len(proc_val),
        "nr_cui": len(furnizori),
        "total_ron_brut": round(total_brut, 2),
        "total_ron_real": round(total_real, 2),
        "furnizori": furnizori,
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    out_file = os.path.join(OUT_DIR, f"_sicap_{an}.json")
    with open(out_file, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)

    print(
        f"\nSCRIS {out_file}\n"
        f"  randuri date       : {nr_contracte:,}\n"
        f"  cu CUI valid       : {nr_cu_cui:,}\n"
        f"  fara CUI           : {nr_fara_cui:,}\n"
        f"  malformate         : {nr_malformate:,}\n"
        f"  cu valoare         : {nr_cu_valoare:,}\n"
        f"  proceduri-lot uniq : {len(proc_val):,}\n"
        f"  CUI distincte      : {len(furnizori):,}\n"
        f"  total BRUT (toti ofertantii): {total_brut:,.0f} RON ({total_brut/1e9:.2f} mld)\n"
        f"  total REAL (dedup proc-lot) : {total_real:,.0f} RON ({total_real/1e9:.2f} mld)",
        flush=True,
    )

    payload["_out_path"] = out_file
    return payload


def main() -> dict:
    ap = argparse.ArgumentParser(description="Harvest contracte SICAP per an.")
    ap.add_argument("--an", type=int, default=2023, help="Anul de procesat (default 2023)")
    ap.add_argument("--url", default=None, help="URL CSV explicit (suprascrie maparea pe an)")
    args = ap.parse_args()

    payload = harvest_year(args.an, args.url)

    top3 = sorted(
        payload["furnizori"].items(),
        key=lambda kv: kv[1]["total_ron"],
        reverse=True,
    )[:3]
    print("\n=== TOP 3 FURNIZORI (dupa total_ron brut) ===", flush=True)
    for cui, info in top3:
        print(
            f"  CUI {cui}: {info['nume']} -- {info['total_ron']:,.0f} RON "
            f"({info['nr_contracte']} contracte)",
            flush=True,
        )

    return {
        "an": payload["an"],
        "out": payload["_out_path"],
        "nr_contracte": payload["nr_contracte"],
        "nr_cui": payload["nr_cui"],
        "total_ron_brut": payload["total_ron_brut"],
        "total_ron_real": payload["total_ron_real"],
    }


if __name__ == "__main__":
    main()
