"""Harvest ARHIVA DNA — comunicate de presă (semnale anticorupție pe persoane/instituții).

Homepage arată doar 5, dar ID-urile `comunicat.xhtml?id=N` sunt DENSE (fiecare id = un comunicat
real). Enumerăm înapoi de la cel mai recent până la un cutoff de an. Extragem data, nr., titlu,
corp + NUMELE inculpaților (secvențe ALL-CAPS) pentru cross-ref cu graful SOLOMONAR.
Resume-safe: JSONL de id-uri procesate. Output data/v1/audit/dna.json.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timezone

import requests
import urllib3

urllib3.disable_warnings()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V = os.path.join(ROOT, "data/v1")
JL = os.path.join(ROOT, "pipeline", "_dna_reproc.jsonl")
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"}
BASE = "https://www.dna.ro/comunicat.xhtml?id="

MAX_IDS = int(os.environ.get("SOLOMONAR_DNA_MAX", "3000"))   # câte id-uri înapoi (data publicării nu e fiabilă per-pagină)

LUNI = {"ianuarie": 1, "februarie": 2, "martie": 3, "aprilie": 4, "mai": 5, "iunie": 6,
        "iulie": 7, "august": 8, "septembrie": 9, "octombrie": 10, "noiembrie": 11, "decembrie": 12}
# cuvinte ALL-CAPS care NU sunt nume de persoană
STOP = {"DNA", "ICCJ", "CCJ", "ANI", "PNA", "DGA", "SRI", "MAI", "IPJ", "ITM", "OUG", "CP", "CPP",
        "UAT", "SRL", "SA", "TVA", "UE", "OLAF", "SC", "RA", "PSD", "PNL", "AUR", "USR", "ROMANIA",
        "BUCURESTI", "NR", "ART", "LEGE", "MO", "CNAS", "APIA", "ANAF", "ROMANIEI", "II", "III", "IV",
        "PRESS", "RELEASE", "COMUNICAT", "NO"}


def _extract_names(text: str) -> list[str]:
    """Secvențe de 2-4 cuvinte ALL-CAPS (litere RO) = candidați nume inculpați."""
    names = []
    for m in re.finditer(r"\b([A-ZĂÂÎȘȚ][A-ZĂÂÎȘȚ\-]{1,}(?:\s+[A-ZĂÂÎȘȚ][A-ZĂÂÎȘȚ\-]{1,}){1,3})\b", text):
        toks = m.group(1).split()
        if all(t in STOP for t in toks) or len(toks) < 2:
            continue
        if sum(1 for t in toks if t not in STOP) >= 2:   # cel puțin 2 tokeni non-stop
            names.append(" ".join(toks))
    seen, out = set(), []
    for n in names:
        if n not in seen:
            seen.add(n); out.append(n)
    return out[:8]


AN_MIN = 2002          # PNA (predecesorul DNA) a fost înființat în 2002
# hotărâri judecătorești (sentințe/decizii, anonimizate) publicate tot prin comunicat.xhtml
_COURT = re.compile(r"Cod ECLI|ECLI:RO|Ședința publică|Sedinta publica|SENTIN[ȚTŢ]A PENAL|DECIZIA PENAL|"
                    r"Completul compus|Instanța constituită", re.I)
LUNI_EN = {"january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7,
           "august": 8, "september": 9, "october": 10, "november": 11, "december": 12}
_RE_DATA_RO = re.compile(r"(\d{1,2})\s+(" + "|".join(LUNI) + r")\s+((?:19|20)\d\d)", re.I)
# engleză: „April, 8 th , 2014” / „April 8th, 2014” / „8 April 2014”
_RE_DATA_EN = re.compile(r"(" + "|".join(LUNI_EN) + r")\s*,?\s*(\d{1,2})\s*(?:st|nd|rd|th)?\s*,?\s*((?:19|20)\d\d)"
                         r"|(\d{1,2})\s*(?:st|nd|rd|th)?\s+(" + "|".join(LUNI_EN) + r")\s*,?\s*((?:19|20)\d\d)", re.I)


def _parse(html: str) -> dict | None:
    """Comunicatul din containerul `results` (fără <script>: altfel codul PrimeFaces devenea „titlu”).

    DNA publică și versiuni în ENGLEZĂ („April, 8 th , 2014 … PRESS RELEASE”) — datate în engleză,
    marcate limba='en'. Fără dată recunoscută → None (pagină fără comunicat).
    """
    if 'class="results"' not in html:
        return None
    body = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    seg = body[body.find('class="results"'):][:20000]
    txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", seg)).strip()
    txt = re.sub(r'^class="results"\s*>\s*', "", txt)
    if _COURT.search(txt[:600]):
        return None       # hotărâre judecătorească (anonimizată) publicată pe același endpoint, nu comunicat
    ro, en = _RE_DATA_RO.search(txt), _RE_DATA_EN.search(txt)
    m = min((x for x in (ro, en) if x), key=lambda x: x.start(), default=None)
    if m is None or int(m.group(3) or m.group(6)) < AN_MIN:
        return None       # fără dată de comunicat (o dată istorică / de naștere nu e data publicării)
    if m is ro:
        zi, luna, an, limba = int(m.group(1)), LUNI[m.group(2).lower()], int(m.group(3)), "ro"
    elif m.group(1):
        zi, luna, an, limba = int(m.group(2)), LUNI_EN[m.group(1).lower()], int(m.group(3)), "en"
    else:
        zi, luna, an, limba = int(m.group(4)), LUNI_EN[m.group(5).lower()], int(m.group(6)), "en"
    nr = re.search(r"\b(?:Nr|No)\.?\s*([\w/.\-]+)", txt)
    rest = txt[m.end():][:3000]
    return {"an": an, "data": m.group(0), "data_iso": f"{an:04d}-{luna:02d}-{zi:02d}", "limba": limba,
            "nr": (nr.group(1) if nr else None), "titlu": rest[:160], "nume_extrase": _extract_names(rest)}


def _is_bad(rec: dict) -> bool:
    """Înregistrare nepublicabilă: fără dată, titlu = cod JS (parserul vechi), an < 2002 sau hotărâre."""
    titlu = rec.get("titlu") or ""
    return (not rec.get("data") or titlu.startswith("if(window.PrimeFaces")
            or (rec.get("an") or AN_MIN) < AN_MIN or bool(_COURT.search(titlu)))


def _needs_refetch(rec: dict) -> bool:
    """Se re-descarcă: înregistrările greșite + cele din parserul vechi (fără data_iso / limba).
    O pagină marcată `exclus` (descărcată cu succes, dar nu e comunicat) nu se mai re-descarcă."""
    return not rec.get("exclus") and (_is_bad(rec) or "data_iso" not in rec)


def main() -> dict:
    hp = requests.get("https://www.dna.ro/comunicate.xhtml", headers=H, verify=False, timeout=30).text
    latest = max(int(x) for x in re.findall(r"comunicat\.xhtml\?id=(\d+)", hp))
    done, redo = set(), set()
    if os.path.exists(JL):
        for line in open(JL, encoding="utf-8"):
            try:
                x = json.loads(line)
            except Exception:
                continue
            (redo if _needs_refetch(x) else done).add(x["id"])
    redo -= done          # ultima versiune bună a unui id câștigă
    print(f"latest id={latest} | deja procesate={len(done)} | de re-parsat={len(redo)} | max_ids={MAX_IDS}",
          flush=True)

    out_jl = open(JL, "a", encoding="utf-8")
    n = 0
    low = latest - MAX_IDS
    todo = [c for c in range(latest, low, -1) if c not in done] + sorted(redo - set(range(latest, low, -1)),
                                                                        reverse=True)
    for cid in todo:
        try:
            r = requests.get(BASE + str(cid), headers=H, verify=False, timeout=20)
            ok = r.status_code == 200 and 'class="results"' in r.text
            rec = _parse(r.text) if ok else None
        except Exception:
            ok, rec = False, None
        if ok and rec is None:
            # pagina există, dar nu e comunicat (hotărâre judecătorească / fără dată): exclusă definitiv
            out_jl.write(json.dumps({"id": cid, "exclus": True}) + "\n")
            out_jl.flush()
        if rec:
            rec["id"] = cid
            rec["url"] = BASE + str(cid)
            out_jl.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out_jl.flush()
            n += 1
            if n % 200 == 0:
                print(f"   {n} comunicate | id={cid}", flush=True)
        time.sleep(0.1)
    out_jl.close()

    recs = {}
    for line in open(JL, encoding="utf-8"):
        try:
            x = json.loads(line)
        except Exception:
            continue
        cur = recs.get(x["id"])
        # prioritate: excludere / parser nou (are data_iso) > parser vechi valid > înregistrare greșită
        rank = lambda r: 3 if r.get("exclus") else (  # noqa: E731
            2 if not _needs_refetch(r) else (1 if not _is_bad(r) else 0))
        if cur is None or rank(x) >= rank(cur):
            recs[x["id"]] = x
    n_exclus = sum(1 for v in recs.values() if v.get("exclus"))
    recs = {k: v for k, v in recs.items() if not v.get("exclus")}
    # nu publicăm înregistrări fără dată / cu JS; o re-descărcare eșuată păstrează versiunea veche validă
    recs = {k: v for k, v in recs.items() if not _is_bad(v)}
    data = sorted(recs.values(), key=lambda x: -x["id"])
    os.makedirs(os.path.join(V, "audit"), exist_ok=True)
    json.dump({"sursa": "DNA comunicate (dna.ro)",
               "generated_at": datetime.now(timezone.utc).isoformat(),
               "total": len(data),
               "pe_limba": {lb: sum(1 for r in data if r.get("limba", "ro") == lb) for lb in ("ro", "en")},
               "nota": ("Comunicate de presă DNA; versiunile în engleză sunt marcate limba='en'. Hotărârile "
                        "judecătorești anonimizate publicate prin același endpoint sunt excluse."),
               "hotarari_si_pagini_excluse": n_exclus,
               "nume_distincte": len({nm for r in data for nm in r.get("nume_extrase", [])}),
               "data": data},
              open(os.path.join(V, "audit/dna.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"PUBLICAT dna.json: {len(data)} comunicate | {n} noi runda asta", flush=True)
    return {"comunicate": len(data)}


if __name__ == "__main__":
    main()
