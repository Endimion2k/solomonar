"""Cititor comun pentru resursele SICAP de pe data.gov.ro (CSV în mai multe dialecte + XLS/XLSX).

Folosit de harvest_achizitii_directe și harvest_redflags. Dialectele întâlnite pe data.gov.ro:
  - `^`, `;` sau `|` ca delimitator, fără ghilimele (majoritatea anilor);
  - 2021 T2 → 2022 T4 (achiziții directe): câmpuri între bare verticale separate prin virgulă
    (`|NUMAR|,|DATA|,...,645,645,|SELGROS SRL|`) — un `split` naiv pe cel mai frecvent caracter
    alegea `|` și strica fiecare rând (0-4.000 rânduri în loc de ~500.000 pe trimestru);
  - câmpuri între ghilimele separate prin virgulă;
  - XLS vechi cu datele pe mai multe foi (limită 65.536 rânduri/foaie) și XLSX cu bannere deasupra antetului.
Pentru un trimestru publicat în mai multe formate (ex. 2023 T3 ca CSV și XLS), `groups()` + un prag de
rânduri permit procesarea unei singure variante (altfel datele se numără de două ori).
"""

from __future__ import annotations

import csv
import io
import itertools
import re
import unicodedata

import requests
import urllib3

urllib3.disable_warnings()
csv.field_size_limit(10_000_000)

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"}
MIN_RANDURI_VALIDE = 1000     # sub atât, varianta unui trimestru e considerată defectă → se încearcă alta


def norm(s) -> str:
    """Nume de coloană normalizat: fără diacritice, doar litere/cifre, lowercase."""
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", s)


def pick(cols, cands) -> int | None:
    """Indexul primei coloane din `cands` (în ordinea preferinței) prezente în antet."""
    nc = [norm(c) for c in cols]
    for cand in cands:
        if cand in nc:
            return nc.index(cand)
    return None


def csv_dialect(first_line: str) -> dict:
    """Parametri csv.reader deduși din antet."""
    s = first_line.lstrip("﻿")
    if s.startswith("|") and "|,|" in s:
        return {"delimiter": ",", "quotechar": "|", "quoting": csv.QUOTE_MINIMAL}
    if s.startswith('"') and '","' in s:
        return {"delimiter": ",", "quotechar": '"', "quoting": csv.QUOTE_MINIMAL}
    # fără ghilimele: echivalent cu split pe delimitator (ghilimelele din denumiri rămân text)
    return {"delimiter": max("^;|,\t", key=s.count), "quoting": csv.QUOTE_NONE}


def iter_rows(url: str, fmt: str, timeout_csv: int = 300, timeout_xls: int = 900):
    """Rânduri (list[str]) dintr-o resursă CSV sau XLS/XLSX — toate foile, fără filtrare."""
    if "XLS" in (fmt or "").upper():
        from python_calamine import CalamineWorkbook
        b = requests.get(url, headers=H, verify=False, timeout=timeout_xls).content
        wb = CalamineWorkbook.from_filelike(io.BytesIO(b))
        for sn in wb.sheet_names:
            for row in wb.get_sheet_by_name(sn).to_python(skip_empty_area=True):
                yield [("" if c is None else str(c)) for c in row]
        return
    r = requests.get(url, headers=H, verify=False, timeout=timeout_csv, stream=True)
    r.raise_for_status()
    r.encoding = "utf-8"
    try:
        lines = r.iter_lines(decode_unicode=True)
        first = next(lines)
        yield from csv.reader(itertools.chain([first.lstrip("﻿")], (x for x in lines if x)),
                              **csv_dialect(first))
    finally:
        r.close()


def find_header(rows, required: list[list[str]], max_scan: int = 12):
    """Primul rând (din primele `max_scan`) care conține câte o coloană din fiecare listă `required`."""
    for _ in range(max_scan):
        try:
            row = next(rows)
        except StopIteration:
            return None
        if all(pick(row, cands) is not None for cands in required):
            return row
    return None


def group_key(res: dict) -> tuple:
    """Cheia unui trimestru/perioade: variantele în formate diferite ale aceleiași perioade au aceeași cheie."""
    return (res.get("an"), res.get("tip"), res.get("perioada"), res.get("part"), res.get("subtip"))


def order_variants(resources: list[dict]) -> list[dict]:
    """Ordinea de încercare într-un grup: XLS/XLSX întâi (multi-foaie, complete), apoi CSV."""
    return sorted(resources, key=lambda r: (0 if "XLS" in (r.get("format") or "").upper() else 1))
