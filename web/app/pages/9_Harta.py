"""SOLOMONAR — Harta companiilor de stat pe județe (distribuție geografică)."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app import data
from app.theme import (ACCENT, ACCENT_2, TEXT_DIM, apply_theme, fmt_int, fmt_lei,
                       kpi_card, page_header, sidebar_brand)

st.set_page_config(page_title="Harta · SOLOMONAR", page_icon="🗺️", layout="wide")
apply_theme()
sidebar_brand()

page_header("Harta companiilor de stat",
            "Distribuția companiilor cu participare de stat pe județe — număr de "
            "companii, angajați și cifra de afaceri agregată.")

df = data.analytics("sumar_judet")

if df.empty:
    st.info("Nu există date de distribuție pe județe.")
    st.stop()

# normalizare numerică (cifra_afaceri poate veni ca text/None)
df = df.copy()
for col in ("n_companii", "salariati", "cifra_afaceri"):
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")
df["judet"] = df["judet"].fillna("—").astype(str)

has_cifra = "cifra_afaceri" in df.columns and df["cifra_afaceri"].notna().any()

# ---- KPI sumar ----
c1, c2, c3, c4 = st.columns(4)
kpi_card(c1, "Județe acoperite", fmt_int(df["judet"].nunique()))
kpi_card(c2, "Total companii", fmt_int(df["n_companii"].sum()))
kpi_card(c3, "Total angajați", fmt_int(df["salariati"].sum()))
top_row = df.sort_values("n_companii", ascending=False).iloc[0]
kpi_card(c4, "Județ lider", f"{top_row['judet']} ({fmt_int(top_row['n_companii'])})")

st.divider()

# ---- controale ----
ctrl1, ctrl2 = st.columns([1, 1])
metric_options = {
    "Număr companii": "n_companii",
    "Angajați": "salariati",
}
if has_cifra:
    metric_options["Cifra de afaceri (lei)"] = "cifra_afaceri"

with ctrl1:
    metric_label = st.selectbox("Sortează / afișează după", list(metric_options.keys()))
with ctrl2:
    top_n = st.slider("Câte județe în grafic", min_value=5,
                      max_value=int(min(42, len(df))), value=min(20, len(df)))

metric_col = metric_options[metric_label]
plot_df = df.dropna(subset=[metric_col]).sort_values(metric_col, ascending=False).head(top_n)

# ---- bar chart orizontal ----
st.markdown(f"#### Top {len(plot_df)} județe după {metric_label.lower()}")
if plot_df.empty:
    st.info("Nu există valori pentru metrica selectată.")
else:
    is_lei = metric_col in ("cifra_afaceri",)
    if is_lei:
        text = [fmt_lei(v) for v in plot_df[metric_col]]
    else:
        text = [fmt_int(v) for v in plot_df[metric_col]]
    fig = go.Figure(go.Bar(
        x=plot_df[metric_col], y=plot_df["judet"], orientation="h",
        marker_color=ACCENT, text=text, textposition="auto",
        hovertemplate="%{y}<br>%{x:,.0f}<extra></extra>",
    ))
    fig.update_layout(
        height=max(360, 26 * len(plot_df)),
        yaxis=dict(autorange="reversed"),
        xaxis_title=metric_label, margin=dict(l=10, r=20, t=10, b=40),
    )
    st.plotly_chart(fig, use_container_width=True)

st.caption("Notă: nu folosim hartă choropleth (lipsesc granițele GeoJSON ale județelor) — "
           "reprezentarea este un clasament orizontal.")

st.divider()

# ---- comparație companii vs angajați (scatter) ----
st.markdown("#### Companii vs. angajați pe județ")
sc = df.dropna(subset=["n_companii", "salariati"])
if not sc.empty:
    fig2 = go.Figure(go.Scatter(
        x=sc["n_companii"], y=sc["salariati"], mode="markers+text",
        text=sc["judet"], textposition="top center",
        textfont=dict(size=9, color=TEXT_DIM),
        marker=dict(size=11, color=ACCENT_2, opacity=0.8,
                    line=dict(width=1, color="#0b0d12")),
        hovertemplate="%{text}<br>companii: %{x}<br>angajați: %{y:,.0f}<extra></extra>",
    ))
    fig2.update_layout(height=460, xaxis_title="număr companii",
                       yaxis_title="număr angajați")
    st.plotly_chart(fig2, use_container_width=True)

st.divider()

# ---- tabel complet ----
st.markdown("#### Tabel complet pe județe")
q = st.text_input("Caută județ", "").strip().lower()
table = df.sort_values("n_companii", ascending=False)
if q:
    table = table[table["judet"].str.lower().str.contains(q, na=False)]

col_cfg = {
    "judet": st.column_config.TextColumn("Județ"),
    "n_companii": st.column_config.NumberColumn("Companii", format="%d"),
    "salariati": st.column_config.NumberColumn("Angajați", format="%d"),
}
if "cifra_afaceri" in table.columns:
    col_cfg["cifra_afaceri"] = st.column_config.NumberColumn("Cifra afaceri (lei)", format="%.0f")

st.dataframe(table, use_container_width=True, hide_index=True, column_config=col_cfg)
st.caption(f"{len(table)} județe afișate · sursă: stratul gold DuckDB (`analytics/sumar_judet`).")
