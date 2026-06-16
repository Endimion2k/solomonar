"""SOLOMONAR — Bugete. Bugete locale (UAT), executia bugetului general consolidat,
agregare pe judete. Date publice: mfinante.gov.ro + analytics DuckDB."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import sys as _sys, pathlib as _pl  # bootstrap: import 'app' fără PYTHONPATH (rulare directă/deploy)
for _a in _pl.Path(__file__).resolve().parents:
    if (_a / 'app').is_dir():
        _sys.path.insert(0, str(_a)); break

from app import data
from app.theme import (ACCENT, ACCENT_2, DANGER, SUCCESS, TEXT_DIM, WARNING,
                       apply_theme, fmt_int, fmt_lei, kpi_card, page_header,
                       sidebar_brand)

st.set_page_config(page_title="Bugete · SOLOMONAR", page_icon="💶", layout="wide")
apply_theme()
sidebar_brand()
page_header("Bugete",
            "Bugete locale (UAT) · execuția bugetului general consolidat · agregare pe județe.")

# ---------------------------------------------------------------- date
uat = data.bugete_uat_df()
bgc = data.bgc_df()
jud = data.analytics("sumar_judet")

# ============================================================ KPI bugete UAT
if uat.empty:
    st.warning("Nu există date despre bugetele UAT.")
else:
    ven_total = uat["venituri_lei"].sum()
    chelt_total = uat["cheltuieli_lei"].sum()
    sold_total = ven_total - chelt_total
    c1, c2, c3, c4 = st.columns(4)
    kpi_card(c1, "UAT înregistrate", fmt_int(len(uat)))
    kpi_card(c2, "Venituri totale UAT", fmt_lei(ven_total))
    kpi_card(c3, "Cheltuieli totale UAT", fmt_lei(chelt_total))
    kpi_card(c4, "Sold agregat", fmt_lei(sold_total),
             help="Venituri minus cheltuieli, însumat pe toate UAT-urile.")

    st.divider()

    # -------------------------------------------------- filtre
    f1, f2, f3 = st.columns([2, 2, 3])
    judete = ["Toate"] + sorted(uat["judet"].dropna().unique().tolist())
    sel_jud = f1.selectbox("Județ", judete, index=0)
    tipuri = ["Toate"] + sorted(uat["tip"].dropna().unique().tolist())
    sel_tip = f2.selectbox("Tip UAT", tipuri, index=0)
    q = f3.text_input("Caută UAT", placeholder="ex: COMUNA, MUNICIPIUL...")

    df = uat.copy()
    if sel_jud != "Toate":
        df = df[df["judet"] == sel_jud]
    if sel_tip != "Toate":
        df = df[df["tip"] == sel_tip]
    if q.strip():
        df = df[df["uat"].str.contains(q.strip(), case=False, na=False)]

    df = df.assign(sold_lei=df["venituri_lei"] - df["cheltuieli_lei"])

    # -------------------------------------------------- top 20 UAT dupa venituri
    st.markdown("#### Top 20 UAT după venituri")
    if df.empty:
        st.info("Niciun UAT pentru filtrele selectate.")
    else:
        top = df.sort_values("venituri_lei", ascending=False).head(20)
        fig = go.Figure()
        fig.add_trace(go.Bar(
            y=top["uat"], x=top["venituri_lei"], orientation="h",
            name="Venituri", marker_color=ACCENT,
            hovertemplate="%{y}<br>Venituri: %{x:,.0f} lei<extra></extra>"))
        fig.add_trace(go.Bar(
            y=top["uat"], x=top["cheltuieli_lei"], orientation="h",
            name="Cheltuieli", marker_color=ACCENT_2,
            hovertemplate="%{y}<br>Cheltuieli: %{x:,.0f} lei<extra></extra>"))
        fig.update_layout(
            height=620, barmode="group", yaxis=dict(autorange="reversed"),
            xaxis_title="lei", legend=dict(orientation="h", y=1.05, x=0),
            margin=dict(l=10, r=20, t=30, b=40))
        st.plotly_chart(fig, use_container_width=True)

        # -------------------------------------------------- tabel UAT
        st.markdown(f"#### Detaliu UAT — {fmt_int(len(df))} rezultate")
        tbl = df[["uat", "judet", "tip", "an", "venituri_lei",
                  "cheltuieli_lei", "sold_lei"]].sort_values(
            "venituri_lei", ascending=False)
        st.dataframe(
            tbl, use_container_width=True, hide_index=True, height=440,
            column_config={
                "uat": "UAT",
                "judet": "Județ",
                "tip": "Tip",
                "an": st.column_config.NumberColumn("An", format="%d"),
                "venituri_lei": st.column_config.NumberColumn(
                    "Venituri (lei)", format="%.0f"),
                "cheltuieli_lei": st.column_config.NumberColumn(
                    "Cheltuieli (lei)", format="%.0f"),
                "sold_lei": st.column_config.NumberColumn(
                    "Sold (lei)", format="%.0f"),
            })

st.divider()

# ============================================================ BGC lunar
st.markdown("#### Execuția bugetului general consolidat (lunar, cumulat)")
if bgc.empty:
    st.info("Nu există date despre execuția bugetară.")
else:
    g = bgc.sort_values(["an", "luna"]).copy()
    g["eticheta"] = g["luna_nume"].str.capitalize() + " " + g["an"].astype(str)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=g["eticheta"], y=g["venituri_mil_lei"], name="Venituri",
        mode="lines+markers", line=dict(color=SUCCESS, width=2.5),
        hovertemplate="%{x}<br>Venituri: %{y:,.0f} mil lei<extra></extra>"))
    fig.add_trace(go.Scatter(
        x=g["eticheta"], y=g["cheltuieli_mil_lei"], name="Cheltuieli",
        mode="lines+markers", line=dict(color=DANGER, width=2.5),
        hovertemplate="%{x}<br>Cheltuieli: %{y:,.0f} mil lei<extra></extra>"))
    fig.update_layout(
        height=380, xaxis_tickangle=-40, yaxis_title="mil lei",
        legend=dict(orientation="h", y=1.08, x=0),
        margin=dict(l=40, r=20, t=30, b=80))
    st.plotly_chart(fig, use_container_width=True)

    # sold lunar (deficit) ca bare
    st.markdown("##### Sold lunar (deficit/excedent cumulat)")
    colors = [SUCCESS if v >= 0 else DANGER for v in g["sold"]]
    figs = go.Figure(go.Bar(
        x=g["eticheta"], y=g["sold"], marker_color=colors,
        hovertemplate="%{x}<br>Sold: %{y:,.0f} mil lei<extra></extra>"))
    figs.update_layout(
        height=300, xaxis_tickangle=-40, yaxis_title="sold (mil lei)",
        margin=dict(l=40, r=20, t=20, b=80))
    st.plotly_chart(figs, use_container_width=True)

    # tabel sintetic BGC
    show = g[["perioada", "an", "luna_nume", "venituri_mil_lei",
              "cheltuieli_mil_lei", "sold", "sold_pct_pib"]].iloc[::-1]
    st.dataframe(
        show, use_container_width=True, hide_index=True, height=300,
        column_config={
            "perioada": "Perioadă",
            "an": st.column_config.NumberColumn("An", format="%d"),
            "luna_nume": "Lună",
            "venituri_mil_lei": st.column_config.NumberColumn(
                "Venituri (mil lei)", format="%.0f"),
            "cheltuieli_mil_lei": st.column_config.NumberColumn(
                "Cheltuieli (mil lei)", format="%.0f"),
            "sold": st.column_config.NumberColumn("Sold (mil lei)", format="%.0f"),
            "sold_pct_pib": st.column_config.NumberColumn(
                "Sold (% PIB)", format="%.2f%%"),
        })

st.divider()

# ============================================================ judete (analytics)
st.markdown("#### Companii de stat pe județ")
st.caption("Agregare din analytics DuckDB — companii cu participație de stat, "
           "cifra de afaceri și salariați pe județ.")
if jud.empty:
    st.info("Nu există date agregate pe județe.")
else:
    jc = jud.copy()
    metric = st.radio(
        "Metrică", ["cifra_afaceri", "n_companii", "salariati"],
        horizontal=True,
        format_func=lambda m: {"cifra_afaceri": "Cifră de afaceri",
                               "n_companii": "Nr. companii",
                               "salariati": "Salariați"}[m])
    top_j = jc.sort_values(metric, ascending=False).head(20)
    fig = go.Figure(go.Bar(
        x=top_j["judet"], y=top_j[metric], marker_color=WARNING,
        hovertemplate="%{x}<br>%{y:,.0f}<extra></extra>"))
    fig.update_layout(height=360, xaxis_tickangle=-40,
                      margin=dict(l=40, r=20, t=20, b=90))
    st.plotly_chart(fig, use_container_width=True)

    st.dataframe(
        jc.sort_values("cifra_afaceri", ascending=False),
        use_container_width=True, hide_index=True, height=360,
        column_config={
            "judet": "Județ",
            "n_companii": st.column_config.NumberColumn("Nr. companii", format="%d"),
            "cifra_afaceri": st.column_config.NumberColumn(
                "Cifră de afaceri (lei)", format="%.0f"),
            "salariati": st.column_config.NumberColumn("Salariați", format="%d"),
        })

st.caption(f"Date din `{data.DATA}` · bugete UAT și BGC: mfinante.gov.ro · "
           "agregări companii: analytics DuckDB.")
