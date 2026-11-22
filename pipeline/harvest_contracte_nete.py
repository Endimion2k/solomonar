"""Contracte SICAP pe firmă, cu valori NETE: fiecare contract numărat o singură dată.

Exportul „raport contracte publicate” (data.gov.ro) are un rând per (contract × semnatar). La contractele
cu mai mulți semnatari (acorduri-cadru, asocieri) valoarea întreagă apare pe fiecare rând, deci suma
simplă pe firmă umflă cifrele: în T3 2023, 398 din 544 mld. lei „brute” veneau din 19.219 astfel de
contracte. Aici:

  * contractul = (autoritate, anunț de atribuire, lot, număr contract, dată, valoare);
  * la n semnatari, fiecare primește valoare / n — o ESTIMARE: exportul nu spune cota fiecăruia;
  * acordurile-cadru („Cu acord cadru”) sunt plafoane, nu bani contractați: se raportează separat
    în `plafon_acorduri_ron` și NU intră în `total_ron`. Banii vin din contractele subsecvente și
    din cele fără acord-cadru;
  * valorile peste MAX_CONTRACT sunt erori de introducere și se ignoră.

Scrie data/v1/achizitii/_sicap_<an>.json, pe care `build_contracte_firme` le combină:
  furnizori[cui] = {nume, total_ron (net estimat), total_ron_singur (doar contractele cu un semnatar),
                    total_ron_brut (metoda veche), plafon_acorduri_ron, nr_contracte,
                    nr_contracte_comune, nr_acorduri_cadru, top_autoritati}

    python -m pipeline.harvest_contracte_nete              # anii din SICAP_ANI (implicit 2024,2025)
    python -m pipeline.harvest_contracte_nete 2025

Un an se publică doar dacă toate perioadele lui au fost citite.
"""

from __future__ import annotations

import collections
import json
import os
import sys
import time
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from connectors.ani.redaction import cnp_valid  # noqa: E402
from pipeline import sicap_io  # noqa: E402
from pipeline.harvest_redflags import (  # noqa: E402
    COL_AUT, COL_AUTCUI, COL_CUI, COL_NUME, COL_VAL, MAX_CONTRACT, _cui, _num, _pick)

P = os.path.join(ROOT, "pipeline")
OUT_DIR = os.path.join(ROOT, "data/v1/achizitii")
ANI = [int(x) for x in os.environ.get("SICAP_ANI", "2024,2025").split(",") if x.strip()]

COL_ANUNT = ["numaranuntatribuire", "numaranunt"]
COL_LOT = ["numarlot", "lot"]
COL_CONTRACT = ["numarcontract", "nrcontract"]
COL_DATA = ["datacontract"]
COL_INCHEIAT = ["incheiatprin", "incheiarprin"]     # 2024 T1-T3 au antetul scris „Incheiar prin”
TOP_N_AUTORITATI = 3
CADRU, SUBSECVENT, SIMPLU = "cadru", "subsecvent", "simplu"


def tip_incheiere(s: str) -> str:
    """„Cu acord cadru” → plafon; „Cu acord cadru subsecvent” și restul → bani contractați."""
    t = sicap_io.norm(s)
    if "subsecvent" in t:
        return SUBSECVENT
    return CADRU if "acordcadru" in t and not t.startswith("fara") else SIMPLU


def adauga(contracte: dict, cheie: tuple, tip: str, valoare: float, cui: str, nume: str, autoritate: str) -> None:
    """Înregistrează un rând: același contract (aceeași cheie + valoare) strânge semnatarii la un loc."""
    c = contracte.get((cheie, valoare))
    if c is None:
        c = contracte[(cheie, valoare)] = {"tip": tip, "valoare": valoare, "autoritate": autoritate, "semnatari": {}}
    c["semnatari"].setdefault(cui, nume)


def agrega(contracte: dict) -> dict:
    """Contracte → {cui: agregate}. Fiecare contract e împărțit egal între semnatarii lui."""
    out: dict[str, dict] = {}
    aut: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for c in contracte.values():
        n = len(c["semnatari"])
        parte = c["valoare"] / n
        for cui, nume in c["semnatari"].items():
            f = out.setdefault(cui, {"nume": nume, "total_ron": 0.0, "total_ron_singur": 0.0, "total_ron_brut": 0.0,
                                     "plafon_acorduri_ron": 0.0, "nr_contracte": 0, "nr_contracte_comune": 0,
                                     "nr_acorduri_cadru": 0})
            f["total_ron_brut"] += c["valoare"]
            if c["tip"] == CADRU:
                f["plafon_acorduri_ron"] += parte
                f["nr_acorduri_cadru"] += 1
                continue
            f["total_ron"] += parte
            f["nr_contracte"] += 1
            if n == 1:
                f["total_ron_singur"] += parte
            else:
                f["nr_contracte_comune"] += 1
            aut[cui][c["autoritate"]] += parte
    for cui, f in out.items():
        for k in ("total_ron", "total_ron_singur", "total_ron_brut", "plafon_acorduri_ron"):
            f[k] = round(f[k], 2)
        f["top_autoritati"] = [a for a, _ in aut[cui].most_common(TOP_N_AUTORITATI) if a]
    return out


