"""Stratul GOLD v2 — rezoluție canonică INSTITUTION-AWARE (romega_id stabil).

v1 contopea omonimii fără dată naștere pe nume identic (Mocanu DSVSA Brașov + Brăila = 1). v2:
  - PARLAMENTARI (dată naștere + ext id) → romega_core.resolve.PersonRegistry → identitate certă.
  - Mențiuni FĂRĂ dată naștere (declarații/reps/CV) → union-find pe (nume + token de organizație
    DISTINCTIV partajat). Separă același-nume la organizații diferite; PĂSTREAZĂ legăturile
    context-consistente (persoana declară LA și conduce ACEEAȘI companie = follow-the-money tare).
  - Cross-link „confirmat pe context": declară la org X ȘI administrează compania X (fără CNP, dar
    nume + organizație comună = încredere mare).

Persistă registrul parlamentari în data/gold/registry.sqlite. Output persoane_gold.json +
rezolutie_stats.json (cu tier de încredere: high=dată naștere · context=org comună · candidat=nume).
"""

from __future__ import annotations

import glob
import hashlib
import json
import os
import re
import sqlite3
import sys
import unicodedata
from collections import defaultdict
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "packages", "romega_core"))
sys.path.insert(0, ROOT)
from romega_core.resolve import PersonRegistry  # noqa: E402
from romega_core.names import name_key  # noqa: E402

V = os.path.join(ROOT, "data/v1")
GOLD = os.path.join(ROOT, "data/gold")

# token-uri generice de organizație (NU disting o entitate) → ignorate la potrivirea de context
STOP_ORG = {
    "sa", "srl", "ra", "regia", "autonoma", "compania", "nationala", "national", "societatea",
    "directia", "sanitara", "veterinara", "siguranta", "alimentelor", "pentru", "agentia",
    "ministerul", "minister", "inspectoratul", "scolar", "scolara", "judetean", "judeteana",
    "casa", "primaria", "comuna", "orasul", "oras", "municipiul", "municipiu", "sectorul", "sector",
    "consiliul", "consiliu", "judetul", "din", "prin", "anul", "deputat", "senator", "publica",
    "publice", "serviciul", "serviciu", "oficiul", "administratia", "centrul", "institutul",
    "spitalul", "scoala", "liceul", "gradinita", "colegiul", "transport", "energie", "apa",
    "salubritate", "termice", "locala", "local", "dezvoltare", "exploatare", "intretinere",
    # acronime de tip deconcentrat (tipul nu distinge; distinge județul/numele)
    "dsvsa", "dsp", "itm", "isj", "ocpi", "ajofm", "dgaspc", "anpm", "apm", "cas", "cjp", "dgrfp",
    "ajfp", "ansvsa", "cnas", "cnpp",
}


def _norm(s):
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()


def _distinct_tokens(org):
    """Token-uri distinctive ale unei organizații (len≥4, fără generice, fără ani)."""
    return {t for t in re.findall(r"[a-z]{4,}", _norm(org)) if t not in STOP_ORG}


def _date(s):
    try:
        y, m, d = str(s)[:10].split("-")
        return date(int(y), int(m), int(d))
    except Exception:
        return None


def _load(p):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return {}


def _rows(d, *keys):
    for k in keys:
        v = d.get(k)
        if isinstance(v, list):
            return v
        if isinstance(v, dict):
            return list(v.values())
    return []


class UF:
    def __init__(self):
        self.p = {}
    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]; x = self.p[x]
        return x
    def union(self, a, b):
        self.p[self.find(a)] = self.find(b)


