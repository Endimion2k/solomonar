"""Data-layer SOLOMONAR pentru clientul Streamlit — citește JSON-urile statice din data/v1 (cache).

Sursa = data/v1 local (sau SOLOMONAR_DATA = director / URL bază GitHub Pages). Funcțiile întorc
DataFrame-uri/dict-uri memoizate (@st.cache_data). Contractul stabil folosit de toate paginile.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache

import pandas as pd
import streamlit as st

_HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("SOLOMONAR_DATA") or os.path.normpath(os.path.join(_HERE, "..", "..", "data", "v1"))
LIVE = DATA.startswith("http")


@lru_cache(maxsize=256)
def _load_raw(rel: str):
    if LIVE:
        import urllib.request
        with urllib.request.urlopen(f"{DATA.rstrip('/')}/{rel}", timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    p = os.path.join(DATA, rel.replace("/", os.sep))
    if not os.path.exists(p):
        return {}
    return json.load(open(p, encoding="utf-8"))


@st.cache_data(show_spinner=False)
def load(rel: str):
    return _load_raw(rel)


# ---------------- sumar ----------------
@st.cache_data(show_spinner=False)
def stats() -> dict:
    return _load_raw("stats.json")


# ---------------- persoane (graf gold) ----------------
@st.cache_data(show_spinner=False)
def persoane_df() -> pd.DataFrame:
    ps = _load_raw("graf/persoane_gold.json").get("persoane", [])
    rows = []
    for p in ps:
        pl = p.get("parlamentar") or {}
        rows.append({
            "romega_id": p.get("romega_id"), "nume": (p.get("nume_key") or "").title(),
            "incredere": p.get("incredere"), "n_declaratii": p.get("n_declaratii", 0),
            "n_companii": p.get("n_companii", 0), "contracte_ron": p.get("total_contracte_ron") or 0,
            "camera": pl.get("camera"), "partid": pl.get("partid"), "judet": pl.get("judet"),
            "comisii": len(pl.get("comisii") or []), "plx_initiate": pl.get("plx_initiate") or 0,
            "are_cv": p.get("are_cv", False),
        })
    return pd.DataFrame(rows)


@st.cache_data(show_spinner=False)
def persoana(romega_id: str) -> dict:
    for p in _load_raw("graf/persoane_gold.json").get("persoane", []):
        if p.get("romega_id") == romega_id:
            return p
    return {}


# ---------------- companii ----------------
@st.cache_data(show_spinner=False)
def companii_df() -> pd.DataFrame:
    idx = _load_raw("companii/_index.json").get("data", [])
    cf = {int(r["cui"]): r for r in _load_raw("achizitii/contracte_firme.json").get("firme", [])
          if str(r.get("cui", "")).isdigit()}
    bvb = {b["nume"].lower(): b for b in _load_raw("companii/actionariat_bvb.json").get("companii", [])}
    rows = []
    for c in idx:
        try:
            cui = int(c["cui"])
        except (ValueError, TypeError):
            continue
        fin = c.get("financials") or {}
        ctr = cf.get(cui, {})
        bv = next((b for k, b in bvb.items() if k in (c.get("name", "").lower())), {})
        rows.append({
            "cui": cui, "nume": c.get("name", ""), "sector": c.get("sector"),
            "tutela": c.get("tutelary_authority"), "judet": c.get("county"),
            "bvb": bool(c.get("bvb_listed")), "salariati": fin.get("nr_salariati"),
            "cifra_afaceri": fin.get("cifra_afaceri"), "profit": fin.get("profit_net"),
            "procent_stat": bv.get("procent_stat"), "contracte_ron": ctr.get("total_ron"),
            "contracte_nr": ctr.get("nr_contracte"), "nr_reps": len(c.get("legal_reps") or []),
        })
    return pd.DataFrame(rows)


# ---------------- achiziții ----------------
@st.cache_data(show_spinner=False)
def contracte_df() -> pd.DataFrame:
    return pd.DataFrame(_load_raw("achizitii/contracte_firme.json").get("firme", []))


@st.cache_data(show_spinner=False)
def achizitii_directe_df() -> pd.DataFrame:
    """Furnizorii de achiziții directe (cumpărări directe SICAP 2007-2025, agregate pe CUI)."""
    d = _load_raw("companii/achizitii_directe.json")
    df = pd.DataFrame(d.get("furnizori", []))
    if not df.empty:
        df["ani_activi"] = df["ani_activi"].apply(lambda a: ", ".join(a) if isinstance(a, list) else (a or ""))
        df["top_autoritati"] = df["top_autoritati"].apply(
            lambda a: " · ".join(a) if isinstance(a, list) else (a or ""))
    return df


@st.cache_data(show_spinner=False)
def achizitii_directe_meta() -> dict:
    d = _load_raw("companii/achizitii_directe.json")
    return {"total_furnizori": d.get("total_furnizori", 0), "total_achizitii": d.get("total_achizitii", 0),
            "valoare_totala_ron": d.get("valoare_totala_ron", 0), "sursa": d.get("sursa", "")}


@st.cache_data(show_spinner=False)
def firma_profil(cui) -> dict:
    """Profil 'bani de la stat' al unei firme după CUI: contracte (licitații) + achiziții directe.

    Datele sunt AGREGATE per firmă (total, număr, ani, top autorități) — nu contract-cu-contract;
    obiectul fiecărui contract nu e în setul public. Întoarce {} dacă CUI invalid.
    """
    try:
        cui_i = int(cui)
    except (TypeError, ValueError):
        return {}
    out: dict = {"cui": cui_i}
    for r in _load_raw("achizitii/contracte_firme.json").get("firme", []):
        if str(r.get("cui")) == str(cui_i):
            out["contracte"] = {"total_ron": r.get("total_ron"), "nr": r.get("nr_contracte"),
                                "ani": r.get("ani") or [], "nume": r.get("nume")}
            break
    for r in _load_raw("companii/achizitii_directe.json").get("furnizori", []):
        if str(r.get("cui")) == str(cui_i):
            out["achizitii_directe"] = {"total_ron": r.get("total_ron"), "nr": r.get("nr"),
                                        "ani_activi": r.get("ani_activi") or [],
                                        "top_autoritati": r.get("top_autoritati") or [],
                                        "nume": r.get("nume")}
            break
    for r in _load_raw("companii/firme_onrc.json").get("firme", []):
        if str(r.get("cui")) == str(cui_i):
            out["onrc"] = {"caen": r.get("caen"), "caen_domeniu": r.get("caen_domeniu"),
                           "forma_juridica": r.get("forma_juridica"), "judet": r.get("judet"),
                           "localitate": r.get("localitate"), "an_infiintare": r.get("an_infiintare")}
            break
    return out


@st.cache_data(show_spinner=False)
def firme_nume_map() -> dict:
    """Hartă cui (int) -> denumire firmă. firme_onrc.json (dump ONRC) nu are denumirea; o luăm din
    reprezentanții legali (denumire), cu fallback pe numele din contracte / achiziții directe."""
    out: dict = {}
    for c in _load_raw("companii/reprezentanti.json").get("companii", []) or []:
        try:
            cui = int(c.get("cui"))
        except (TypeError, ValueError):
            continue
        if c.get("denumire"):
            out[cui] = c["denumire"]
    for path, key in (("achizitii/contracte_firme.json", "firme"),
                      ("companii/achizitii_directe.json", "furnizori")):
        for r in _load_raw(path).get(key, []) or []:
            try:
                cui = int(r.get("cui"))
            except (TypeError, ValueError):
                continue
            if cui not in out and r.get("nume"):
                out[cui] = r["nume"]
    return out


# ---------------- analiză de rețea (inele / huburi / poduri) ----------------
@st.cache_data(show_spinner=False)
def network_metrics() -> dict:
    return _load_raw("graf/network_metrics.json")


@st.cache_data(show_spinner=False)
def ro_judete_geojson() -> dict:
    """GeoJSON cu județele RO (simplificat). proprietăți: judet (cheie normalizată), nume (afișare)."""
    return _load_raw("geo/ro_judete.geojson")


@st.cache_data(show_spinner=False)
def changelog() -> dict:
    """Modificări față de rebuild-ul anterior (deepdiff). Gol până la al 2-lea rebuild."""
    return _load_raw("changelog.json")


@st.cache_data(show_spinner=False)
def redflags() -> dict:
    """Red-flags achiziții (single-bid + fragmentare), metodologie OCDS. Vezi harvest_redflags.py."""
    return _load_raw("redflags.json")


# ---------------- firme ONRC (profil firme cu bani de stat) ----------------
@st.cache_data(show_spinner=False)
def firme_onrc() -> pd.DataFrame:
    """Profil ONRC al firmelor care au luat bani de la stat (contracte + achiziții directe).

    Sursa: data/v1/companii/firme_onrc.json. Adaugă coloane derivate:
      - este_noua: flag 'firmă nouă cu bani de stat' (înființată cu ≤1 an înainte de prima achiziție)
      - mama_straina: are firmă-mamă într-o țară străină (exclude România)
      - flaguri_txt: flagurile concatenate pentru afișare
    """
    firme = _load_raw("companii/firme_onrc.json").get("firme", [])
    df = pd.DataFrame(firme)
    if df.empty:
        return df

    def _flaguri(x):
        return x if isinstance(x, list) else []

    df["flaguri"] = df["flaguri"].apply(_flaguri)
    df["este_noua"] = df["flaguri"].apply(lambda fl: any("firmă nouă" in f for f in fl))
    df["flaguri_txt"] = df["flaguri"].apply(lambda fl: " · ".join(fl))
    tm = df["tara_mama"].fillna("").str.strip()
    df["mama_straina"] = (tm != "") & (tm.str.lower() != "românia")
    df["nume"] = df["cui"].map(firme_nume_map()).fillna("")
    return df


@st.cache_data(show_spinner=False)
def firme_onrc_meta() -> dict:
    d = _load_raw("companii/firme_onrc.json")
    return {
        "total": d.get("total", 0),
        "cu_caen": d.get("cu_caen", 0),
        "cu_mama_straina": d.get("cu_mama_straina", 0),
        "flagged": d.get("flagged", 0),
        "sursa": d.get("sursa", ""),
        "nota": d.get("nota", ""),
    }


# ---------------- follow-the-money ----------------
@st.cache_data(show_spinner=False)
def follow_money() -> dict:
    return _load_raw("graf/follow_the_money.json")


@st.cache_data(show_spinner=False)
def retele_coadministrare() -> pd.DataFrame:
    return pd.DataFrame(_load_raw("analytics/retele_coadministrare.json").get("data", []))


# ---------------- partide ----------------
@st.cache_data(show_spinner=False)
def partide_df() -> pd.DataFrame:
    return pd.DataFrame(_load_raw("partide/partide.json").get("partide", []))


@st.cache_data(show_spinner=False)
def subventii_df() -> pd.DataFrame:
    return pd.DataFrame(_load_raw("partide/subventii.json").get("subventii", []))


# ---------------- bugete ----------------
@st.cache_data(show_spinner=False)
def bugete_uat_df() -> pd.DataFrame:
    return pd.DataFrame(_load_raw("bugete/uat.json"))


@st.cache_data(show_spinner=False)
def bgc_df() -> pd.DataFrame:
    return pd.DataFrame(_load_raw("bugete/bgc.json"))


# ---------------- DNA ----------------
@st.cache_data(show_spinner=False)
def dna_df() -> pd.DataFrame:
    return pd.DataFrame(_load_raw("audit/dna.json").get("data", []))


# ---------------- comisii / legislativ ----------------
@st.cache_data(show_spinner=False)
def comisii_senat() -> list:
    return _load_raw("comisii/senat_comisii.json").get("comisii", [])


@st.cache_data(show_spinner=False)
def plx_initiatori_df() -> pd.DataFrame:
    return pd.DataFrame(_load_raw("comisii/plx_initiatori.json").get("plx", []))


# ---------------- analytics (DuckDB views) ----------------
@st.cache_data(show_spinner=False)
def analytics(name: str) -> pd.DataFrame:
    return pd.DataFrame(_load_raw(f"analytics/{name}.json").get("data", []))


# ---------------- alerte (semnale) ----------------
@st.cache_data(show_spinner=False)
def alerte() -> dict:
    """Semnale de interes generate automat din date deschise (NU acuzații).

    Întoarce dict-ul brut: {disclaimer, total, pe_severitate, pe_tip, agregate, alerte:[...]}.
    Câmpul alerte[i].entitate poate fi string SAU dict (ex. {cui, forma_juridica, ...}).
    """
    return _load_raw("alerte.json")


# ---------------- sancțiuni & PEP ----------------
@st.cache_data(show_spinner=False)
def sanctiuni() -> dict:
    """Entități cu legătură RO din OpenSanctions (sancțiuni internaționale + PEP).

    Întoarce: {meta: {total, sanctiuni, pep, in_graf, nota}, df: DataFrame}.
    df coloane: nume, nume_key, schema, dataset ('sanctions'|'peps'), topics, tara,
    pozitie, motiv, liste, in_graf, romega_id, n_declaratii, n_companii.
    """
    d = _load_raw("sanctiuni_ro.json")
    ents = d.get("entitati", [])
    rows = []
    for e in ents:
        rows.append({
            "nume": e.get("nume") or "",
            "nume_key": e.get("nume_key") or "",
            "schema": e.get("schema") or "",
            "dataset": e.get("dataset") or "",
            "topics": e.get("topics") or [],
            "tara": e.get("tara") or [],
            "pozitie": e.get("pozitie"),
            "motiv": e.get("motiv"),
            "liste": e.get("liste") or [],
            "in_graf": bool(e.get("in_graf")),
            "romega_id": e.get("romega_id"),
            "n_declaratii": e.get("n_declaratii", 0),
            "n_companii": e.get("n_companii", 0),
        })
    df = pd.DataFrame(rows)
    meta = {
        "total": d.get("total", len(ents)),
        "sanctiuni": d.get("sanctiuni", 0),
        "pep": d.get("pep", 0),
        "in_graf": d.get("in_graf", 0),
        "nota": d.get("nota", ""),
    }
    return {"meta": meta, "df": df}


# ---------------- search index ----------------
@st.cache_data(show_spinner=False)
def search_index() -> list:
    return _load_raw("search/index.json").get("items", [])