def citeste(url: str, fmt: str, contracte: dict, stat: collections.Counter) -> int:
    """Citește o resursă în `contracte`; întoarce numărul de rânduri valide."""
    rows = sicap_io.iter_rows(url, fmt)
    cols = sicap_io.find_header(rows, [COL_CUI, COL_VAL])
    if cols is None:
        return 0
    ic, iv, inm, ia, iac = (_pick(cols, x) for x in (COL_CUI, COL_VAL, COL_NUME, COL_AUT, COL_AUTCUI))
    ian, il, ict, idt, iin = (sicap_io.pick(cols, x) for x in (COL_ANUNT, COL_LOT, COL_CONTRACT, COL_DATA, COL_INCHEIAT))
    if ian is None or ict is None:
        stat["resurse_fara_cheie_de_contract"] += 1      # fără ele, rândurile nu pot fi grupate pe contract
    mx = max(x for x in (ic, iv, inm, ia, iac, ian, il, ict, idt, iin) if x is not None)
    n = 0
    for nr, p in enumerate(rows):
        if len(p) <= mx:
            continue
        n += 1
        cui = _cui(p[ic])
        if not cui:
            stat["randuri_fara_cui"] += 1
            continue
        if cnp_valid(cui):                    # persoană fizică: CNP-ul nu se publică
            stat["randuri_persoane_fizice"] += 1
            continue
        brut = _num(p[iv], float("inf"))
        valoare = _num(p[iv], MAX_CONTRACT)
        if brut > MAX_CONTRACT:
            stat["valori_peste_plafon"] += 1
        if valoare <= 0:
            stat["randuri_fara_valoare"] += 1
            continue
        g = lambda i: p[i].strip() if i is not None else ""   # noqa: E731
        cheie = ((g(iac) or g(ia), g(ian), g(il), g(ict), g(idt)) if ian is not None and ict is not None
                 else (url, nr))
        adauga(contracte, cheie, tip_incheiere(g(iin)), valoare, str(int(cui)), g(inm)[:120], g(ia)[:120])
    return n


def an_complet(an: int, resurse: list[dict]) -> dict:
    """Citește toate perioadele unui an; ridică SystemExit dacă vreuna lipsește."""
    grupuri: dict = {}
    for r in resurse:
        grupuri.setdefault(sicap_io.group_key(r), []).append(r)
    contracte: dict = {}
    stat: collections.Counter = collections.Counter()
    pierdute = []
    for key in sorted(grupuri, key=lambda k: tuple(str(x) for x in k)):
        citita = False
        for r in sicap_io.order_variants(grupuri[key]):
            proba: dict = {}
            t0 = time.time()
            try:
                n = citeste(r["url"], r.get("format"), proba, stat)
            except Exception as e:
                print(f"   FAIL {an} {r.get('perioada')} {r.get('format')}: {type(e).__name__} {str(e)[:60]}", flush=True)
                continue
            print(f"   {an} {r.get('perioada')} {r.get('format')}: {n} rânduri, {len(proba)} contracte, "
                  f"{round(time.time() - t0)}s", flush=True)
            if n >= sicap_io.MIN_RANDURI_VALIDE:
                for k, c in proba.items():        # aceeași cheie în două perioade = același contract
                    contracte.setdefault(k, c)["semnatari"].update(c["semnatari"])
                stat["randuri"] += n
                citita = True
                break
        if not citita:
            pierdute.append(str(key[2]))
    if pierdute:
        raise SystemExit(f"REFUZ să public _sicap_{an}.json: perioadele {', '.join(pierdute)} nu au putut fi citite. "
                         f"Fișierul publicat rămâne neatins.")
    furnizori = agrega(contracte)
    tipuri = collections.Counter(c["tip"] for c in contracte.values())
    return {
        "an": an, "generat": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sursa": "data.gov.ro — raport contracte publicate (export SICAP)",
        "nota_valori": "total_ron = net estimat: fiecare contract o singură dată, împărțit egal între semnatari; "
                       "acordurile-cadru (plafoane) sunt separat în plafon_acorduri_ron. total_ron_brut = metoda veche.",
        "statistici": {**stat, "contracte": len(contracte), "contracte_pe_tip": dict(tipuri),
                       "contracte_cu_mai_multi_semnatari": sum(1 for c in contracte.values() if len(c["semnatari"]) > 1),
                       "total_ron_net": round(sum(f["total_ron"] for f in furnizori.values())),
                       "total_ron_brut": round(sum(f["total_ron_brut"] for f in furnizori.values())),
                       "plafon_acorduri_ron": round(sum(f["plafon_acorduri_ron"] for f in furnizori.values()))},
        "furnizori": furnizori,
    }


def main(ani: list[int] | None = None) -> dict:
    res = json.load(open(os.path.join(P, "_achizitii_map.json"), encoding="utf-8"))
    res = res if isinstance(res, list) else [v for k, v in res.items() if k != "_meta"][0]
    rezultat, esecuri = {}, []
    for an in ani or ANI:
        resurse = [r for r in res if r.get("url") and r.get("an") == an and r.get("tip") == "contracte"]
        print(f"== contracte nete {an}: {len(resurse)} resurse ==", flush=True)
        try:
            d = an_complet(an, resurse)
        except SystemExit as e:
            print(str(e), flush=True)
            esecuri.append(an)
            continue
        json.dump(d, open(os.path.join(OUT_DIR, f"_sicap_{an}.json"), "w", encoding="utf-8"), ensure_ascii=False)
        s = d["statistici"]
        print(f"PUBLICAT _sicap_{an}.json: {len(d['furnizori'])} firme | net {s['total_ron_net']:,} | "
              f"brut {s['total_ron_brut']:,} | plafoane {s['plafon_acorduri_ron']:,}", flush=True)
        rezultat[an] = len(d["furnizori"])
    if esecuri:
        raise SystemExit(f"Ani nepublicați: {esecuri}")
    return rezultat


if __name__ == "__main__":
    main([int(a) for a in sys.argv[1:]] or None)
