"""Server MCP ROMEGA — interogare conversațională a aparatului de stat român.

Expune datele gold ROMEGA (DuckDB read-only) pentru orice client MCP
(Claude Desktop / Cursor / Continue). Întrebări naturale despre persoane,
companii de stat, follow-the-money, contracte publice, partide, comisii.

Sursa primară: ``data/gold/romega.duckdb`` (tabele curate, dedublicate).
Enrichment (declarații, CV, comisii nominale): ``data/v1/graf/*.json``.

ETICĂ — citește înainte de a trage concluzii din răspunsuri:
  * Legăturile persoană↔firmă sunt pe NUME (fără CNP). Un "candidat" poate
    fi un OMONIM, NU persoana publică. NU e o acuzație.
  * Doar conflictele AUTO-DECLARATE (incredere='high'/'context', cu declarații
    de avere/interese care confirmă firma) sunt defensabile.
  * Comunicatele DNA, dacă apar, sunt TRIMITERI ÎN JUDECATĂ, nu condamnări
    (prezumția de nevinovăție).
  * CNP-ul este redactat din toate sursele; nu există în acest dataset.
Fiecare răspuns include un câmp ``_provenance`` cu sursa și avertismentele.

Rulare:   romega-mcp-core        (sau: python -m romega_core.mcp_server)
Config Claude Desktop:
  {"mcpServers": {"romega": {"command": "romega-mcp-core"}}}
"""

from __future__ import annotations

import json
import os
import unicodedata
from functools import lru_cache
from typing import Any

import duckdb
from mcp.server.fastmcp import FastMCP

# ----------------------------------------------------------------------------
# Localizare date (override prin env ROMEGA_DUCKDB / ROMEGA_DATA)
# ----------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.normpath(os.path.join(_HERE, "..", "..", ".."))

DUCKDB_PATH = os.environ.get("ROMEGA_DUCKDB") or os.path.join(
    _ROOT, "data", "gold", "romega.duckdb")
DATA_V1 = os.environ.get("ROMEGA_DATA") or os.path.join(_ROOT, "data", "v1")

# Avertismente standard refolosite în provenance.
WARN_OMONIM = (
    "Legăturile persoană↔firmă sunt pe NUME (fără CNP). Un 'candidat' poate fi "
    "OMONIM — NU este o acuzație și nu confirmă identitatea persoanei publice.")
WARN_DNA = (
    "Eventualele referințe DNA sunt TRIMITERI ÎN JUDECATĂ, nu condamnări "
    "(prezumția de nevinovăție).")
SOURCE = "ROMEGA gold (DuckDB) — date publice agregate: ANI, CDEP/Senat, "\
    "ONRC, SICAP, BVB, AEP."

mcp = FastMCP("romega", instructions=(
    "ROMEGA — transparența aparatului de stat român. Date publice agregate din "
    "DuckDB gold: declarații de avere/interese (ANI), parlamentari și comisii "
    "(CDEP/Senat), companii de stat (bilanț, % stat, contracte SICAP), partide "
    "(subvenții AEP), participații BVB. IMPORTANT pentru interpretare: legăturile "
    "persoană↔firmă sunt pe NUME (fără CNP), deci un 'candidat' poate fi un "
    "OMONIM — nu o acuzație. Doar conflictele AUTO-DECLARATE sunt defensabile. "
    "Comunicatele DNA = trimiteri în judecată, NU condamnări. CNP redactat."))


# ----------------------------------------------------------------------------
# Conexiune DuckDB (read-only, cache-uită) + helper de interogare
# ----------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _con() -> duckdb.DuckDBPyConnection:
    """Conexiune DuckDB read-only, deschisă o singură dată și refolosită."""
    if not os.path.exists(DUCKDB_PATH):
        raise FileNotFoundError(
            f"Baza DuckDB ROMEGA lipsește: {DUCKDB_PATH}. "
            "Setează ROMEGA_DUCKDB sau rulează pipeline-ul gold.")
    return duckdb.connect(DUCKDB_PATH, read_only=True)


def _rows(sql: str, params: list[Any] | None = None) -> list[dict]:
    """Rulează SQL și întoarce list[dict] (nume coloane → valori)."""
    cur = _con().execute(sql, params or [])
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _norm(s: str | None) -> str:
    """Normalizare pentru căutare: fără diacritice, lowercase, trim."""
    return (unicodedata.normalize("NFKD", s or "")
            .encode("ascii", "ignore").decode().lower().strip())


