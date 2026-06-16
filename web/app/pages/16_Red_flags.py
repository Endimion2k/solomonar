"""Red-flags achiziții — single-bid + fragmentare (metodologie OCDS), din datele per-linie SICAP.

Sursă: data/v1/redflags.json (vezi pipeline/harvest_redflags.py). Lead-uri de verificat, NU acuzații.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, GridOptionsBuilder, JsCode

import sys as _sys, pathlib as _pl  # bootstrap: import 'app' fără PYTHONPATH (rulare directă/deploy)
for _a in _pl.Path(__file__).resolve().parents:
    if (_a / 'app').is_dir():
        _sys.path.insert(0, str(_a)); break

from app import data
from app.theme import (DANGER, WARNING, apply_theme, fmt_int, fmt_lei, kpi_card,
                       page_header, sidebar_brand)

st.set_page_config(page_title="Red-flags · SOLOMONAR", page_icon="🚩", layout="wide")
apply_theme()
sidebar_brand()
page_header("🚩 Red-flags achiziții",
            "Indicatori de risc din datele per-linie SICAP: contracte cu o singură ofertă (single-bid) "
            "și atribuiri directe repetate (fragmentare). Metodologie OCDS — lead-uri de verificat.")

rf = data.redflags()
if not rf or not (rf.get("single_bid") or rf.get("fragmentare")):
    st.warning("Datele de red-flags nu sunt încă generate. Rulează "
               "`python -m pipeline.harvest_redflags` (stream din data.gov.ro).")
    st.stop()

sb = rf.get("single_bid") or {}
fr = rf.get("fragmentare") or {}
sb_items = sb.get("items") or []
fr_items = fr.get("items") or []

st.warning(rf.get("disclaimer", ""), icon="⚠️")

c1, c2, c3, c4 = st.columns(4)
kpi_card(c1, "Contracte single-bid", fmt_int(sb.get("total", len(sb_items))),
         help="Licitații cu o singură ofertă primită — risc de competiție redusă (OCDS R018).")
val_sb = sum(x.get("valoare_ron", 0) for x in sb_items)
kpi_card(c2, "Valoare single-bid (top)", fmt_lei(val_sb))
kpi_card(c3, "Perechi fragmentare", fmt_int(fr.get("total", len(fr_items))),
         help="Autoritate→furnizor cu multe cumpărări directe repetate.")
kpi_card(c4, "Ani acoperiți", ", ".join(str(a) for a in rf.get("ani", [])) or "—")

st.divider()

_lei_fmt = JsCode("function(p){return p.value==null?'':Math.round(p.value).toLocaleString('ro-RO');}")


def _grid(df, page=20, height=520, numeric_cols=()):
    gob = GridOptionsBuilder.from_dataframe(df)
    gob.configure_default_column(filter=True, sortable=True, resizable=True, floatingFilter=True)
    gob.configure_pagination(paginationAutoPageSize=False, paginationPageSize=page)
    for col in numeric_cols:
        gob.configure_column(col, type=["numericColumn"], valueFormatter=_lei_fmt)
    AgGrid(df, gridOptions=gob.build(), theme="streamlit", height=height,
           fit_columns_on_grid_load=False, allow_unsafe_jscode=True,
           enable_enterprise_modules=False)


tab_sb, tab_fr = st.tabs(["🅰 Single-bid (o singură ofertă)", "🧩 Fragmentare (atribuiri directe repetate)"])

with tab_sb:
    st.caption(sb.get("nota", ""))
    if sb_items:
        df = pd.DataFrame(sb_items)
        df = df.rename(columns={
            "valoare_ron": "Valoare (lei)", "autoritate": "Autoritate", "castigator": "Câștigător",
            "obiect": "Obiect", "procedura": "Procedură", "cpv": "CPV", "an": "An", "data": "Dată"})
        keep = [c for c in ["Autoritate", "Câștigător", "cui", "Valoare (lei)", "Obiect",
                            "Procedură", "Dată"] if c in df.columns]
        df = df[keep].rename(columns={"cui": "CUI"})
        _grid(df, numeric_cols=["Valoare (lei)"])
    else:
        st.info("Niciun contract single-bid în setul curent.")

with tab_fr:
    st.caption(fr.get("nota", ""))
    if fr_items:
        df = pd.DataFrame(fr_items)
        df["ani_activi"] = df.get("ani_activi", pd.Series([[]] * len(df))).apply(
            lambda a: ", ".join(str(x) for x in a) if isinstance(a, list) else "")
        df = df.rename(columns={
            "autoritate": "Autoritate", "castigator": "Furnizor", "cui": "CUI",
            "nr": "Nr. cumpărări", "total": "Total (lei)", "ani_activi": "Ani"})
        keep = [c for c in ["Autoritate", "Furnizor", "CUI", "Nr. cumpărări", "Total (lei)", "Ani"]
                if c in df.columns]
        _grid(df[keep], numeric_cols=["Total (lei)"])
    else:
        st.info("Nicio pereche de fragmentare în setul curent.")

st.divider()
st.caption(f"Sursă: data/v1/redflags.json (per-linie SICAP, data.gov.ro). Generat: {rf.get('generat', '')}. "
           "Single-bid și atribuirile directe repetate pot fi perfect legale — verifică fiecare caz.")
