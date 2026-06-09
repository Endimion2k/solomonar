"""Îmbogățește companiile cu BILANȚURI (MF/ANAF, data.gov.ro) — cifră afaceri, profit, salariați.

Sursa: "Situații financiare {an}" pe data.gov.ro → WEB_BL_BS_SL + WEB_UU (.txt, keyed pe CUI).
Coloane (legendă): CUI;CAEN;i1..i20 → i7=Datorii, i13=Cifra afaceri neta, i16=Profit brut,
i18=Profit net, i19=Pierdere neta, i20=Nr. salariati. Stream filtrat pe CUI-urile SOE (~1GB total).

Enrich companii/_index.json (financials) + publică companii/bilanturi.json.
"""

from __future__ import annotations

import json
import os
import re
import sys

import requests
import urllib3

urllib3.disable_warnings()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V = os.path.join(ROOT, "data/v1")
DATASETS = {  # an → dataset id (Situatii financiare)
    2023: "7861a98f-4d5c-4faa-90d4-8e934ebd1782",
}
COLS = {"datorii": 7, "cifra_afaceri": 13, "profit_brut": 16, "profit_net": 18,
        "pierdere_neta": 19, "nr_salariati": 20}  # i{n}


def _soe_cuis():
    ci = json.load(open(os.path.join(V, "companii/_index.json"), encoding="utf-8"))["data"]
    return {int(c["cui"]): c for c in ci if c.get("cui")}


def _data_urls(an: int):
    r = requests.get(f"https://data.gov.ro/api/3/action/package_show?id={DATASETS[an]}",
                     timeout=30, verify=False)
    urls = []
    for rs in r.json()["result"]["resources"]:
        u = rs.get("url", "")
        nm = (rs.get("name", "") + u).upper()
        if u.lower().endswith(".txt") and ("BL_BS_SL" in nm or "WEB_UU" in nm) and "DESCRIERE" not in nm:
            urls.append(u)
    return urls


def _stream(url, cuis, out):
    n = 0
    with requests.get(url, stream=True, timeout=180, verify=False) as r:
        r.encoding = "utf-8"
        it = r.iter_lines(decode_unicode=True)
        first = next(it, "")
        delim = ";" if first.count(";") >= first.count(",") else ","
        hdr = first.split(delim)
        # poziții: dacă header are 'CUI' → pe nume i{n}; altfel pozițional (CUI,CAEN,i1..i20)
        if hdr and hdr[0].strip().upper() == "CUI":
            idx = {h.strip().lower(): i for i, h in enumerate(hdr)}
            ci = idx.get("cui", 0)
            colidx = {k: idx.get(f"i{n}") for k, n in COLS.items()}
            rows = it  # restul sunt date
        else:
            ci = 0
            colidx = {k: n + 1 for k, n in COLS.items()}  # i{n} la index n+1
            rows = [first] + list(it)  # prima linie e deja date

            def _gen():
                yield first
                yield from it
            rows = _gen()
        for line in rows:
            n += 1
            if n % 500_000 == 0:
                print(f"   {url[-30:]}: {n//1000}k randuri, gasite={len(out)}", flush=True)
            p = line.split(delim)
            try:
                cui = int(p[ci])
            except (ValueError, IndexError):
                continue
            if cui in cuis and cui not in out:
                def num(k):
                    i = colidx.get(k)
                    if i is None or i >= len(p):
                        return None
                    v = re.sub(r"[^\d-]", "", p[i])
                    return int(v) if v and v not in ("-",) else None
                profit = num("profit_net")
                pierdere = num("pierdere_neta")
                out[cui] = {"cifra_afaceri": num("cifra_afaceri"),
                            "profit_net": profit if profit else (-pierdere if pierdere else None),
                            "datorii": num("datorii"), "nr_salariati": num("nr_salariati")}


def main(an: int = 2023) -> dict:
    cuis = _soe_cuis()
    print(f"CUI-uri SOE: {len(cuis)}", flush=True)
    out = {}
    for url in _data_urls(an):
        print(f"stream {url[-40:]}", flush=True)
        _stream(url, set(cuis), out)
    print(f"[bilant] {len(out)}/{len(cuis)} SOE cu date financiare", flush=True)
    # enrich index
    ci = json.load(open(os.path.join(V, "companii/_index.json"), encoding="utf-8"))
    enr = 0
    for c in ci["data"]:
        fin = out.get(int(c["cui"])) if c.get("cui") else None
        if fin and any(v is not None for v in fin.values()):
            c["financials"] = {"an": an, **fin}
            enr += 1
    json.dump(ci, open(os.path.join(V, "companii/_index.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    rows = [{"cui": k, "denumire": cuis[k].get("name", ""), "an": an, **v} for k, v in out.items()]
    json.dump({"an": an, "total": len(rows), "sursa": "MF/ANAF situatii financiare (data.gov.ro)",
               "bilanturi": rows}, open(os.path.join(V, "companii/bilanturi.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"PUBLICAT bilanturi.json: {len(rows)} | index imbogatit: {enr}", flush=True)
    return {"bilanturi": len(rows), "enriched": enr}


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 2023)
