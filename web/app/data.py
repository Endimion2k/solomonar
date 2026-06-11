"""Data-layer ROMEGA pentru clientul Streamlit — citește JSON-urile statice din data/v1 (cache).

Sursa = data/v1 local (sau ROMEGA_DATA = director / URL bază GitHub Pages). Funcțiile întorc
DataFrame-uri/dict-uri memoizate (@st.cache_data). Contractul stabil folosit de toate paginile.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache

import pandas as pd
import streamlit as st

_HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("ROMEGA_DATA") or os.path.normpath(os.path.join(_HERE, "..", "..", "data", "v1"))
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


# ---------------- search index ----------------
@st.cache_data(show_spinner=False)
def search_index() -> list:
    return _load_raw("search/index.json").get("items", [])