@lru_cache(maxsize=8)
def _json(rel: str) -> Any:
    """Încarcă (și cache-uiește) un JSON din data/v1."""
    p = os.path.join(DATA_V1, rel.replace("/", os.sep))
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=1)
def _persoane_by_id() -> dict[str, dict]:
    """Index romega_id → fișa JSON bogată (declarații, CV, comisii)."""
    data = _json("graf/persoane_gold.json")
    persoane = data.get("persoane", []) if isinstance(data, dict) else data
    return {p.get("romega_id"): p for p in persoane if p.get("romega_id")}


def _prov(extra: dict | None = None, omonim: bool = False) -> dict:
    """Construiește blocul _provenance atașat fiecărui răspuns."""
    p = {"sursa": SOURCE, "baza": "data/gold/romega.duckdb (read_only)"}
    if omonim:
        p["avertisment"] = WARN_OMONIM
    if extra:
        p.update(extra)
    return p


# ----------------------------------------------------------------------------
# TOOLS
# ----------------------------------------------------------------------------
@mcp.tool()
def search_persoana(nume: str, limit: int = 15) -> dict:
    """Caută persoane în registrul ROMEGA după nume (parțial, fără diacritice).

    Întoarce pentru fiecare: romega_id, nume, nivel de încredere al identității
    ('high' = parlamentar/declarant cert, 'context', 'candidat' = posibil
    omonim), nr. declarații/companii, total contracte de stat ale firmelor
    legate, camera + partid (dacă e parlamentar), județ.

    ETICĂ: 'candidat' = match pe nume fără confirmare — posibil OMONIM, NU o
    acuzație. Folosește get_persoana(romega_id) pentru fișa completă.
    """
    q = _norm(nume)
    rows = _rows(
        """
        SELECT romega_id, nume, incredere, n_declaratii, n_companii,
               total_contracte_ron, camera, partid, judet
        FROM person
        WHERE strip_accents(lower(nume)) LIKE '%' || ? || '%'
        ORDER BY (incredere='high') DESC, total_contracte_ron DESC NULLS LAST,
                 n_declaratii DESC
        LIMIT ?
        """,
        [q, max(1, min(limit, 100))],
    )
    for r in rows:
        r["nume"] = (r.get("nume") or "").title()
    return {"query": nume, "n": len(rows), "rezultate": rows,
            "_provenance": _prov(omonim=True)}


@mcp.tool()
def get_persoana(romega_id: str) -> dict:
    """Fișa completă a unei persoane (din romega_id, obținut cu search_persoana).

    Combină DuckDB (rol parlamentar, companii cu rol, contracte) cu JSON-ul gold
    (declarații de avere/interese, CV, comisii parlamentare nominale).

    Câmpuri: identitate + incredere, parlamentar{camera,partid,judet,comisii},
    companii[]{cui,nume,rol}, total_contracte_ron, declaratii[], are_cv.

    ETICĂ: dacă incredere='candidat', identitatea NU e confirmată (posibil omonim).
    Contractele aparțin FIRMELOR legate de persoană, nu sunt plăți către persoană.
    """
    base = _rows(
        """
        SELECT romega_id, nume, birth_date, incredere, n_declaratii, n_companii,
               total_contracte_ron, camera, partid, judet
        FROM person WHERE romega_id = ?
        """,
        [romega_id],
    )
    if not base:
        return {"eroare": f"romega_id inexistent: {romega_id}",
                "_provenance": _prov()}
    rec = base[0]
    rec["nume"] = (rec.get("nume") or "").title()

    rec["companii"] = _rows(
        """
        SELECT pc.cui, c.nume, pc.rol, c.sector, c.is_soe,
               c.contracte_ron, c.contracte_nr
        FROM person_company pc
        LEFT JOIN company c ON c.cui = pc.cui
        WHERE pc.romega_id = ?
        ORDER BY c.contracte_ron DESC NULLS LAST
        """,
        [romega_id],
    )

    # Enrichment din JSON gold (declarații, CV, comisii nominale)
    rich = _persoane_by_id().get(romega_id, {})
    parl = rich.get("parlamentar") or {}
    rec["parlamentar"] = {
        "camera": rec.get("camera") or parl.get("camera"),
        "partid": rec.get("partid") or parl.get("partid"),
        "judet": rec.get("judet") or parl.get("judet"),
        "legislatura": parl.get("legislatura"),
        "comisii": parl.get("comisii", []),
    } if (rec.get("camera") or parl) else None
    rec["declaratii"] = rich.get("declaratii", [])
    rec["are_cv"] = rich.get("are_cv", False)
    rec["firme_contracte_autodeclarate"] = rich.get(
        "firme_contracte_autodeclarate", [])

    omonim = rec.get("incredere") == "candidat"
    return {**rec, "_provenance": _prov(omonim=omonim)}


