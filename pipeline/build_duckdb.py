"""Stratul GOLD relațional în DuckDB — realizează arhitectura din docs (medallion gold).

Încarcă toate entitățile + relațiile din JSON-urile gold în DuckDB (engine la build, NU server),
permite interogări relaționale + CTE recursive (expandare de rețea persoană↔companie), și exportă
VIEW-URI ANALITICE noi ca JSON în API static (agregări greu de produs în Python).

DuckDB (data/gold/solomonar.duckdb) e EFEMER (gitignored, regenerabil). Deliverable = build script +
data/v1/analytics/*.json.
"""

from __future__ import annotations

import json
import os
import sys

import duckdb

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V = os.path.join(ROOT, "data/v1")
GOLD = os.path.join(ROOT, "data/gold")
ANALYTICS = os.path.join(V, "analytics")


def _load(p):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return {}


def _bulk(con, table, rows, cols):
    """Insert rapid: scrie ndjson temp (Python) → read_json_auto (DuckDB nativ). executemany e prea lent."""
    if not rows:
        return
    tmp = os.path.join(GOLD, f"_tmp_{table}.jsonl")
    with open(tmp, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(dict(zip(cols, r)), ensure_ascii=False) + "\n")
    con.execute(f"INSERT INTO {table} SELECT {','.join(cols)} FROM read_json_auto('{tmp.replace(chr(92), '/')}')")
    os.remove(tmp)


