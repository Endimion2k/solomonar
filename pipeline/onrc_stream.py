"""Citirea în flux a dump-urilor ONRC de pe data.gov.ro (CSV cu separator „^”), cu verificare de completitudine.

Serverul trimite fișierele fără Content-Length și uneori încheie răspunsul la mijloc fără nicio eroare:
un dump trunchiat arată ca unul complet, doar mai scurt. De aceea se cere `Range: bytes=0-` (răspunsul
aduce atunci `Content-Range: bytes 0-N/TOTAL`), se numără octeții primiți și se oprește totul dacă
lipsesc. Fără mărimea totală nu se poate ști dacă fișierul e întreg, deci nici atunci nu se publică.
"""

from __future__ import annotations

import codecs
import os
import re
from datetime import date
from typing import Iterable, Iterator

import requests
import urllib3

urllib3.disable_warnings()

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120",
           "Accept-Encoding": "identity", "Range": "bytes=0-"}
CHUNK = 1 << 20
BOM = "﻿"


class DescarcareIncompleta(SystemExit):
    """Dump citit parțial: pasul trebuie să eșueze, nu să publice."""


# ---------------- care dump ----------------
# ONRC publică pe data.gov.ro un set NOU (alt id, alte resurse) cam lunar, cu titlul
# „Firme înregistrate la Registrul Comerțului până la data de ZZ.LL.AAAA”. Id-urile fixate în cod
# rămân pe setul vechi, deci căutăm la fiecare rulare cel mai nou set care are toate fișierele cerute.
# ONRC_DATASET=<id set> fixează un set anume (ex. pentru a reface o rulare).
CKAN = "https://data.gov.ro/api/3/action"
_TITLU = re.compile(r"registrul comer\S*\s+p\S*n\S*\s+la\s+data\s+de\s+(\d{1,2})\.(\d{1,2})\.(\d{4})", re.I)


def data_setului(titlu: str) -> date | None:
    """Data din titlul setului ONRC, sau None dacă titlul nu e al unui dump de firme."""
    m = _TITLU.search(titlu or "")
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def _resurse(pachet: dict) -> dict[str, str]:
    """{OD_FIRME: url, ...} — numele resursei fără extensie, cu majuscule."""
    out = {}
    for r in pachet.get("resources") or []:
        nume = re.sub(r"\.csv$", "", (r.get("name") or "").strip(), flags=re.I).upper()
        if nume and r.get("url"):
            out[nume] = r["url"]
    return out


def alege_setul(pachete: list[dict], fisiere: Iterable[str]) -> tuple[dict, date, dict[str, str]]:
    """Cel mai nou set ONRC care are TOATE fișierele cerute → (pachet, data, {fișier: url})."""
    cerute = [f.upper() for f in fisiere]
    candidati = []
    for p in pachete:
        d = data_setului(p.get("title", ""))
        if d and ((p.get("organization") or {}).get("name") in (None, "onrc")):
            candidati.append((d, p))
    for d, p in sorted(candidati, key=lambda x: x[0], reverse=True):
        res = _resurse(p)
        if all(f in res for f in cerute):
            return p, d, {f: res[f] for f in cerute}
    raise SystemExit(f"Niciun set ONRC de pe data.gov.ro nu are toate fișierele {cerute}.")


def _ckan(actiune: str, **params) -> dict:
    r = requests.get(f"{CKAN}/{actiune}", params=params, headers={"User-Agent": HEADERS["User-Agent"]},
                     timeout=60, verify=False)
    r.raise_for_status()
    return r.json()["result"]


def dump_curent(*fisiere: str) -> tuple[str, dict[str, str]]:
    """(„ONRC până la ZZ.LL.AAAA (id set)”, {fișier: url}) pentru cel mai nou set complet."""
    fixat = os.environ.get("ONRC_DATASET", "").strip()
    if fixat:
        pachete = [_ckan("package_show", id=fixat)]
    else:
        pachete = _ckan("package_search", q="Firme inregistrate Registrul Comertului", fq="organization:onrc",
                        rows=100, sort="metadata_modified desc").get("results") or []
    p, d, urls = alege_setul(pachete, fisiere)
    eticheta = f"ONRC până la {d:%d.%m.%Y} (set {p['id']})"
    print(f"[onrc] {eticheta}", flush=True)
    return eticheta, urls


def marime_totala(headers) -> int:
    """Mărimea fișierului din antetele răspunsului (Content-Length, altfel totalul din Content-Range)."""
    m = re.search(r"/(\d+)\s*$", headers.get("Content-Range") or "")
    return int(headers.get("Content-Length") or 0) or (int(m.group(1)) if m else 0)


def linii(bucati: Iterable[bytes], contor: list[int]) -> Iterator[str]:
    """Bucăți de octeți → linii de text; `contor[0]` ține numărul de octeți văzuți."""
    dec = codecs.getincrementaldecoder("utf-8")(errors="replace")
    rest = ""
    for b in bucati:
        contor[0] += len(b)
        parti = (rest + dec.decode(b)).split("\n")
        rest = parti.pop()
        for p in parti:
            yield p.rstrip("\r")
    rest += dec.decode(b"", final=True)
    if rest:
        yield rest.rstrip("\r")


def randuri(url: str, timeout: int = 300) -> Iterator[tuple[list[str], dict[str, int]]]:
    """(câmpurile rândului, {COLOANĂ: poziție}) pentru fiecare rând; ridică DescarcareIncompleta la final."""
    nume = url.rsplit("/", 1)[-1]
    contor = [0]
    with requests.get(url, headers=HEADERS, stream=True, timeout=timeout, verify=False) as r:
        r.raise_for_status()
        asteptat = marime_totala(r.headers)
        it = linii(r.iter_content(chunk_size=CHUNK), contor)
        idx = {c.strip().upper(): i for i, c in enumerate(next(it, "").lstrip(BOM).split("^"))}
        for line in it:
            if line:
                yield line.split("^"), idx
    if not asteptat:
        raise DescarcareIncompleta(f"Nu pot afla mărimea {nume}, deci nu pot ști dacă e complet. Nu public.")
    if contor[0] < asteptat:
        raise DescarcareIncompleta(f"DESCĂRCARE INCOMPLETĂ {nume}: {contor[0]:,} din {asteptat:,} octeți. "
                                   f"Nu public date parțiale.")
