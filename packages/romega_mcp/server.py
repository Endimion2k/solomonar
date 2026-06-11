"""Server MCP ROMEGA — expune datele de transparență pentru interogare conversațională.

Orice agent MCP (Claude Desktop / Cursor / Continue) poate întreba natural despre persoane, companii
de stat, follow-the-money, contracte, partide, DNA, comisii. Citește JSON-urile statice din data/v1.

Rulare:  romega-mcp   (sau: python -m romega_mcp.server)
Config Claude Desktop:  {"mcpServers": {"romega": {"command": "romega-mcp"}}}
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from functools import lru_cache

from mcp.server.fastmcp import FastMCP

DATA = os.environ.get("ROMEGA_DATA") or os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "v1"))

mcp = FastMCP("romega", instructions=(
    "ROMEGA — transparența aparatului de stat român. Date publice agregate: declarații de avere/interese, "
    "companii de stat (bilanț, acționariat, reprezentanți), achiziții publice, follow-the-money, partide "
    "(subvenții), bugete, DNA, comisii parlamentare. IMPORTANT: legăturile persoană↔firmă sunt pe NUME "
    "(fără CNP) → 'candidat' poate fi omonim; doar 'confirmat'/auto-declarat e defensabil. Comunicatele DNA "
    "sunt trimiteri în judecată, NU condamnări (prezumția de nevinovăție)."))


@lru_cache(maxsize=64)
def _load(rel: str):
    p = os.path.join(DATA, rel.replace("/", os.sep))
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()


# ---------------- TOOLS ----------------
@mcp.tool()
def stats() -> dict:
    """Sumarul global ROMEGA: câte declarații, persoane, companii, contracte, CV, partide, bugete, DNA."""
    return _load("stats.json")


@mcp.tool()
def search_persoana(nume: str, limit: int = 15) -> list[dict]:
    """Caută persoane în graf după nume. Întoarce: nume, încredere, nr declarații/companii, contracte, rol parlamentar."""
    q = _norm(nume)
    out = []
    for p in _load("graf/persoane_gold.json").get("persoane", []):
        if q in _norm(p.get("nume_key", "")):
            pl = p.get("parlamentar") or {}
            out.append({"romega_id": p.get("romega_id"), "nume": (p.get("nume_key") or "").title(),
                        "incredere": p.get("incredere"), "n_declaratii": p.get("n_declaratii"),
                        "n_companii": p.get("n_companii"), "contracte_ron": p.get("total_contracte_ron"),
                        "rol": (pl.get("camera") + " " + str(pl.get("partid"))) if pl else None})
            if len(out) >= limit:
                break
    return out


@mcp.tool()
def get_persoana(romega_id: str) -> dict:
    """Fișa completă a unei persoane (din search_persoana): declarații, companii conduse, CV, partid, comisii, proiecte."""
    for p in _load("graf/persoane_gold.json").get("persoane", []):
        if p.get("romega_id") == romega_id:
            return p
    return {}


@mcp.tool()
def search_companie(nume: str = "", sector: str = "", judet: str = "", doar_bvb: bool = False,
                    limit: int = 20) -> list[dict]:
    """Caută companii de stat după nume/sector/județ. Întoarce bilanț, % deținut de stat (BVB), contracte, tutelă."""
    cf = {int(r["cui"]): r for r in _load("achizitii/contracte_firme.json").get("firme", [])
          if str(r.get("cui", "")).isdigit()}
    bvb = {b["nume"].lower(): b for b in _load("companii/actionariat_bvb.json").get("companii", [])}
    qn, qs, qj = _norm(nume), _norm(sector), _norm(judet)
    out = []
    for c in _load("companii/_index.json").get("data", []):
        if qn and qn not in _norm(c.get("name", "")):
            continue
        if qs and qs not in _norm(c.get("sector", "")):
            continue
        if qj and qj not in _norm(c.get("county", "")):
            continue
        if doar_bvb and not c.get("bvb_listed"):
            continue
        try:
            cui = int(c["cui"])
        except (ValueError, TypeError):
            continue
        fin = c.get("financials") or {}
        bv = next((b for k, b in bvb.items() if k in (c.get("name", "").lower())), {})
        out.append({"cui": cui, "nume": c.get("name"), "sector": c.get("sector"),
                    "tutela": c.get("tutelary_authority"), "judet": c.get("county"),
                    "cifra_afaceri_ron": fin.get("cifra_afaceri"), "profit_ron": fin.get("profit_net"),
                    "salariati": fin.get("nr_salariati"), "procent_stat": bv.get("procent_stat"),
                    "contracte_ron": (cf.get(cui) or {}).get("total_ron"),
                    "reprezentanti": c.get("legal_reps", [])[:8]})
        if len(out) >= limit:
            break
    return out


@mcp.tool()
def follow_the_money(doar_confirmate: bool = True) -> dict:
    """Persoane (declaranți/parlamentari) ale căror FIRME au câștigat contracte de stat. doar_confirmate=True
    întoarce doar conflictele auto-declarate (defensabile). False adaugă candidații nume-bazați (posibili omonimi)."""
    fm = _load("graf/follow_the_money.json")
    res = {"nota": fm.get("nota"), "confirmate": fm.get("confirmate", [])}
    if not doar_confirmate:
        res["candidati_neverificati"] = fm.get("leaduri_neverificate", [])[:50]
    return res


@mcp.tool()
def top_contracte_firme(limit: int = 20) -> list[dict]:
    """Top firme după valoarea contractelor de stat câștigate (SICAP)."""
    fr = sorted(_load("achizitii/contracte_firme.json").get("firme", []),
                key=lambda x: -(x.get("total_ron") or 0))
    return [{"nume": f.get("nume"), "cui": f.get("cui"), "total_ron": f.get("total_ron"),
             "nr_contracte": f.get("nr_contracte")} for f in fr[:limit]]


@mcp.tool()
def participatii_stat() -> list[dict]:
    """Companiile listate la BVB cu participație de stat (% deținut de stat + capitalizare)."""
    return _load("analytics/participatii_stat.json").get("data", [])


@mcp.tool()
def subventii_partide() -> list[dict]:
    """Subvențiile de stat pentru partide (total istoric 2008-2026 + nr. parlamentari + rapoarte RVC)."""
    return [{"partid": p["cod"], "subventie_totala_lei": p.get("total_subventie_lei"),
             "nr_deputati": p.get("nr_deputati"), "nr_senatori": p.get("nr_senatori"),
             "rapoarte_rvc": p.get("nr_rapoarte_rvc")}
            for p in _load("partide/partide.json").get("partide", [])]


@mcp.tool()
def search_dna(text: str = "", an: int = 0, limit: int = 15) -> list[dict]:
    """Caută în comunicatele DNA (trimiteri în judecată — PREZUMȚIA DE NEVINOVĂȚIE) după text/nume sau an."""
    q = _norm(text)
    out = []
    for c in _load("audit/dna.json").get("data", []):
        if an and c.get("an") != an:
            continue
        blob = _norm((c.get("titlu") or "") + " " + " ".join(c.get("nume_extrase", [])))
        if q and q not in blob:
            continue
        out.append({"id": c.get("id"), "data": c.get("data"), "an": c.get("an"),
                    "titlu": (c.get("titlu") or "")[:150], "nume": c.get("nume_extrase", [])[:6],
                    "url": c.get("url")})
        if len(out) >= limit:
            break
    return out


@mcp.tool()
def comisie_senat(nume: str) -> dict:
    """Componența unei comisii a Senatului (membri + rol) după nume parțial (ex. 'buget', 'juridica')."""
    q = _norm(nume)
    for c in _load("comisii/senat_comisii.json").get("comisii", []):
        if q in _norm(c.get("nume", "")):
            return {"comisie": c.get("nume"), "n_membri": c.get("n_membri"),
                    "membri": [{"nume": m.get("nume"), "rol": m.get("rol")} for m in c.get("membri", [])]}
    return {"eroare": f"nicio comisie care conține '{nume}'"}


@mcp.tool()
def analytics_view(nume: str) -> list[dict]:
    """View analitic DuckDB. Nume valide: sumar_sector, sumar_judet, companii_per_tutela, participatii_stat,
    oficiali_contracte, retele_coadministrare."""
    return _load(f"analytics/{nume}.json").get("data", [])


def run() -> None:
    mcp.run()


if __name__ == "__main__":
    run()