def _export(con, name, sql):
    rows = con.execute(sql).fetchall()
    cols = [d[0] for d in con.description]
    data = [dict(zip(cols, r)) for r in rows]
    json.dump({"generat_de": "build_duckdb", "total": len(data), "data": data},
              open(os.path.join(ANALYTICS, name), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return len(data)


def main() -> dict:
    os.makedirs(GOLD, exist_ok=True)
    os.makedirs(ANALYTICS, exist_ok=True)
    db = os.path.join(GOLD, "solomonar.duckdb")
    if os.path.exists(db):
        os.remove(db)
    con = duckdb.connect(db)

    # ---------- schema ----------
    con.execute("""
        CREATE TABLE person(romega_id VARCHAR PRIMARY KEY, nume VARCHAR, birth_date VARCHAR,
            incredere VARCHAR, n_declaratii INT, n_companii INT, total_contracte_ron DOUBLE,
            directe_ron DOUBLE, camera VARCHAR, partid VARCHAR, judet VARCHAR);
        CREATE TABLE company(cui BIGINT PRIMARY KEY, nume VARCHAR, sector VARCHAR, tutela VARCHAR,
            judet VARCHAR, bvb BOOLEAN, is_soe BOOLEAN, ca_ron DOUBLE, profit_ron DOUBLE,
            salariati INT, procent_stat DOUBLE, contracte_ron DOUBLE, contracte_nr INT,
            directe_ron DOUBLE, directe_nr INT);
        CREATE TABLE direct_supplier(cui VARCHAR PRIMARY KEY, nume VARCHAR, total_ron DOUBLE,
            nr INT, ani_activi VARCHAR, top_autoritati VARCHAR);
        CREATE TABLE person_company(romega_id VARCHAR, cui BIGINT, rol VARCHAR);
        CREATE TABLE party(cod VARCHAR PRIMARY KEY, subventie_lei DOUBLE, nr_deputati INT,
            nr_senatori INT, nr_rvc INT);
        CREATE TABLE committee_member(parlamentar_id VARCHAR, comisie VARCHAR, rol VARCHAR);
        CREATE TABLE state_holding(simbol VARCHAR, nume VARCHAR, procent_stat DOUBLE, capitalizare VARCHAR);
    """)

    # ---------- load: persoane + edges (person_company = graful bipartit) ----------
    persons, pc = [], []
    for p in _load(os.path.join(V, "graf/persoane_gold.json")).get("persoane", []):
        pl = p.get("parlamentar") or {}
        persons.append((p["romega_id"], p.get("nume_key", ""), pl.get("birth_date"),
                        p.get("incredere", ""), p.get("n_declaratii", 0), p.get("n_companii", 0),
                        p.get("total_contracte_ron") or 0.0, p.get("total_achizitii_directe_ron") or 0.0,
                        pl.get("camera"), str(pl.get("partid") or ""), pl.get("judet")))
        for c in p.get("companii", []):
            try:
                pc.append((p["romega_id"], int(c["cui"]), c.get("rol", "")))
            except (ValueError, TypeError):
                pass
    _bulk(con, "person", persons, ["romega_id","nume","birth_date","incredere","n_declaratii","n_companii","total_contracte_ron","directe_ron","camera","partid","judet"])
    _bulk(con, "person_company", pc, ["romega_id","cui","rol"])
    print(f"   persoane={len(persons)} edges={len(pc)}", flush=True)

    # ---------- load: companii (+ financials + contracte + BVB) ----------
    cf = {int(r["cui"]): r for r in _load(os.path.join(V, "achizitii/contracte_firme.json")).get("firme", [])
          if str(r.get("cui", "")).isdigit()}
    ad = {str(r["cui"]): r for r in _load(os.path.join(V, "companii/achizitii_directe.json")).get("furnizori", [])}
    bvb = {b["nume"].lower(): b for b in _load(os.path.join(V, "companii/actionariat_bvb.json")).get("companii", [])}
    comps, seen = [], set()
    for c in _load(os.path.join(V, "companii/_index.json")).get("data", []):
        try:
            cui = int(c["cui"])
        except (ValueError, TypeError):
            continue
        if cui in seen:
            continue
        seen.add(cui)
        fin = c.get("financials") or {}
        ctr = cf.get(cui, {})
        adr = ad.get(str(cui), {})
        bv = next((b for k, b in bvb.items() if k in (c.get("name", "").lower())), {})
        comps.append((cui, c.get("name", ""), c.get("sector") or "", str(c.get("tutelary_authority") or ""),
                      c.get("county") or "", bool(c.get("bvb_listed")), bool(c.get("is_soe")),
                      fin.get("cifra_afaceri"), fin.get("profit_net"), fin.get("nr_salariati"),
                      bv.get("procent_stat"), ctr.get("total_ron"), ctr.get("nr_contracte"),
                      adr.get("total_ron"), adr.get("nr")))
    _bulk(con, "company", comps, ["cui","nume","sector","tutela","judet","bvb","is_soe","ca_ron","profit_ron","salariati","procent_stat","contracte_ron","contracte_nr","directe_ron","directe_nr"])
    # furnizorii de achiziții directe (toți publicații — top 50k)
    _bulk(con, "direct_supplier",
          [(str(r["cui"]), r.get("nume", ""), r.get("total_ron"), r.get("nr"),
            ",".join(r.get("ani_activi", [])), " | ".join(r.get("top_autoritati", [])))
           for r in ad.values()],
          ["cui","nume","total_ron","nr","ani_activi","top_autoritati"])

    # ---------- load: partide, comisii, state holdings ----------
    con.executemany("INSERT INTO party VALUES (?,?,?,?,?)",
                    [(p["cod"], p.get("total_subventie_lei", 0), p.get("nr_deputati", 0),
                      p.get("nr_senatori", 0), p.get("nr_rapoarte_rvc", 0))
                     for p in _load(os.path.join(V, "partide/partide.json")).get("partide", [])])
    cm = []
    for c in _load(os.path.join(V, "comisii/senat_comisii.json")).get("comisii", []):
        for m in c.get("membri", []):
            cm.append((m.get("parlamentar_id", ""), c.get("nume", ""), m.get("rol", "")))
    con.executemany("INSERT INTO committee_member VALUES (?,?,?)", cm)
    con.executemany("INSERT INTO state_holding VALUES (?,?,?,?)",
                    [(b["simbol"], b["nume"], b.get("procent_stat"), str(b.get("capitalizare_ron")))
                     for b in _load(os.path.join(V, "companii/actionariat_bvb.json")).get("companii", [])])

    con.execute("CREATE INDEX i_pc_cui ON person_company(cui); CREATE INDEX i_pc_rid ON person_company(romega_id);")

    n = {t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
         for t in ("person", "company", "person_company", "party", "committee_member", "state_holding", "direct_supplier")}
    print(f"DuckDB încărcat: {n}", flush=True)

    # ---------- VIEW-URI ANALITICE → JSON ----------
    ex = {}
    ex["sumar_sector.json"] = _export(con, "sumar_sector.json", """
        SELECT sector, count(*) n_companii, round(sum(ca_ron)) cifra_afaceri_totala,
               round(sum(contracte_ron)) contracte_totale, sum(salariati) salariati,
               round(avg(procent_stat),1) procent_stat_mediu
        FROM company WHERE sector<>'' GROUP BY sector ORDER BY contracte_totale DESC NULLS LAST""")
    ex["sumar_judet.json"] = _export(con, "sumar_judet.json", """
        SELECT judet, count(*) n_companii, round(sum(ca_ron)) cifra_afaceri, sum(salariati) salariati
        FROM company WHERE judet<>'' GROUP BY judet ORDER BY n_companii DESC""")
    ex["companii_per_tutela.json"] = _export(con, "companii_per_tutela.json", """
        SELECT tutela, count(*) n_companii, round(sum(contracte_ron)) contracte, sum(salariati) salariati
        FROM company WHERE tutela<>'' GROUP BY tutela ORDER BY n_companii DESC LIMIT 60""")
    ex["participatii_stat.json"] = _export(con, "participatii_stat.json", """
        SELECT nume, simbol, procent_stat, capitalizare FROM state_holding
        WHERE procent_stat>0 ORDER BY procent_stat DESC""")
    # cross-entity: oficiali (declaranți/parlamentari) cu firme cu contracte
    ex["oficiali_contracte.json"] = _export(con, "oficiali_contracte.json", """
        SELECT p.nume, p.incredere, p.camera, p.partid, p.n_declaratii,
               round(p.total_contracte_ron) contracte_firme,
               count(DISTINCT pc.cui) n_firme
        FROM person p JOIN person_company pc ON pc.romega_id=p.romega_id
        JOIN company c ON c.cui=pc.cui AND c.contracte_ron>0
        WHERE p.total_contracte_ron>0 AND (p.n_declaratii>0 OR p.camera IS NOT NULL)
        GROUP BY ALL ORDER BY contracte_firme DESC LIMIT 100""")

    # ---------- CTE RECURSIV: expandare de rețea în jurul Hidroelectrica ----------
    # persoană↔companie e un graf bipartit; expandăm 3 hop-uri din cei mai mari câștigători de contracte
    seed = con.execute("SELECT cui FROM company ORDER BY contracte_ron DESC NULLS LAST LIMIT 1").fetchone()[0]
    net = con.execute(f"""
        WITH RECURSIVE reteam(cui, nivel) AS (
            SELECT {seed}, 0
            UNION
            SELECT pc2.cui, r.nivel+1
            FROM reteam r
            JOIN person_company pc1 ON pc1.cui=r.cui
            JOIN person_company pc2 ON pc2.romega_id=pc1.romega_id
            WHERE r.nivel<2
        )
        SELECT count(DISTINCT cui) FROM reteam""").fetchone()[0]
    print(f"  CTE recursiv (rețea 2-hop din firma top-contracte CUI {seed}): {net} companii conectate", flush=True)

    # exemplu: rețeaua persoanelor în jurul firmelor cu contracte mari (co-administrare)
    ex["retele_coadministrare.json"] = _export(con, "retele_coadministrare.json", """
        WITH multi AS (SELECT cui FROM person_company GROUP BY cui HAVING count(*)>=2)
        SELECT c.nume firma, round(c.contracte_ron) contracte, count(DISTINCT pc.romega_id) n_administratori,
               list(DISTINCT p.nume)[1:6] administratori
        FROM person_company pc JOIN multi ON multi.cui=pc.cui
        JOIN company c ON c.cui=pc.cui JOIN person p ON p.romega_id=pc.romega_id
        WHERE c.contracte_ron>0
        GROUP BY ALL ORDER BY contracte DESC LIMIT 80""")

    con.close()
    json.dump({"nota": "View-uri analitice generate de stratul gold DuckDB (build_duckdb.py). "
               "Engine relational la build; API ramane JSON static.", "tabele": n,
               "exporturi": ex, "cte_recursiv_retea": net},
              open(os.path.join(ANALYTICS, "_index.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"PUBLICAT data/v1/analytics/: {len(ex)} view-uri {ex}", flush=True)
    return {"tabele": n, "exporturi": ex}


if __name__ == "__main__":
    main()