@mcp.tool()
def search_companie_stat(nume: str = "", sector: str = "", cui: int = 0,
                         judet: str = "", doar_bvb: bool = False,
                         limit: int = 20) -> dict:
    """Caută companii cu participație/relevanță de stat după nume/sector/CUI/județ.

    Filtre opționale combinabile. Întoarce: cui, nume, sector, autoritatea
    tutelară, județ, listare BVB, is_soe (întreprindere de stat), cifra de
    afaceri, profit net, salariați, % deținut de stat, valoarea și nr.
    contractelor de stat (SICAP).
    """
    where, params = [], []
    if cui:
        where.append("cui = ?"); params.append(int(cui))
    if nume:
        where.append("strip_accents(lower(nume)) LIKE '%' || ? || '%'")
        params.append(_norm(nume))
    if sector:
        where.append("strip_accents(lower(sector)) LIKE '%' || ? || '%'")
        params.append(_norm(sector))
    if judet:
        where.append("strip_accents(lower(judet)) LIKE '%' || ? || '%'")
        params.append(_norm(judet))
    if doar_bvb:
        where.append("bvb = TRUE")
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    rows = _rows(
        f"""
        SELECT cui, nume, sector, tutela, judet, bvb, is_soe, ca_ron,
               profit_ron, salariati, procent_stat, contracte_ron, contracte_nr
        FROM company {clause}
        ORDER BY contracte_ron DESC NULLS LAST, ca_ron DESC NULLS LAST
        LIMIT ?
        """,
        params + [max(1, min(limit, 200))],
    )
    return {"n": len(rows), "rezultate": rows, "_provenance": _prov()}


@mcp.tool()
def top_firme_contracte(n: int = 20, sector: str = "") -> dict:
    """Top firme după valoarea contractelor de stat câștigate (SICAP), opțional
    filtrate pe sector.

    Întoarce: nume, cui, sector, tutelă, is_soe, valoarea totală a contractelor,
    nr. contracte, cifra de afaceri. Util pentru a vedea cei mai mari
    beneficiari de bani publici.
    """
    where, params = ["contracte_ron IS NOT NULL", "contracte_ron > 0"], []
    if sector:
        where.append("strip_accents(lower(sector)) LIKE '%' || ? || '%'")
        params.append(_norm(sector))
    rows = _rows(
        f"""
        SELECT nume, cui, sector, tutela, is_soe, contracte_ron, contracte_nr,
               ca_ron
        FROM company WHERE {' AND '.join(where)}
        ORDER BY contracte_ron DESC
        LIMIT ?
        """,
        params + [max(1, min(n, 200))],
    )
    return {"n": len(rows), "sector": sector or "(toate)", "top": rows,
            "_provenance": _prov()}


