"""Red-flags achiziții (OCDS-style) din datele per-linie SICAP — streaming din data.gov.ro.

Spre deosebire de harvest_achizitii_directe (care agregă pe furnizor), aici păstrăm semnalele de risc:
  - SINGLE-BID (din CONTRACTE/licitații): NumarOfertePrimite == 1 la valoare mare (R018 OCDS Cardinal).
  - FRAGMENTARE (din DIRECTE): aceeași autoritate -> același furnizor, multe cumpărări directe repetate
    (semnal de evitare a licitației prin atribuiri directe — open-tender-watch).

Scop implicit: ani recenți (REDFLAGS_YEARS, default 2023-2025) ca să fie tractabil (~GB, nu 13,7 GB).
Checkpoint per resursă. Output: data/v1/redflags.json. Lead-uri de verificat, NU acuzații.
"""

from __future__ import annotations

import io
import json
import os
import re
import time
import unicodedata

import requests
import urllib3

urllib3.disable_warnings()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(ROOT, "pipeline")
V = os.path.join(ROOT, "data/v1")
LOCAL = os.path.join(ROOT, "_local")
CKPT = os.path.join(LOCAL, "_redflags_ckpt.json")     # {done:[urls], single:[...], frag:{pair:{...}}}
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"}

_Y = os.environ.get("REDFLAGS_YEARS", "").strip()
YEARS = (set(int(y) for y in _Y.split(",") if y.strip())
         if _Y and _Y.lower() != "all" else None)  # None = toți anii (resurse CSV)

# praguri
PRAG_SINGLE_BID = 200_000.0     # contracte single-bid peste atât = semnal
PRAG_PROC = 500_000.0           # procedură necompetitivă peste atât = semnal
FRAG_MIN_NR = 10                # ≥ atâtea cumpărări directe pe pereche (autoritate→furnizor) = fragmentare
FRAG_MIN_TOTAL = 100_000.0      # și total minim
MAX_DIRECT = 2_000_000.0        # plafon legal cumpărare directă
MAX_CONTRACT = 50_000_000_000.0  # sanitizare garbage la contracte
PROC_RISC = ("negociere fara", "fara public", "fara invitatie")  # proceduri necompetitive

COL_CUI = ["castigatorcui", "cuicastigator", "cuiofertant", "cuiofertantcastigator"]
COL_VAL = ["valoareron", "valoarecontractron", "valoareatribuitaron", "valoareatribuita",
           "valoareachizitieron", "valoareachizitie"]
COL_NUME = ["castigator", "denumirecastigator", "ofertant", "ofertantcastigator"]
COL_AUT = ["autoritatecontractanta", "denumireac"]
COL_AUTCUI = ["autoritatecontractantacui", "autoritatecontractantacu", "cuiautoritatecontractanta"]
COL_OFERTE = ["numaroferteprimite", "numaroferte", "oferteprimite"]
COL_TITLU = ["titlucontract", "obiectcontract", "denumirecpv", "titlu", "obiect"]
COL_CPV = ["cpvcode", "cpv", "codcpv"]
COL_PROC = ["tipprocedura", "procedura"]
COL_DATA = ["datacontract", "dataanunt", "dataanuntatribuire"]


