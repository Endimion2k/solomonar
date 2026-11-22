"""Îmbogățește companiile cu BILANȚURI (MF/ANAF, data.gov.ro) — cifră afaceri, profit, salariați.

Sursa: "Situații financiare {an}" pe data.gov.ro → WEB_IR (raportori IFRS: companiile mari, listate),
WEB_BL_BS_SL și WEB_UU (.txt, keyed pe CUI). Toate trei au aceeași legendă: CUI;CAEN;i1..i20 →
i7=Datorii, i13=Cifra afaceri neta, i16=Profit brut, i18=Profit net, i19=Pierdere neta,
i20=Nr. salariati. Stream filtrat pe CUI-urile SOE (~1GB total).

Fără WEB_IR, Hidroelectrica, Romgaz, Nuclearelectrica, Transgaz, Transelectrica etc. lipseau sau
apăreau cu cifre greșite.

Băncile, IFN-urile și asigurătorii au formulare proprii (fișiere mici, altă legendă — vezi SPECIALE).
Se citesc după cele de mai sus și se aduc la aceleași câmpuri, cu `tip_raportare` ca să se știe că
cifrele nu sunt direct comparabile: la bănci și IFN „datorii” = datoriile financiare (i10+i11+i12),
iar numărul de salariați nu se raportează; la asigurători „cifra_afaceri” = veniturile totale (i32).

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
DATASETS = {  # an → dataset id sau nume CKAN (Situatii financiare, MF pe data.gov.ro)
    2025: "situatii_financiare_2025",              # publicat 2026-06
    2024: "situatii_financiare_2024_actualizat",   # versiunea actualizată 2026-06 (înlocuiește _2024)
    2023: "7861a98f-4d5c-4faa-90d4-8e934ebd1782",
    2022: "aa2567a4-e7d7-4e6e-ab19-d08d39f99996",
    2021: "f8353c0e-fee9-4aa3-b26d-be0e96c328a7",
    2020: "e977e5b9-0a1f-46ac-8cb8-f856a011a8ed",
}
COLS = {"datorii": 7, "cifra_afaceri": 13, "profit_brut": 16, "profit_net": 18,
        "pierdere_neta": 19, "nr_salariati": 20}  # i{n}
# tipurile de raportare citite, în ordinea priorității (primul fișier care conține CUI-ul câștigă)
RAPORTARI = ("WEB_IR", "BL_BS_SL", "WEB_UU")
MIN_KEEP_RATIO = 0.5   # sub jumătate din ce e publicat = sursă căzută, nu date noi

# Formulare speciale: fragment din numele resursei (normalizat) → (tip_raportare, nr. coloane așteptat).
# Legenda e verificată pe fișierele 2025; un fișier cu alt număr de coloane are altă legendă și se sare.
BANCA, IFN, ASIGURATOR = "banca", "ifn", "asigurator"
SPECIALE = (("INSTITDECREDIT", BANCA, 25), ("INSTDECREDIT", BANCA, 25), ("IFN", IFN, 25), ("ASIG", ASIGURATOR, 40))


def _soe_cuis():
    ci = json.load(open(os.path.join(V, "companii/_index.json"), encoding="utf-8"))["data"]
    return {int(c["cui"]): c for c in ci if c.get("cui")}


def _published(rel: str) -> dict:
    """Fișierul deja publicat ({} dacă lipsește sau nu se poate citi)."""
    try:
        with open(os.path.join(V, rel), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _data_urls(an: int):
    r = requests.get(f"https://data.gov.ro/api/3/action/package_show?id={DATASETS[an]}",
                     timeout=30, verify=False)
    urls = []
    for rs in r.json()["result"]["resources"]:
        u = rs.get("url", "")
        nm = (rs.get("name", "") + u).upper()
        tip = next((i for i, t in enumerate(RAPORTARI) if t in nm), None)
        if u.lower().endswith(".txt") and tip is not None and "DESCRIERE" not in nm:
            urls.append((tip, u))
    return [u for _, u in sorted(urls)]


def _int(v) -> int | None:
    v = re.sub(r"[^\d-]", "", str(v or ""))
    return int(v) if v and v != "-" else None


def bilant_special(p: list[str], tip: str) -> dict:
    """Un rând (CUI, CAEN, i1…) dintr-un formular special → câmpurile comune de bilanț."""
    i = lambda n: _int(p[n + 1]) if n + 1 < len(p) else None   # noqa: E731
    if tip == ASIGURATOR:
        profit, pierdere = i(36), i(37)
        return {"cifra_afaceri": i(32), "profit_net": profit if profit else (-pierdere if pierdere else None),
                "datorii": i(24), "nr_salariati": i(38), "tip_raportare": tip}
    datorii = [x for x in (i(10), i(11), i(12)) if x is not None]
    return {"cifra_afaceri": i(23), "profit_net": i(22), "datorii": sum(datorii) if datorii else None,
            "nr_salariati": None, "tip_raportare": tip}


def _urls_speciale(an: int) -> list[tuple[str, str, int]]:
    r = requests.get(f"https://data.gov.ro/api/3/action/package_show?id={DATASETS[an]}", timeout=30, verify=False)
    out = []
    for rs in r.json()["result"]["resources"]:
        u = rs.get("url", "")
        nm = re.sub(r"[^A-Z]", "", u.rsplit("/", 1)[-1].upper().replace(".TXT", ""))
        if not u.lower().endswith(".txt"):
            continue
        for frag, tip, ncol in SPECIALE:
            if frag in nm:
                out.append((u, tip, ncol))
                break
    return out


def _speciale(an: int, cuis: set, out: dict) -> int:
    """Completează `out` din formularele speciale ale anului; întoarce câte companii a adăugat."""
    adaugate = 0
    for url, tip, ncol in _urls_speciale(an):
        linii = requests.get(url, timeout=120, verify=False).content.decode("utf-8", "replace").splitlines()
        if not linii:
            continue
        delim = ";" if linii[0].count(";") >= linii[0].count(",") else ","
        if len(linii[0].split(delim)) != ncol:
            print(f"   SAR {url[-36:]}: {len(linii[0].split(delim))} coloane, legenda cunoscută are {ncol}", flush=True)
            continue
        for line in linii:
            p = line.split(delim)
            cui = _int(p[0])
            if cui in cuis and cui not in out:
                out[cui] = bilant_special(p, tip)
                adaugate += 1
    return adaugate


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
        # o conexiune căzută la mijloc se termină fără excepție: verificăm că a venit tot fișierul
        asteptat = int(r.headers.get("Content-Length") or 0)
        primit = r.raw.tell()
        if asteptat and primit < asteptat:
            raise IOError(f"descărcare incompletă: {primit} din {asteptat} octeți ({url[-40:]})")


def main(an: int = 2023) -> dict:
    cuis = _soe_cuis()
    print(f"CUI-uri SOE: {len(cuis)}", flush=True)
    out = {}
    for url in _data_urls(an):
        print(f"stream {url[-40:]}", flush=True)
        _stream(url, set(cuis), out)
    print(f"[bilant] formulare speciale (bănci, IFN, asigurători): +{_speciale(an, set(cuis), out)}", flush=True)
    print(f"[bilant] {len(out)}/{len(cuis)} SOE cu date financiare", flush=True)
    publicate = _published("companii/bilanturi.json")
    if publicate.get("an") == an and len(out) < len(publicate.get("bilanturi") or []) * MIN_KEEP_RATIO:
        raise SystemExit(f"REFUZ să suprascriu bilanturi.json: {len(out)} companii față de "
                         f"{len(publicate['bilanturi'])} publicate pentru {an}. Sursa a răspuns parțial.")
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


def main_trend(ani=(2025, 2024, 2023, 2022, 2021, 2020)) -> dict:
    """Bilanțuri multi-an → trend per SOE (cui → {an: financials})."""
    cuis = _soe_cuis()
    print(f"CUI-uri SOE: {len(cuis)} | ani: {ani}", flush=True)
    trend = {}
    ani_esuati = []
    for an in ani:
        out = {}
        try:
            for url in _data_urls(an):
                print(f"  {an}: stream {url[-36:]}", flush=True)
                _stream(url, set(cuis), out)
            _speciale(an, set(cuis), out)
        except Exception as e:   # sursă instabilă: anul întreg e considerat necitit, nu parțial
            print(f"    EȘEC {an}: {type(e).__name__} {str(e)[:80]}", flush=True)
            ani_esuati.append(an)
            continue
        for cui, fin in out.items():
            if any(v is not None for v in fin.values()):
                trend.setdefault(cui, {})[an] = fin
        print(f"  {an}: {len(out)} SOE", flush=True)
    # un bilanț publicat nu dispare: ce nu a fost regăsit acum (an necitit, fișier schimbat la sursă)
    # rămâne cum era; valorile citite acum au prioritate
    pastrate = 0
    for t in _published("companii/bilanturi_trend.json").get("trend", []):
        if not str(t.get("cui", "")).isdigit():
            continue
        for an, fin in (t.get("ani") or {}).items():
            ani_cui = trend.setdefault(int(t["cui"]), {})
            if int(an) not in ani_cui:
                ani_cui[int(an)] = fin
                pastrate += 1
    if pastrate:
        print(f"  păstrate {pastrate} bilanțuri publicate anterior, neregăsite în această rulare", flush=True)
    rows = [{"cui": k, "denumire": cuis[k].get("name", ""), "ani": v} for k, v in trend.items() if k in cuis]
    json.dump({"ani": list(ani), "total": len(rows), "trend": rows},
              open(os.path.join(V, "companii/bilanturi_trend.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"PUBLICAT bilanturi_trend.json: {len(rows)} SOE cu istoric multi-an", flush=True)
    if ani_esuati:
        raise SystemExit(f"Anii {ani_esuati} nu au putut fi citiți; pentru ei s-au păstrat valorile "
                         f"publicate anterior. Reia pasul când data.gov.ro răspunde.")
    return {"soe": len(rows)}


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "trend":
        main_trend()
    else:
        main(int(sys.argv[1]) if len(sys.argv) > 1 else 2023)