@mcp.tool()
def follow_the_money(doar_confirmate: bool = True) -> dict:
    """Persoane (declaranți/parlamentari) ale căror FIRME au câștigat contracte
    de stat — potențiale conflicte de interese.

    doar_confirmate=True (recomandat): doar conflictele AUTO-DECLARATE — persoana
    și-a declarat ea însăși firma în declarația de avere/interese, iar firma are
    contracte de stat. Acestea sunt DEFENSABILE jurnalistic.

    doar_confirmate=False: adaugă 'leaduri_neverificate' — match pe NUME între
    o persoană publică și un reprezentant de firmă, FĂRĂ confirmare (fără CNP).
    AVERTISMENT: majoritatea sunt OMONIMI (ex. un reprezentant ENGIE/Groupama cu
    același nume ca un parlamentar). NU sunt acuzații. NU le publica fără
    verificare independentă.
    """
    fm = _json("graf/follow_the_money.json")

    def _slim(p: dict) -> dict:
        parl = p.get("parlamentar") or {}
        return {
            "romega_id": p.get("romega_id"),
            "nume": (p.get("nume_key") or "").title(),
            "incredere": p.get("incredere"),
            "este_parlamentar": bool(parl),
            "camera": parl.get("camera") if parl else None,
            "partid": parl.get("partid") if parl else None,
            "n_firme_cu_contracte": p.get("n_firme_cu_contracte"),
            "total_contracte_ron": p.get("total_contracte_ron"),
            "firme_contracte_autodeclarate": p.get(
                "firme_contracte_autodeclarate", []),
        }

    confirmate = [_slim(p) for p in fm.get("confirmate", [])]
    res: dict = {
        "nota_sursa": fm.get("nota"),
        "n_confirmate": len(confirmate),
        "confirmate_autodeclarate": confirmate,
    }
    prov_extra = {"definitie_confirmat":
                  "firmă cu contracte de stat declarată chiar de persoană în "
                  "declarația de avere/interese (auto-declarat)."}
    if not doar_confirmate:
        leaduri = [_slim(p) for p in fm.get("leaduri_neverificate", [])]
        res["n_leaduri_neverificate"] = len(leaduri)
        res["leaduri_neverificate"] = leaduri
        res["AVERTISMENT"] = WARN_OMONIM
    return {**res, "_provenance": _prov(prov_extra,
                                        omonim=not doar_confirmate)}


@mcp.tool()
def persoane_cu_firme_contracte(min_lei: float = 0) -> dict:
    """Persoane ale căror firme au contracte de stat cumulate ≥ min_lei (RON).

    Agregă pe persoană valoarea contractelor firmelor pe care le conduce/
    reprezintă (din person_company × company). Întoarce: romega_id, nume,
    incredere, dacă e parlamentar, total contracte, nr. firme cu contracte.

    ETICĂ: pentru incredere='candidat' legătura e pe nume (posibil omonim).
    Contractele aparțin FIRMELOR, nu sunt venituri ale persoanei.
    """
    rows = _rows(
        """
        SELECT p.romega_id, p.nume, p.incredere, p.camera, p.partid,
               SUM(c.contracte_ron) AS total_contracte_ron,
               COUNT(*) FILTER (WHERE c.contracte_ron > 0) AS n_firme_contracte
        FROM person_company pc
        JOIN person p  ON p.romega_id = pc.romega_id
        JOIN company c ON c.cui = pc.cui
        WHERE c.contracte_ron IS NOT NULL AND c.contracte_ron > 0
        GROUP BY p.romega_id, p.nume, p.incredere, p.camera, p.partid
        HAVING SUM(c.contracte_ron) >= ?
        ORDER BY total_contracte_ron DESC
        LIMIT 200
        """,
        [float(min_lei)],
    )
    for r in rows:
        r["nume"] = (r.get("nume") or "").title()
        r["este_parlamentar"] = bool(r.get("camera"))
    return {"min_lei": min_lei, "n": len(rows), "persoane": rows,
            "_provenance": _prov(omonim=True)}


@mcp.tool()
def party_subventii(cod: str = "") -> dict:
    """Subvențiile de stat pentru partide (AEP) + nr. parlamentari + rapoarte RVC.

    cod opțional (ex. 'PSD', 'PNL', 'USR', 'AUR') filtrează un singur partid;
    gol = toate, ordonate descrescător după subvenție. Întoarce: cod,
    subvenție totală (lei), nr. deputați/senatori, nr. rapoarte RVC.
    """
    where, params = [], []
    if cod:
        where.append("upper(cod) = upper(?)"); params.append(cod.strip())
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    rows = _rows(
        f"""
        SELECT cod, subventie_lei, nr_deputati, nr_senatori, nr_rvc
        FROM party {clause}
        ORDER BY subventie_lei DESC NULLS LAST
        """,
        params,
    )
    return {"n": len(rows), "partide": rows, "_provenance": _prov()}


@mcp.tool()
def companii_cu_participatie_stat() -> dict:
    """Companiile listate la BVB cu participație de stat (state_holding).

    Întoarce: simbol bursier, nume, % deținut de stat, capitalizare de piață.
    Acestea sunt 'bijuteriile coroanei' — Hidroelectrica, Romgaz, Nuclearelectrica
    etc., unde statul e acționar majoritar/semnificativ.
    """
    rows = _rows(
        """
        SELECT simbol, nume, procent_stat, capitalizare
        FROM state_holding
        ORDER BY procent_stat DESC NULLS LAST
        """
    )
    return {"n": len(rows), "companii": rows, "_provenance": _prov()}