def _proc_riscanta(s: str) -> bool:
    s = unicodedata.normalize("NFKD", str(s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return any(p in s for p in PROC_RISC)


def _norm(s):
    return re.sub(r"[^a-z]", "", (s or "").lower())


def _pick(cols, cands):
    nc = [_norm(c) for c in cols]
    for cand in cands:
        if cand in nc:
            return nc.index(cand)
    return None


def _num(s, cap):
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
    return v if 0 < v <= cap else 0.0


def _cui(s):
    return re.sub(r"\D", "", str(s or ""))


def _load_ckpt():
    if os.path.exists(CKPT):
        try:
            return json.load(open(CKPT, encoding="utf-8"))
        except Exception:
            pass
    return {"done": [], "single": [], "frag": {}}


def _raw_rows(url, fmt):
    """Yield rânduri (list[str]) dintr-o resursă CSV sau XLS/XLSX."""
    if "XLS" in (fmt or "").upper():
        from python_calamine import CalamineWorkbook
        b = requests.get(url, headers=H, verify=False, timeout=900).content
        wb = CalamineWorkbook.from_filelike(io.BytesIO(b))
        for sn in wb.sheet_names:                         # .xls vechi: date pe 4 foi (limită 65k/foaie)
            for row in wb.get_sheet_by_name(sn).to_python(skip_empty_area=True):
                yield [("" if c is None else str(c)) for c in row]
    else:
        r = requests.get(url, headers=H, verify=False, timeout=300, stream=True)
        r.raise_for_status()
        r.encoding = "utf-8"
        it = r.iter_lines(decode_unicode=True)
        first = next(it)
        delim = max("^|;,", key=lambda d: first.count(d))
        nc = len(first.split(delim))
        yield first.split(delim)
        for line in it:
            if not line:
                continue
            p = line.split(delim)
            if len(p) == nc:
                yield p
        r.close()


def _oferte(s):
    s = re.sub(r"[^\d.]", "", str(s or ""))
    try:
        return int(float(s)) if s else None
    except (ValueError, OverflowError):
        return None


def _process(url, fmt, tip, an, ck):
    rows = _raw_rows(url, fmt)
    # găsește rândul de header (CUI+VAL prezente) în primele 12 rânduri (XLSX poate avea bannere)
    cols = None
    for _ in range(12):
        try:
            row = next(rows)
        except StopIteration:
            return 0
        if _pick(row, COL_CUI) is not None and _pick(row, COL_VAL) is not None:
            cols = row
            break
    if cols is None:
        return 0
    ic, iv, inm, ia = (_pick(cols, COL_CUI), _pick(cols, COL_VAL),
                       _pick(cols, COL_NUME), _pick(cols, COL_AUT))
    iac, iof = _pick(cols, COL_AUTCUI), _pick(cols, COL_OFERTE)
    it_, icpv, idt, iproc = (_pick(cols, COL_TITLU), _pick(cols, COL_CPV),
                             _pick(cols, COL_DATA), _pick(cols, COL_PROC))
    mx = max(x for x in (ic, iv, inm, ia, iac, iof, it_, icpv, idt, iproc) if x is not None)
    is_contract = (tip == "contracte")  # din harta de resurse (nu din prezența ofertelor)
    n = 0
    for p in rows:
        if len(p) <= mx:
            continue
        n += 1
        cui = _cui(p[ic])
        if not cui:
            continue
        if is_contract:
            val = _num(p[iv], MAX_CONTRACT)
            sb = iof is not None and _oferte(p[iof]) == 1 and val >= PRAG_SINGLE_BID
            pr = (not sb) and iproc is not None and val >= PRAG_PROC and _proc_riscanta(p[iproc])
            if sb or pr:
                item = {
                    "an": an, "valoare_ron": round(val),
                    "autoritate": (p[ia][:70] if ia is not None else ""),
                    "castigator": (p[inm][:70] if inm is not None else ""), "cui": cui,
                    "obiect": (p[it_][:90] if it_ is not None and p[it_] else ""),
                    "cpv": (p[icpv][:14] if icpv is not None and p[icpv] else ""),
                    "procedura": (p[iproc][:50] if iproc is not None and p[iproc] else ""),
                    "data": (p[idt][:10] if idt is not None and p[idt] else str(an)),
                }
                (ck["single"] if sb else ck["proc"]).append(item)
        else:
            val = _num(p[iv], MAX_DIRECT)
            if val <= 0:
                continue
            autcui = _cui(p[iac]) if iac is not None else ""
            if not autcui:    # fără CUI-autoritate nu putem atribui perechea (evită over-merge pe furnizor)
                continue
            key = f"{autcui}>{cui}"
            fr = ck["frag"].get(key)
            if fr is None:
                fr = ck["frag"][key] = {
                    "autoritate": (p[ia][:60] if ia is not None else ""),
                    "autoritate_cui": autcui,
                    "castigator": (p[inm][:60] if inm is not None else ""), "cui": cui,
                    "nr": 0, "total": 0.0, "ani": []}
            fr["nr"] += 1
            fr["total"] += val
            if an and an not in fr["ani"]:
                fr["ani"].append(an)
    return n


def _write_output(ck, ani_proc) -> dict:
    """Scrie data/v1/redflags.json din starea curentă (non-mutant — apelabil incremental)."""
    single = sorted(ck["single"], key=lambda x: -x["valoare_ron"])
    proc = sorted(ck["proc"], key=lambda x: -x["valoare_ron"])
    frag = [{"autoritate": f["autoritate"], "autoritate_cui": f["autoritate_cui"],
             "castigator": f["castigator"], "cui": f["cui"], "nr": f["nr"],
             "total": round(f["total"]), "ani_activi": sorted(f.get("ani", []))}
            for f in ck["frag"].values()
            if f["nr"] >= FRAG_MIN_NR and f["total"] >= FRAG_MIN_TOTAL]
    frag.sort(key=lambda x: (x["nr"], x["total"]), reverse=True)
    out = {
        "generat": time.strftime("%Y-%m-%d"),
        "ani": ani_proc,
        "acoperire": "Toate resursele SICAP (CSV + .xls). Single-bid (nr. ofertanți) doar pe anii cu acea "
                     "coloană (format CSV bogat); pe anii .xls recenți se folosește în loc indicatorul "
                     "„procedură necompetitivă”. Fragmentarea acoperă toate cumpărările directe.",
        "disclaimer": "Red-flags = indicatori de RISC din date deschise (metodologie OCDS/open-tender-watch). "
                      "NU sunt dovezi de ilegalitate — sunt lead-uri de verificat. Single-bid, procedurile "
                      "necompetitive și atribuirile directe repetate pot fi perfect legale.",
        "single_bid": {
            "nota": f"Contracte (licitații) cu o singură ofertă primită, peste {int(PRAG_SINGLE_BID):,} lei.",
            "total": len(single), "items": single[:1500]},
        "procedura_necompetitiva": {
            "nota": f"Contracte prin negociere fără publicare / fără invitație, peste {int(PRAG_PROC):,} lei "
                    "(competiție absentă — relevant pe anii fără nr. ofertanți).",
            "total": len(proc), "items": proc[:1500]},
        "fragmentare": {
            "nota": f"Perechi autoritate→furnizor cu ≥{FRAG_MIN_NR} cumpărări directe (posibilă evitare a licitației).",
            "total": len(frag), "items": frag[:1500]},
    }
    json.dump(out, open(os.path.join(V, "redflags.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    return {"single": len(single), "proc": len(proc), "frag": len(frag)}


def main() -> dict:
    res = json.load(open(os.path.join(P, "_achizitii_map.json"), encoding="utf-8"))
    res = res if isinstance(res, list) else [v for k, v in res.items() if k != "_meta"][0]
    todo = [r for r in res if r.get("url") and (YEARS is None or r.get("an") in YEARS)]
    todo.sort(key=lambda x: (x.get("an", 0), str(x.get("perioada", ""))))
    ani_proc = sorted({r.get("an") for r in todo if r.get("an")})

    ck = {"single": [], "proc": [], "frag": {}}    # un singur pas (fără checkpoint greu pe frag)
    print(f"red-flags ani {ani_proc} | resurse: {len(todo)}", flush=True)
    os.makedirs(V, exist_ok=True)

    n_done = 0
    for r in todo:
        url, an, tip, fmt = r["url"], r.get("an"), r.get("tip"), r.get("format")
        t0 = time.time()
        try:
            n = _process(url, fmt, tip, an, ck)
        except Exception as e:
            print(f"   FAIL {an} {tip} {r.get('perioada')}: {type(e).__name__} {str(e)[:40]}", flush=True)
            continue
        if len(ck["frag"]) > 1_000_000:   # bound memorie: scapă de cumpărările one-off (nr==1)
            ck["frag"] = {k: v for k, v in ck["frag"].items() if v["nr"] >= 2}
        print(f"   {an} {tip} {r.get('perioada')}: {n} rânduri, {round(time.time()-t0)}s | "
              f"single={len(ck['single'])} proc={len(ck['proc'])} frag_pairs={len(ck['frag'])}", flush=True)
        n_done += 1
        if n_done % 6 == 0:               # output incremental — rezilient la crash/OOM
            _write_output(ck, ani_proc)

    res = _write_output(ck, ani_proc)
    print(f"PUBLICAT redflags.json: single-bid={res['single']}, procedura={res['proc']}, "
          f"fragmentare={res['frag']}", flush=True)
    return res


if __name__ == "__main__":
    main()
