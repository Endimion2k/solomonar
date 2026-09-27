"""Harvest ACHIZIȚII DIRECTE (SICAP 2007→prezent, ~33M rânduri) — streaming + agregare pe CUI furnizor.

Sursa: data.gov.ro ADR, mapate în _achizitii_map.json (86 resurse directe CSV/XLSX). NU stocăm cele
22M de rânduri — STREAMUIM fiecare resursă și AGREGĂM pe CastigatorCUI: {total_ron, nr, nume, ani,
top_autoritati}. Resume-safe per resursă (checkpoint). Output companii/achizitii_directe.json
(toți furnizorii cu total) — multiplică follow-the-money (cine a luat bani de la stat, direct).

CSV: delim '^', col CastigatorCUI/ValoareRON/AutoritateContractanta (auto-detect din header).
XLSX: openpyxl read_only streaming.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timezone

import urllib3

urllib3.disable_warnings()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from connectors.ani.redaction import clean_cui, is_pf_cnp  # noqa: E402
from pipeline import sicap_io  # noqa: E402

P = os.path.join(ROOT, "pipeline")
V = os.path.join(ROOT, "data/v1")
AGG = os.path.join(P, "_achizitii_directe_agg.json")   # CUI -> agregat (checkpoint)
CKPT = os.path.join(P, "_achizitii_directe_done.txt")  # „url<TAB>rânduri” procesate

# nume de coloane acceptate (normalizate cu sicap_io.norm), în ordinea preferinței. Valoarea: cea
# ATRIBUITĂ (nu cea estimată); lista veche nu conținea `VALOARE_ATRIBUITA_RON` → 2022-2025 dădeau 0 rânduri.
COL_CUI = ["castigatorcui", "cuicastigator", "cuiofertant", "cuiofertantcastigator", "cuifurnizor", "cui"]
COL_VAL = ["valoareatribuitaron", "valoareatribuita", "valoareachizitieron", "valoareachizitie",
           "valoareron", "valoarecontractron", "valoarecontract", "valoare"]
COL_NUME = ["castigator", "denumirecastigator", "ofertant", "ofertantcastigator", "denumireofertant", "furnizor"]
COL_AUT = ["autoritatecontractanta", "denumireac", "autoritatecontractant", "denumireautoritatecontractanta",
           "autoritate"]


MAX_VAL = 2_000_000.0   # achizițiile directe au plafon legal (~270k-1M lei); peste 2M = garbage/misaliniat


def _num(s):
    s = re.sub(r"[^\d,.\-]", "", str(s or ""))
    if not s:
        return 0.0
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        v = float(s)
    except (ValueError, OverflowError):
        return 0.0
    return v if 0 < v <= MAX_VAL else 0.0   # sanitizare: skip garbage/outlieri imposibili


def _ident(raw: str, nume: str) -> tuple[str | None, dict]:
    """(cheie de agregare, câmpuri de identitate) pentru un identificator fiscal brut.

    CUI RO valid (2-10 cifre) → cheia = CUI. CNP valid (PFA/II) → NU se publică (Legea 176/2010 +
    GDPR): agregare pe nume, cui=None, pf=True. Alt identificator lung (străin / șiruri lipite) nu e
    PII → păstrat în `cui_nevalid`, fără eticheta de persoană fizică.
    """
    cui = clean_cui(raw)
    if cui:
        return cui, {"cui": cui}
    if is_pf_cnp(raw):
        n = nume.strip().upper()[:80]
        return (f"pf:{n}" if n else None), {"cui": None, "pf": True}
    return raw, {"cui": None, "cui_nevalid": raw}


def _rekey_checkpoint(agg: dict) -> dict:
    """Checkpoint-uri scrise înainte de filtru pot avea CNP-uri drept chei → recheiere + unire."""
    out: dict = {}
    for k, a in agg.items():
        if str(k).startswith("pf:"):
            nk, ident = k, {"cui": None, "pf": True}
        else:
            nk, ident = _ident(re.sub(r"\D", "", str(k)), a.get("nume") or "")
        if nk is None:
            continue
        cur = out.get(nk)
        if cur is None:
            out[nk] = {**a, **ident}
            continue
        cur["total_ron"] += a.get("total_ron", 0.0)
        cur["nr"] += a.get("nr", 0)
        for fld in ("ani", "aut"):
            for kk, vv in (a.get(fld) or {}).items():
                cur[fld][kk] = cur[fld].get(kk, 0) + vv
    return out


def _add(agg, cui, nume, val, an, aut):
    raw = re.sub(r"\D", "", str(cui))
    if not raw or val <= 0:
        return
    key, ident = _ident(raw, nume)
    if key is None:
        return
    a = agg.setdefault(key, {**ident, "nume": nume[:80], "total_ron": 0.0, "nr": 0, "ani": {}, "aut": {}})
    a["total_ron"] += val
    a["nr"] += 1
    if nume and not a["nume"]:
        a["nume"] = nume[:80]
    if an:
        a["ani"][str(an)] = a["ani"].get(str(an), 0) + 1
    if aut:
        a["aut"][aut[:50]] = a["aut"].get(aut[:50], 0) + 1


def _stream(url, fmt, agg, an) -> int:
    """Agregă o resursă (CSV în orice dialect sau XLS/XLSX pe toate foile) prin cititorul comun."""
    rows = sicap_io.iter_rows(url, fmt, timeout_xls=600)
    cols = sicap_io.find_header(rows, [COL_CUI, COL_VAL])
    if cols is None:
        return 0
    ic, iv, inm, ia = (sicap_io.pick(cols, COL_CUI), sicap_io.pick(cols, COL_VAL),
                       sicap_io.pick(cols, COL_NUME), sicap_io.pick(cols, COL_AUT))
    need = max(x for x in (ic, iv, inm, ia) if x is not None)
    n = 0
    for p in rows:
        if len(p) <= need:
            continue
        _add(agg, p[ic], p[inm] if inm is not None else "", _num(p[iv]), an,
             p[ia] if ia is not None else "")
        n += 1
    return n


def main() -> dict:
    res = json.load(open(os.path.join(P, "_achizitii_map.json"), encoding="utf-8"))
    res = res if isinstance(res, list) else res.get("resurse", res.get("data", []))
    directe = [r for r in res if r.get("tip") == "directe" and r.get("url")]
    directe.sort(key=lambda x: (x.get("an", 0), str(x.get("perioada", ""))))

    agg = _rekey_checkpoint(json.load(open(AGG, encoding="utf-8"))) if os.path.exists(AGG) else {}
    done: dict[str, int] = {}          # url -> rânduri (linii vechi fără număr = considerate valide)
    if os.path.exists(CKPT):
        for line in open(CKPT, encoding="utf-8").read().splitlines():
            if line.strip():
                url, _, n = line.partition("\t")
                done[url] = int(n) if n.strip().isdigit() else sicap_io.MIN_RANDURI_VALIDE
    groups: dict[tuple, list] = {}
    for r in directe:
        groups.setdefault(sicap_io.group_key(r), []).append(r)
    print(f"resurse directe: {len(directe)} în {len(groups)} perioade | deja={len(done)} | "
          f"CUI agregate={len(agg)}", flush=True)

    fc = open(CKPT, "a", encoding="utf-8")
    for key in sorted(groups, key=lambda k: (k[0] or 0, str(k[2]), k[3] or 0, str(k[4] or ""))):
        variants = sicap_io.order_variants(groups[key])
        if any(done.get(v["url"], 0) >= sicap_io.MIN_RANDURI_VALIDE for v in variants):
            continue
        for r in variants:                 # XLS întâi; dacă o variantă e defectă, se încearcă următoarea
            url, an, fmt = r["url"], r.get("an"), (r.get("format") or "").upper()
            if url in done:
                continue
            t0 = time.time()
            try:
                n = _stream(url, fmt, agg, an)
            except Exception as e:
                print(f"   FAIL {an} {r.get('perioada')} [{fmt}]: {type(e).__name__} {str(e)[:60]}", flush=True)
                continue
            fc.write(f"{url}\t{n}\n"); fc.flush()
            done[url] = n
            json.dump(agg, open(AGG, "w", encoding="utf-8"))   # checkpoint
            print(f"   {an} {r.get('perioada')} [{fmt}]: {n} rânduri, {round(time.time()-t0)}s | "
                  f"CUI total={len(agg)}", flush=True)
            if n >= sicap_io.MIN_RANDURI_VALIDE:
                break
    fc.close()

    # publică: top + cei legați de graf (companii de stat + firme cu contracte)
    out = sorted(agg.values(), key=lambda x: -x["total_ron"])
    for a in out:
        a["total_ron"] = round(a["total_ron"], 2)
        a["top_autoritati"] = [k for k, _ in sorted(a.pop("aut", {}).items(), key=lambda kv: -kv[1])[:3]]
        a["ani_activi"] = sorted(a.pop("ani", {}).keys())
    os.makedirs(os.path.join(V, "companii"), exist_ok=True)
    ani = sorted({int(y) for a in out for y in a.get("ani_activi") or [] if str(y).isdigit()})
    acoperire = f"{ani[0]}-{ani[-1]}" if ani else ""
    json.dump({"sursa": f"data.gov.ro ADR achiziții directe SICAP {acoperire}", "acoperire": acoperire,
               "generated_at": datetime.now(timezone.utc).isoformat(), "total_furnizori": len(out),
               "total_achizitii": sum(a["nr"] for a in out),
               "valoare_totala_ron": round(sum(a["total_ron"] for a in out), 2),
               "furnizori": out[:50000]},
              open(os.path.join(V, "companii/achizitii_directe.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"PUBLICAT achizitii_directe.json: {len(out)} furnizori, "
          f"{sum(a['nr'] for a in out)} achiziții, {round(sum(a['total_ron'] for a in out)/1e9,1)} mld lei", flush=True)
    return {"furnizori": len(out)}


if __name__ == "__main__":
    main()
