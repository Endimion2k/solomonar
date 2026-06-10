"""Harvest ARHIVA DNA — comunicate de presă (semnale anticorupție pe persoane/instituții).

Homepage arată doar 5, dar ID-urile `comunicat.xhtml?id=N` sunt DENSE (fiecare id = un comunicat
real). Enumerăm înapoi de la cel mai recent până la un cutoff de an. Extragem data, nr., titlu,
corp + NUMELE inculpaților (secvențe ALL-CAPS) pentru cross-ref cu graful ROMEGA.
Resume-safe: JSONL de id-uri procesate. Output data/v1/audit/dna.json.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time

import requests
import urllib3

urllib3.disable_warnings()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V = os.path.join(ROOT, "data/v1")
JL = os.path.join(ROOT, "pipeline", "_dna_reproc.jsonl")
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"}
BASE = "https://www.dna.ro/comunicat.xhtml?id="

MAX_IDS = int(os.environ.get("ROMEGA_DNA_MAX", "3000"))   # câte id-uri înapoi (data publicării nu e fiabilă per-pagină)

LUNI = {"ianuarie": 1, "februarie": 2, "martie": 3, "aprilie": 4, "mai": 5, "iunie": 6,
        "iulie": 7, "august": 8, "septembrie": 9, "octombrie": 10, "noiembrie": 11, "decembrie": 12}
# cuvinte ALL-CAPS care NU sunt nume de persoană
STOP = {"DNA", "ICCJ", "CCJ", "ANI", "PNA", "DGA", "SRI", "MAI", "IPJ", "ITM", "OUG", "CP", "CPP",
        "UAT", "SRL", "SA", "TVA", "UE", "OLAF", "SC", "RA", "PSD", "PNL", "AUR", "USR", "ROMANIA",
        "BUCURESTI", "NR", "ART", "LEGE", "MO", "CNAS", "APIA", "ANAF", "ROMANIEI", "II", "III", "IV"}


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


def _parse(html: str) -> dict | None:
    if 'class="results"' not in html:
        return None
    txt = re.sub(r"<[^>]+>", " ", html)
    txt = re.sub(r"\s+", " ", txt).strip()
    data = re.search(r"(\d{1,2})\s+(" + "|".join(LUNI) + r")\s+(20\d\d)", txt)
    an = int(data.group(3)) if data else None
    nr = re.search(r"Nr\.?\s*([\w/.\-]+)", txt)
    body = txt[data.end():][:3000] if data else txt[:3000]
    return {"an": an, "data": (data.group(0) if data else None), "nr": (nr.group(1) if nr else None),
            "titlu": body[:160], "nume_extrase": _extract_names(body)}


def main() -> dict:
    hp = requests.get("https://www.dna.ro/comunicate.xhtml", headers=H, verify=False, timeout=30).text
    latest = max(int(x) for x in re.findall(r"comunicat\.xhtml\?id=(\d+)", hp))
    done = set()
    if os.path.exists(JL):
        for line in open(JL, encoding="utf-8"):
            try:
                done.add(json.loads(line)["id"])
            except Exception:
                pass
    print(f"latest id={latest} | deja procesate={len(done)} | max_ids={MAX_IDS}", flush=True)

    out_jl = open(JL, "a", encoding="utf-8")
    n = 0
    cid = latest
    low = latest - MAX_IDS
    while cid > low:
        if cid in done:
            cid -= 1
            continue
        try:
            r = requests.get(BASE + str(cid), headers=H, verify=False, timeout=20)
            rec = _parse(r.text) if r.status_code == 200 else None
        except Exception:
            rec = None
        if rec:
            rec["id"] = cid
            rec["url"] = BASE + str(cid)
            out_jl.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out_jl.flush()
            n += 1
            if n % 200 == 0:
                print(f"   {n} comunicate | id={cid}", flush=True)
        cid -= 1
        time.sleep(0.1)
    out_jl.close()

    recs = {}
    for line in open(JL, encoding="utf-8"):
        try:
            x = json.loads(line)
            recs[x["id"]] = x
        except Exception:
            pass
    data = sorted(recs.values(), key=lambda x: -x["id"])
    os.makedirs(os.path.join(V, "audit"), exist_ok=True)
    json.dump({"sursa": "DNA comunicate (dna.ro)", "total": len(data),
               "nume_distincte": len({nm for r in data for nm in r.get("nume_extrase", [])}),
               "data": data},
              open(os.path.join(V, "audit/dna.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"PUBLICAT dna.json: {len(data)} comunicate | {n} noi runda asta", flush=True)
    return {"comunicate": len(data)}


if __name__ == "__main__":
    main()
