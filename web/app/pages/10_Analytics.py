"""SOLOMONAR — Analytics: vitrina view-urilor analitice din stratul gold (DuckDB)."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import sys as _sys, pathlib as _pl  # bootstrap: import 'app' fără PYTHONPATH (rulare directă/deploy)
for _a in _pl.Path(__file__).resolve().parents:
    if (_a / 'app').is_dir():
        _sys.path.insert(0, str(_a)); break

from app import data
from app.theme import (ACCENT, ACCENT_2, SUCCESS, WARNING, TEXT_DIM, CONF_COLORS,
                       apply_theme, fmt_int, fmt_lei, page_header, sidebar_brand)

st.set_page_config(page_title="Analytics · SOLOMONAR", page_icon="📊", layout="wide")
apply_theme()
sidebar_brand()

page_header("Analytics — vitrina stratului gold",
            "View-uri analitice pre-agregate, generate de stratul gold DuckDB: sectoare, "
            "ministere tutelare, oficiali cu contracte și participații de stat la BVB.")


def _num(series):
    return pd.to_numeric(series, errors="coerce")


def _parse_ro_number(val):
    """Parsează un număr în format românesc ('20.964.250.633,00') -> float."""
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


# =====================================================================
# 1. SUMAR SECTOR
# =====================================================================
st.markdown("### Companii de stat pe sector")
sec = data.analytics("sumar_sector")
if sec.empty:
    st.info("View `sumar_sector` indisponibil.")
else:
    sec = sec.copy()
    for c in ("n_companii", "contracte_totale", "salariati", "procent_stat_mediu",
              "cifra_afaceri_totala"):
        if c in sec.columns:
            sec[c] = _num(sec[c])

    plot = sec.dropna(subset=["contracte_totale"]).sort_values(
        "contracte_totale", ascending=False)
    if not plot.empty:
        fig = go.Figure(go.Bar(
            x=plot["contracte_totale"], y=plot["sector"], orientation="h",
            marker_color=ACCENT, text=[fmt_lei(v) for v in plot["contracte_totale"]],
            textposition="auto",
            hovertemplate="%{y}<br>contracte: %{x:,.0f} lei<extra></extra>",
        ))
        fig.update_layout(height=max(320, 30 * len(plot)),
                          yaxis=dict(autorange="reversed"),
                          xaxis_title="contracte câștigate (lei)",
                          margin=dict(l=10, r=20, t=10, b=40))
        st.plotly_chart(fig, use_container_width=True)

    st.dataframe(
        sec, use_container_width=True, hide_index=True,
        column_config={
            "sector": st.column_config.TextColumn("Sector"),
            "n_companii": st.column_config.NumberColumn("Companii", format="%d"),
            "cifra_afaceri_totala": st.column_config.NumberColumn("Cifra afaceri (lei)", format="%.0f"),
            "contracte_totale": st.column_config.NumberColumn("Contracte (lei)", format="%.0f"),
            "salariati": st.column_config.NumberColumn("Angajați", format="%d"),
            "procent_stat_mediu": st.column_config.NumberColumn("% stat mediu", format="%.1f"),
        })

st.divider()

# =====================================================================
# 2. COMPANII PER TUTELĂ (minister)
# =====================================================================
st.markdown("### Companii pe minister tutelar")
tut = data.analytics("companii_per_tutela")
if tut.empty:
    st.info("View `companii_per_tutela` indisponibil.")
else:
    tut = tut.copy()
    for c in ("n_companii", "contracte", "salariati"):
        if c in tut.columns:
            tut[c] = _num(tut[c])
    tut["tutela"] = tut["tutela"].fillna("—").astype(str)

    metric_map = {"Contracte (lei)": "contracte", "Angajați": "salariati",
                  "Număr companii": "n_companii"}
    pick = st.selectbox("Clasament ministere după", list(metric_map.keys()), key="tut_metric")
    mcol = metric_map[pick]
    plot = tut.dropna(subset=[mcol]).sort_values(mcol, ascending=False).head(15)
    if not plot.empty:
        # scurtăm etichetele lungi de minister
        labels = [t if len(t) <= 42 else t[:39] + "…" for t in plot["tutela"]]
        is_lei = mcol == "contracte"
        text = [fmt_lei(v) for v in plot[mcol]] if is_lei else [fmt_int(v) for v in plot[mcol]]
        fig = go.Figure(go.Bar(
            x=plot[mcol], y=labels, orientation="h",
            marker_color=ACCENT_2, text=text, textposition="auto",
            customdata=plot["tutela"],
            hovertemplate="%{customdata}<br>%{x:,.0f}<extra></extra>",
        ))
        fig.update_layout(height=max(360, 30 * len(plot)),
                          yaxis=dict(autorange="reversed"),
                          xaxis_title=pick, margin=dict(l=10, r=20, t=10, b=40))
        st.plotly_chart(fig, use_container_width=True)

    st.dataframe(
        tut.sort_values("n_companii", ascending=False),
        use_container_width=True, hide_index=True,
        column_config={
            "tutela": st.column_config.TextColumn("Minister tutelar", width="large"),
            "n_companii": st.column_config.NumberColumn("Companii", format="%d"),
            "contracte": st.column_config.NumberColumn("Contracte (lei)", format="%.0f"),
            "salariati": st.column_config.NumberColumn("Angajați", format="%.0f"),
        })

st.divider()

# =====================================================================
# 3. OFICIALI CU CONTRACTE
# =====================================================================
st.markdown("### Oficiali cu firme care au contracte de stat")
ofi = data.analytics("oficiali_contracte")
if ofi.empty:
    st.info("View `oficiali_contracte` indisponibil.")
else:
    ofi = ofi.copy()
    for c in ("n_declaratii", "contracte_firme", "n_firme"):
        if c in ofi.columns:
            ofi[c] = _num(ofi[c])
    ofi["nume"] = ofi["nume"].fillna("—").astype(str).str.title()
    ofi["incredere"] = ofi["incredere"].fillna("candidat").astype(str)

    # filtru pe nivel de încredere
    levels = [lvl for lvl in ["high", "context", "candidat"] if lvl in set(ofi["incredere"])]
    sel = st.multiselect("Nivel de încredere al legăturii", levels, default=levels,
                         key="ofi_conf")
    view = ofi[ofi["incredere"].isin(sel)] if sel else ofi

    plot = view.dropna(subset=["contracte_firme"]).sort_values(
        "contracte_firme", ascending=False).head(15)
    if not plot.empty:
        colors = [CONF_COLORS.get(lvl, TEXT_DIM) for lvl in plot["incredere"]]
        fig = go.Figure(go.Bar(
            x=plot["contracte_firme"], y=plot["nume"], orientation="h",
            marker_color=colors,
            text=[fmt_lei(v) for v in plot["contracte_firme"]], textposition="auto",
            customdata=plot["incredere"],
            hovertemplate="%{y}<br>contracte firme: %{x:,.0f} lei"
                          "<br>încredere: %{customdata}<extra></extra>",
        ))
        fig.update_layout(height=max(360, 30 * len(plot)),
                          yaxis=dict(autorange="reversed"),
                          xaxis_title="contracte de stat ale firmelor asociate (lei)",
                          margin=dict(l=10, r=20, t=10, b=40))
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Culoarea = nivelul de încredere al asocierii persoană↔firmă "
                   "(verde=high, cyan=context, gri=candidat).")

    st.dataframe(
        view.sort_values("contracte_firme", ascending=False),
        use_container_width=True, hide_index=True,
        column_config={
            "nume": st.column_config.TextColumn("Nume"),
            "incredere": st.column_config.TextColumn("Încredere"),
            "camera": st.column_config.TextColumn("Cameră"),
            "partid": st.column_config.TextColumn("Partid"),
            "n_declaratii": st.column_config.NumberColumn("Declarații", format="%d"),
            "contracte_firme": st.column_config.NumberColumn("Contracte firme (lei)", format="%.0f"),
            "n_firme": st.column_config.NumberColumn("Firme", format="%d"),
        })

st.divider()

# =====================================================================
# 4. PARTICIPAȚII DE STAT (BVB)
# =====================================================================
st.markdown("### Participații de stat la companii listate (BVB)")
par = data.analytics("participatii_stat")
if par.empty:
    st.info("View `participatii_stat` indisponibil.")
else:
    par = par.copy()
    par["procent_stat"] = _num(par["procent_stat"])
    par["cap_num"] = par["capitalizare"].map(_parse_ro_number)
    par["nume"] = par["nume"].fillna("—").astype(str)

    cc1, cc2 = st.columns(2)

    with cc1:
        st.markdown("**% deținut de stat**")
        plot = par.dropna(subset=["procent_stat"]).sort_values("procent_stat", ascending=False)
        if not plot.empty:
            fig = go.Figure(go.Bar(
                x=plot["procent_stat"], y=plot["nume"], orientation="h",
                marker_color=SUCCESS,
                text=[f"{v:.1f}%" for v in plot["procent_stat"]], textposition="auto",
                hovertemplate="%{y}<br>%{x:.2f}% deținut de stat<extra></extra>",
            ))
            fig.update_layout(height=max(320, 28 * len(plot)),
                              yaxis=dict(autorange="reversed"),
                              xaxis_title="% deținut de stat",
                              margin=dict(l=10, r=20, t=10, b=40))
            st.plotly_chart(fig, use_container_width=True)

    with cc2:
        st.markdown("**Capitalizare bursieră (lei)**")
        plot = par.dropna(subset=["cap_num"]).sort_values("cap_num", ascending=False)
        if not plot.empty:
            fig = go.Figure(go.Bar(
                x=plot["cap_num"], y=plot["nume"], orientation="h",
                marker_color=WARNING,
                text=[fmt_lei(v) for v in plot["cap_num"]], textposition="auto",
                hovertemplate="%{y}<br>cap.: %{x:,.0f} lei<extra></extra>",
            ))
            fig.update_layout(height=max(320, 28 * len(plot)),
                              yaxis=dict(autorange="reversed"),
                              xaxis_title="capitalizare (lei)",
                              margin=dict(l=10, r=20, t=10, b=40))
            st.plotly_chart(fig, use_container_width=True)

    st.dataframe(
        par.drop(columns=["cap_num"]).sort_values("procent_stat", ascending=False),
        use_container_width=True, hide_index=True,
        column_config={
            "nume": st.column_config.TextColumn("Companie"),
            "simbol": st.column_config.TextColumn("Simbol"),
            "procent_stat": st.column_config.NumberColumn("% stat", format="%.2f"),
            "capitalizare": st.column_config.TextColumn("Capitalizare (lei)"),
        })

st.divider()
st.caption("Toate tabelele de pe această pagină provin din view-uri pre-agregate "
           "ale stratului **gold DuckDB** (`analytics/*`).")