def main() -> dict:
    os.makedirs(GOLD, exist_ok=True)

    # ---------- 1. PARLAMENTARI prin registru (dată naștere = identitate certă) ----------
    reg = PersonRegistry()
    mp = {}              # romega_id -> {parlamentar, name_key}
    nk_to_mp = {}        # name_key -> romega_id (pt. legare candidat)
    stats = {"matched": 0, "review": 0, "new": 0}
    for fn, k, cam, pcol, idsys, idcol in [
        ("parlament/deputati.json", "deputati", "deputat", "current_party", "cdep", "cdep_idm"),
        ("parlament/senatori.json", "senatori", "senator", "party", "senat", "senat_guid")]:
        for r in _rows(_load(os.path.join(V, fn)), "data", k):
            nm = r.get("name", "")
            try:
                mr = reg.resolve(nm, birth_date=_date(r.get("birth_date")),
                                 external_ids={idsys: r.get(idcol)} if r.get(idcol) else None)
            except ValueError:
                continue
            stats[mr.status.value] += 1
            mp.setdefault(mr.romega_id, {"name_key": name_key(nm), "parlamentar": None})["parlamentar"] = {
                "camera": cam, "partid": r.get(pcol), "judet": r.get("judet"),
                "legislatura": r.get("legislatura"), "birth_date": r.get("birth_date")}
            if name_key(nm):
                nk_to_mp[name_key(nm)] = mr.romega_id

    # ---------- 2. mențiuni FĂRĂ dată naștere (declarații + reps + CV) ----------
    mentions = []  # {nk, tokens, kind, org, payload}
    cidx = {c["cui"]: c for c in _rows(_load(os.path.join(V, "companii/_index.json")), "data")}
    for c in _rows(_load(os.path.join(V, "companii/reprezentanti.json")), "companii"):
        co = cidx.get(c["cui"], {})
        oname = co.get("name", c.get("denumire", ""))
        for rp in c.get("reprezentanti", []):
            nk = name_key(rp["nume"])
            if nk:
                mentions.append({"nk": nk, "tokens": _distinct_tokens(oname), "kind": "companie", "org": oname,
                                 "payload": {"cui": c["cui"], "nume": oname, "rol": rp["calitate"],
                                             "sector": co.get("sector", ""), "financials": co.get("financials")}})
    for f in glob.glob(os.path.join(V, "declaratii/avere_*.json")) + glob.glob(os.path.join(V, "declaratii/interese_*.json")):
        tip = "avere" if "/avere_" in f.replace("\\", "/") else "interese"
        for d in _load(f).get("declaratii", []):
            nm = d.get("nume")
            if not nm:
                continue
            nk = name_key(nm)
            if nk:
                inst = d.get("institutie", "")
                mentions.append({"nk": nk, "tokens": _distinct_tokens(inst), "kind": "declaratie", "org": inst,
                                 "payload": {"tip": tip, "institutie": inst, "venituri_ron": d.get("venituri_ron")}})
    cv_by_nk = {}
    for fn in ("companii/cv.json", "companii/cv_parlament.json", "companii/cv_senatori.json"):
        for r in _load(os.path.join(V, fn)).get("cv", []):
            if r.get("nume") and (r.get("studii") or r.get("experienta")):
                cv_by_nk.setdefault(name_key(r["nume"]), {"studii": r.get("studii", "")[:600],
                                                           "experienta": r.get("experienta", "")[:600]})

    # ---------- 3. union-find: în cadrul fiecărui name_key, leagă mențiuni cu token org comun ----------
    uf = UF()
    by_nk = defaultdict(list)
    for i, m in enumerate(mentions):
        uf.find(i)
        by_nk[m["nk"]].append(i)
    for nk, idxs in by_nk.items():
        tok_to_idx = defaultdict(list)
        for i in idxs:
            for t in mentions[i]["tokens"]:
                tok_to_idx[t].append(i)
        for t, group in tok_to_idx.items():
            for j in group[1:]:
                uf.union(group[0], j)
        # mențiunile fără niciun token distinctiv (org generic/gol): fiecare rămâne separată

    # componente → persoane canonice
    comp = defaultdict(list)
    for i in range(len(mentions)):
        comp[uf.find(i)].append(i)

    def _cid(idxs):
        m0 = mentions[idxs[0]]
        sig = m0["nk"] + "|" + "|".join(sorted({t for i in idxs for t in mentions[i]["tokens"]})[:3])
        return "g:" + hashlib.sha256(sig.encode()).hexdigest()[:16]

    persoane = {}
    for root, idxs in comp.items():
        nk = mentions[idxs[0]]["nk"]
        rid = nk_to_mp.get(nk) or _cid(idxs)   # dacă numele e al unui parlamentar → leagă la el (candidat)
        p = persoane.setdefault(rid, {"romega_id": rid, "nume_key": nk, "declaratii": [], "companii": [],
                                      "orgs_decl": set(), "orgs_comp": set()})
        for i in idxs:
            m = mentions[i]
            if m["kind"] == "declaratie":
                p["declaratii"].append(m["payload"]); p["orgs_decl"].add(frozenset(m["tokens"]))
            else:
                p["companii"].append(m["payload"]); p["orgs_comp"].add(frozenset(m["tokens"]))

    # parlamentari fără mențiuni → adaugă-i
    for rid, d in mp.items():
        persoane.setdefault(rid, {"romega_id": rid, "nume_key": d["name_key"], "declaratii": [],
                                  "companii": [], "orgs_decl": set(), "orgs_comp": set()})

    # ---------- 4. finalizează + tier de încredere ----------
    out = []
    for rid, p in persoane.items():
        is_mp = rid in mp
        nk = p["nume_key"]
        cv = cv_by_nk.get(nk)
        ncomp = len({c["cui"] for c in p["companii"]})
        # legătură context-confirmată: token org comun între o declarație și o companie
        decl_tok = set().union(*p["orgs_decl"]) if p["orgs_decl"] else set()
        comp_tok = set().union(*p["orgs_comp"]) if p["orgs_comp"] else set()
        ctx_link = bool(decl_tok & comp_tok)
        if is_mp:
            conf = "high"   # identitate ancorată pe dată naștere
        elif ctx_link:
            conf = "context"  # declară LA + conduce ACEEAȘI org (nume+context)
        else:
            conf = "candidat"
        rec = {"romega_id": rid, "nume_key": nk, "incredere": conf, "parlamentar": mp.get(rid, {}).get("parlamentar"),
               "n_declaratii": len(p["declaratii"]), "n_companii": ncomp, "are_cv": cv is not None,
               "declaratii": p["declaratii"][:20], "companii": p["companii"], "cv": cv}
        out.append(rec)
    out.sort(key=lambda x: (-x["n_companii"], -x["n_declaratii"]))

    # persistă registrul parlamentari (romega_id stabil)
    db = os.path.join(GOLD, "registry.sqlite")
    con = sqlite3.connect(db)
    con.executescript("DROP TABLE IF EXISTS person;DROP TABLE IF EXISTS crosswalk;"
                      "CREATE TABLE person(romega_id TEXT PRIMARY KEY,key TEXT,canonical TEXT,birth_date TEXT);"
                      "CREATE TABLE crosswalk(system TEXT,ext_id TEXT,romega_id TEXT);")
    for rec in reg.records():
        con.execute("INSERT OR REPLACE INTO person VALUES(?,?,?,?)",
                    (rec.romega_id, rec.key, rec.canonical_name, rec.birth_date.isoformat() if rec.birth_date else None))
    for s, e, rid in reg.crosswalk_items():
        con.execute("INSERT INTO crosswalk VALUES(?,?,?)", (s, e, rid))
    con.commit(); con.close()

    cross = [r for r in out if r["n_declaratii"] > 0 and r["n_companii"] > 0]
    confirmed = [r for r in cross if r["incredere"] in ("high", "context")]
    parl_co = [r for r in out if r.get("parlamentar") and r["n_companii"] > 0]
    json.dump({"total_persoane": len(out), "parlamentari": len(mp),
               "incredere": {t: sum(1 for r in out if r["incredere"] == t) for t in ("high", "context", "candidat")},
               "rezolutie_parlament": stats, "persoane": out},
              open(os.path.join(V, "graf/persoane_gold.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    json.dump({"nota": "v2 institution-aware. incredere: high=dată naștere (parlamentari), "
               "context=declară LA + conduce ACEEAȘI organizație (nume+org, fără CNP), candidat=doar nume.",
               "cross_links_total": len(cross), "cross_links_confirmate": len(confirmed),
               "confirmate": confirmed[:200], "parlamentari_companii": len(parl_co)},
              open(os.path.join(V, "graf/rezolutie_stats.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"GOLD v2: {len(out)} persoane | parlamentari={len(mp)} | "
          f"incredere high={sum(1 for r in out if r['incredere']=='high')} "
          f"context={sum(1 for r in out if r['incredere']=='context')} candidat={sum(1 for r in out if r['incredere']=='candidat')}")
    print(f"  cross-links: {len(cross)} total | {len(confirmed)} CONFIRMATE (high/context) | parl+comp {len(parl_co)}")
    return {"persoane": len(out), "confirmate": len(confirmed)}


if __name__ == "__main__":
    main()
