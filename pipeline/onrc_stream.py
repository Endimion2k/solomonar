"""Citirea în flux a dump-urilor ONRC de pe data.gov.ro (CSV cu separator „^”), cu verificare de completitudine.

Serverul trimite fișierele fără Content-Length și uneori încheie răspunsul la mijloc fără nicio eroare:
un dump trunchiat arată ca unul complet, doar mai scurt. De aceea se cere `Range: bytes=0-` (răspunsul
aduce atunci `Content-Range: bytes 0-N/TOTAL`), se numără octeții primiți și se oprește totul dacă
lipsesc. Fără mărimea totală nu se poate ști dacă fișierul e întreg, deci nici atunci nu se publică.
"""

from __future__ import annotations

import codecs
import re
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