@mcp.tool()
def comisie_membri(nume: str) -> dict:
    """Componența unei comisii parlamentare după nume parțial (ex. 'buget',
    'juridic', 'sanatate', 'aparare').

    Întoarce membrii nominali (din graful gold — parlamentari cu romega_id,
    camera, partid) plus distribuția rolurilor din tabelul oficial CDEP/Senat
    (Președinte/Vicepreședinte/Secretar/Membru), când există.

    Notă: legătura rol-nominal nu e 1:1 disponibilă (sursa CDEP cheamă membrii
    prin GUID intern), deci 'roluri_oficiale' e agregat, iar 'membri' vine din
    apartenențele declarate ale parlamentarilor.
    """
    q = _norm(nume)
    # 1) Membri nominali din JSON (parlamentar.comisii)
    membri: list[dict] = []
    comisii_gasite: set[str] = set()
    for p in _persoane_by_id().values():
        parl = p.get("parlamentar") or {}
        for com in parl.get("comisii", []):
            if q in _norm(com):
                comisii_gasite.add(com)
                membri.append({
                    "romega_id": p.get("romega_id"),
                    "nume": (p.get("nume_key") or "").title(),
                    "camera": parl.get("camera"),
                    "partid": parl.get("partid"),
                    "comisie": com,
                })
    # 2) Distribuția rolurilor din tabelul oficial committee_member
    roluri = _rows(
        """
        SELECT comisie, rol, COUNT(*) AS n
        FROM committee_member
        WHERE strip_accents(lower(comisie)) LIKE '%' || ? || '%'
        GROUP BY comisie, rol
        ORDER BY comisie, n DESC
        """,
        [q],
    )
    for r in roluri:
        comisii_gasite.add(r["comisie"])
    if not membri and not roluri:
        return {"eroare": f"nicio comisie care conține '{nume}'",
                "_provenance": _prov()}
    return {
        "query": nume,
        "comisii_gasite": sorted(comisii_gasite),
        "n_membri": len(membri),
        "membri": sorted(membri, key=lambda m: m["nume"]),
        "roluri_oficiale": roluri,
        "_provenance": _prov(),
    }


@mcp.tool()
def stats_globale() -> dict:
    """Sumarul global ROMEGA: dimensiunile dataset-ului (persoane, companii,
    legături, partide, comisii, participații) + câteva agregate-cheie.

    Util pentru a înțelege acoperirea și scara datelor înainte de interogări
    detaliate.
    """
    counts = _rows(
        """
        SELECT
          (SELECT COUNT(*) FROM person)            AS n_persoane,
          (SELECT COUNT(*) FROM person WHERE camera IS NOT NULL) AS n_parlamentari,
          (SELECT COUNT(*) FROM person WHERE incredere='high')   AS n_persoane_high,
          (SELECT COUNT(*) FROM person WHERE incredere='candidat') AS n_candidati,
          (SELECT COUNT(*) FROM company)           AS n_companii,
          (SELECT COUNT(*) FROM company WHERE is_soe) AS n_intreprinderi_stat,
          (SELECT COUNT(*) FROM company WHERE bvb) AS n_companii_bvb,
          (SELECT COUNT(*) FROM person_company)    AS n_legaturi_pers_firma,
          (SELECT COUNT(*) FROM party)             AS n_partide,
          (SELECT COUNT(*) FROM committee_member)  AS n_apartenente_comisii,
          (SELECT COUNT(*) FROM state_holding)     AS n_participatii_bvb,
          (SELECT SUM(contracte_ron) FROM company) AS total_contracte_ron,
          (SELECT SUM(subventie_lei) FROM party)   AS total_subventii_lei
        """
    )
    return {**counts[0],
            "_provenance": _prov({"definitii": {
                "incredere": "high=identitate certă · context=plauzibilă · "
                             "candidat=match pe nume, posibil omonim",
                "is_soe": "state-owned enterprise (întreprindere de stat)",
            }})}


# ----------------------------------------------------------------------------
# Entry-point
# ----------------------------------------------------------------------------
def run() -> None:
    """Pornește serverul MCP pe stdio (pentru Claude Desktop & co.)."""
    mcp.run()


if __name__ == "__main__":
    run()
