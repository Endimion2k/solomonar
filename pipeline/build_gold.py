"""Stratul GOLD — rezoluție de entități canonică (romega_id stabil) + graf pe ID, nu pe nume.

Refolosește romega_core.resolve.PersonRegistry (crosswalk + blocking + scor nume modulat de dată
naștere + praguri matched/review/new). Persistă registrul în SQLite (data/gold/registry.sqlite,
romega_id stabil între rulări). Față de build_graf (name-matching brut), aici:
  - parlamentarii (cu DATĂ NAȘTERE) sunt rezolvați PRIMII → ancorează registrul fără coliziuni
  - external_ids (cdep:idm, senat:guid) → crosswalk decisiv
  - homonimii fără dată naștere → status 'review' (NU merge silențios) + flag de încredere

Ordinea contează: semnal tare (dată naștere) întâi, apoi mențiuni slabe (declarații/reps/CV).
Output: data/gold/registry.sqlite + data/v1/graf/persoane_gold.json + rezolutie_stats.json.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "packages", "romega_core"))
sys.path.insert(0, ROOT)
from romega_core.resolve import MatchStatus, PersonRegistry  # noqa: E402
from romega_core.names import name_key  # noqa: E402

V = os.path.join(ROOT, "data/v1")
GOLD = os.path.join(ROOT, "data/gold")


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


def main() -> dict:
    os.makedirs(GOLD, exist_ok=True)
    reg = PersonRegistry()
    # seed din SQLite existent (romega_id stabil între rulări)
    db_path = os.path.join(GOLD, "registry.sqlite")
    if os.path.exists(db_path):
        con = sqlite3.connect(db_path)
        try:
            for rid, key, canon, bd in con.execute("SELECT romega_id,key,canonical,birth_date FROM person"):
                xs = [(s, e) for s, e in con.execute("SELECT system,ext_id FROM crosswalk WHERE romega_id=?", (rid,))]
                reg.seed(rid, key, canon, _date(bd), external_ids=xs)
        except sqlite3.OperationalError:
            pass
        con.close()

    persoane = defaultdict(lambda: {"declaratii": [], "companii": [], "cv": None, "parlamentar": None,
                                    "statusuri": set(), "fara_dn_institutii": set()})
    stats = {"matched": 0, "review": 0, "new": 0}
    key_cache: dict[str, str] = {}   # name_key -> romega_id (doar pt. mențiuni fără semnal: dedup + viteză)
    prog = {"n": 0}

    def res(name, bd=None, ext=None):
        """Rezolvă → romega_id. Cache pe name_key pt. mențiunile fără dată naștere/ext (bulk)."""
        prog["n"] += 1
        if prog["n"] % 5000 == 0:
            print(f"   ...{prog['n']} mențiuni rezolvate (registru={len(reg)})", flush=True)
        no_signal = bd is None and not ext
        if no_signal:
            k = name_key(name)
            if k and k in key_cache:
                return type("M", (), {"romega_id": key_cache[k], "status": MatchStatus.MATCHED})()
        try:
            r = reg.resolve(name, birth_date=bd, external_ids=ext)
        except ValueError:
            return None
        stats[r.status.value] += 1
        if no_signal:
            kk = name_key(name)
            if kk:
                key_cache[kk] = r.romega_id
        return r

    # 1. PARLAMENTARI (semnal tare: dată naștere + external id) — ancorează registrul
    for fn, key, cam, pcol, idsys, idcol in [
        ("parlament/deputati.json", "deputati", "deputat", "current_party", "cdep", "cdep_idm"),
        ("parlament/senatori.json", "senatori", "senator", "party", "senat", "senat_guid")]:
        for r in _rows(_load(os.path.join(V, fn)), "data", key):
            mr = res(r.get("name", ""), _date(r.get("birth_date")),
                     {idsys: r.get(idcol)} if r.get(idcol) else None)
            if mr:
                p = persoane[mr.romega_id]
                p["parlamentar"] = {"camera": cam, "partid": r.get(pcol), "judet": r.get("judet"),
                                    "legislatura": r.get("legislatura"), "birth_date": r.get("birth_date")}
                p["statusuri"].add(mr.status.value)

    # 2. REPREZENTANȚI companii (nume + companie, fără dată naștere)
    cidx = {c["cui"]: c for c in _rows(_load(os.path.join(V, "companii/_index.json")), "data")}
    for c in _rows(_load(os.path.join(V, "companii/reprezentanti.json")), "companii"):
        co = cidx.get(c["cui"], {})
        for rp in c.get("reprezentanti", []):
            mr = res(rp["nume"])
            if mr:
                p = persoane[mr.romega_id]
                p["companii"].append({"cui": c["cui"], "nume": co.get("name", c.get("denumire", "")),
                                      "rol": rp["calitate"], "sector": co.get("sector", ""),
                                      "financials": co.get("financials")})
                p["statusuri"].add(mr.status.value)

    # 3. DECLARAȚII (nume + instituție context, fără dată naștere)
    import glob
    for f in glob.glob(os.path.join(V, "declaratii/avere_*.json")) + glob.glob(os.path.join(V, "declaratii/interese_*.json")):
        tip = "avere" if "/avere_" in f.replace("\\", "/") else "interese"
        for d in _load(f).get("declaratii", []):
            nm = d.get("nume")
            if not nm:
                continue
            mr = res(nm)
            if mr:
                p = persoane[mr.romega_id]
                p["declaratii"].append({"tip": tip, "institutie": d.get("institutie", ""),
                                        "venituri_ron": d.get("venituri_ron")})
                p["statusuri"].add(mr.status.value)
                if d.get("institutie"):
                    p["fara_dn_institutii"].add(d["institutie"][:40])

    # 4. CV-uri
    for fn in ("companii/cv.json", "companii/cv_parlament.json", "companii/cv_senatori.json"):
        for r in _load(os.path.join(V, fn)).get("cv", []):
            if r.get("nume") and (r.get("studii") or r.get("experienta")):
                mr = res(r["nume"])
                if mr:
                    persoane[mr.romega_id]["cv"] = {"studii": r.get("studii", "")[:600],
                                                    "experienta": r.get("experienta", "")[:600]}

    # --- persistă registrul în SQLite ---
    con = sqlite3.connect(db_path)
    con.executescript("DROP TABLE IF EXISTS person; DROP TABLE IF EXISTS crosswalk;"
                      "CREATE TABLE person(romega_id TEXT PRIMARY KEY,key TEXT,canonical TEXT,birth_date TEXT,aliases TEXT);"
                      "CREATE TABLE crosswalk(system TEXT,ext_id TEXT,romega_id TEXT);")
    for rec in reg.records():
        con.execute("INSERT OR REPLACE INTO person VALUES(?,?,?,?,?)",
                    (rec.romega_id, rec.key, rec.canonical_name,
                     rec.birth_date.isoformat() if rec.birth_date else None, " | ".join(sorted(rec.aliases))[:500]))
    for system, ext, rid in reg.crosswalk_items():
        con.execute("INSERT INTO crosswalk VALUES(?,?,?)", (system, ext, rid))
    con.commit()

    # --- output canonical persons + încredere ---
    out = []
    for rid, p in persoane.items():
        rec = reg.get(rid)
        bd = rec.birth_date if rec else None
        ncomp = len({c["cui"] for c in p["companii"]})
        # încredere: dată naștere=high; nume unic fără DN=med; nume cu >1 instituții fără DN=low (homonim posibil)
        if bd:
            conf = "high"
        elif len(p["fara_dn_institutii"]) > 1:
            conf = "low"
        else:
            conf = "med"
        out.append({"romega_id": rid, "nume": rec.canonical_name if rec else "",
                    "birth_date": bd.isoformat() if bd else None, "incredere": conf,
                    "n_declaratii": len(p["declaratii"]), "n_companii": ncomp,
                    "are_cv": p["cv"] is not None, "parlamentar": p["parlamentar"],
                    "declaratii": p["declaratii"][:20], "companii": p["companii"], "cv": p["cv"]})
    out.sort(key=lambda x: (-x["n_companii"], -x["n_declaratii"]))

    cross = [r for r in out if r["n_declaratii"] > 0 and r["n_companii"] > 0]
    parl_co = [r for r in out if r.get("parlamentar") and r["n_companii"] > 0]
    os.makedirs(os.path.join(V, "graf"), exist_ok=True)
    json.dump({"total_persoane": len(out), "cu_dată_naștere": sum(1 for r in out if r["birth_date"]),
               "cu_parlamentar": sum(1 for r in out if r["parlamentar"]),
               "rezolutie": stats, "persoane": out},
              open(os.path.join(V, "graf/persoane_gold.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    json.dump({"nota": "Rezolutie canonica (romega_id). matched=legat decisiv, review=homonim posibil, new=nou. "
               "incredere: high=dată naștere, med=nume unic, low=nume cu instituții multiple fără dată naștere.",
               "stats": stats, "cross_links": len(cross), "parlamentari_companii": len(parl_co),
               "parlamentari_companii_lista": parl_co},
              open(os.path.join(V, "graf/rezolutie_stats.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    con.close()
    print(f"GOLD: {len(out)} persoane canonice | rezolutie {stats} | cu_DN={sum(1 for r in out if r['birth_date'])} "
          f"| parlamentari={sum(1 for r in out if r['parlamentar'])}")
    print(f"  cross-links declarant+companie={len(cross)} | parlamentari+companie={len(parl_co)} | SQLite={db_path}")
    return {"persoane": len(out), **stats}


if __name__ == "__main__":
    main()
