"""ROMEGA — Partide: subvenții de stat, evoluție anuală, rapoarte RVC."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app import data
from app.theme import (ACCENT, ACCENT_2, TEXT_DIM, apply_theme, fmt_int, fmt_lei,
                       kpi_card, page_header, party_color, sidebar_brand)

st.set_page_config(page_title="Partide · ROMEGA", page_icon="🎗️", layout="wide")
apply_theme()
sidebar_brand()
page_header("Partide", "Subvenții de stat alocate partidelor, evoluție anuală și prezență parlamentară.")

p = data.partide_df()

if p.empty:
    st.info("Nu există date despre partide.")
    st.stop()

# normalizări
p = p.copy()
p["cod"] = p["cod"].fillna("—").astype(str)
for c in ("total_subventie_lei", "nr_deputati", "nr_senatori", "nr_rapoarte_rvc"):
    if c in p.columns:
        p[c] = pd.to_numeric(p[c], errors="coerce").fillna(0)
p["nr_parlamentari"] = p["nr_deputati"] + p["nr_senatori"]

# ---------------- KPI ----------------
total_subv = float(p["total_subventie_lei"].sum())
n_parlamentare = int((p["nr_parlamentari"] > 0).sum())
top = p.sort_values("total_subventie_lei", ascending=False).iloc[0]

c1, c2, c3, c4 = st.columns(4)
kpi_card(c1, "Partide monitorizate", fmt_int(len(p)))
kpi_card(c2, "Partide parlamentare", fmt_int(n_parlamentare),
         help="Partide cu cel puțin un deputat sau senator în mandatul curent.")
kpi_card(c3, "Subvenții stat (total istoric)", fmt_lei(total_subv),
         help="Suma cumulată a subvențiilor de la bugetul de stat, toți anii disponibili.")
kpi_card(c4, "Cel mai subvenționat", f"{top['cod']} · {fmt_lei(top['total_subventie_lei'])}")

st.divider()

# ---------------- Bar: subvenții totale per partid ----------------
st.markdown("#### Subvenții totale de la stat, pe partid")
pb = p[p["total_subventie_lei"] > 0].sort_values("total_subventie_lei", ascending=True)
if pb.empty:
    st.caption("Fără subvenții înregistrate.")
else:
    fig = go.Figure(go.Bar(
        x=pb["total_subventie_lei"], y=pb["cod"], orientation="h",
        marker_color=[party_color(c) for c in pb["cod"]],
        customdata=pb["total_subventie_lei"].map(fmt_lei),
        hovertemplate="<b>%{y}</b><br>%{customdata}<extra></extra>",
        text=pb["total_subventie_lei"].map(fmt_lei), textposition="auto",
    ))
    fig.update_layout(height=max(320, 26 * len(pb)), xaxis_title="subvenție totală (lei)",
                      margin=dict(l=70, r=20, t=20, b=40))
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# ---------------- Line: evoluție subvenții pe an (top 6) ----------------
st.markdown("#### Evoluția subvențiilor pe an")
sub = data.subventii_df()
if sub.empty or "an" not in sub.columns:
    st.caption("Nu există serie temporală de subvenții.")
else:
    sub = sub.copy()
    sub["an"] = pd.to_numeric(sub["an"], errors="coerce")
    sub["suma_lei"] = pd.to_numeric(sub["suma_lei"], errors="coerce").fillna(0)
    sub = sub.dropna(subset=["an"])
    sub["partid"] = sub["partid"].fillna("—").astype(str)

    # top 6 partide după total subvenție din seria anuală
    totals = sub.groupby("partid")["suma_lei"].sum().sort_values(ascending=False)
    top6 = list(totals.head(6).index)

    sel = st.multiselect("Partide afișate", options=list(totals.index), default=top6,
                         help="Implicit: cele 6 partide cu cea mai mare subvenție cumulată.")
    if not sel:
        sel = top6

    yearly = (sub[sub["partid"].isin(sel)]
              .groupby(["partid", "an"], as_index=False)["suma_lei"].sum())

    if yearly.empty:
        st.caption("Nicio selecție validă.")
    else:
        fig2 = go.Figure()
        for partid in sel:
            d = yearly[yearly["partid"] == partid].sort_values("an")
            if d.empty:
                continue
            fig2.add_trace(go.Scatter(
                x=d["an"], y=d["suma_lei"], mode="lines+markers", name=partid,
                line=dict(color=party_color(partid), width=2.5),
                customdata=d["suma_lei"].map(fmt_lei),
                hovertemplate=f"<b>{partid}</b> · %{{x}}<br>%{{customdata}}<extra></extra>",
            ))
        fig2.update_layout(height=420, xaxis_title="an", yaxis_title="subvenție (lei)",
                           hovermode="x unified", legend_title_text="partid",
                           margin=dict(l=60, r=20, t=20, b=40))
        fig2.update_xaxes(dtick=2)
        st.plotly_chart(fig2, use_container_width=True)

st.divider()

# ---------------- Tabel partide ----------------
st.markdown("#### Detaliu partide")
tbl = (p[["cod", "total_subventie_lei", "nr_deputati", "nr_senatori", "nr_rapoarte_rvc"]]
       .sort_values("total_subventie_lei", ascending=False)
       .rename(columns={
           "cod": "Partid", "total_subventie_lei": "Subvenție totală (lei)",
           "nr_deputati": "Deputați", "nr_senatori": "Senatori",
           "nr_rapoarte_rvc": "Rapoarte RVC",
       }))
st.dataframe(
    tbl, use_container_width=True, hide_index=True,
    column_config={
        "Subvenție totală (lei)": st.column_config.NumberColumn(format="%.0f"),
        "Deputați": st.column_config.NumberColumn(format="%d"),
        "Senatori": st.column_config.NumberColumn(format="%d"),
        "Rapoarte RVC": st.column_config.NumberColumn(
            format="%d", help="Rapoarte de venituri și cheltuieli depuse la AEP."),
    },
)
st.caption("Surse: subvenții de la bugetul de stat (AEP) și rapoartele de venituri/cheltuieli ale partidelor. "
           "Numărul de deputați/senatori reflectă mandatul curent.")
