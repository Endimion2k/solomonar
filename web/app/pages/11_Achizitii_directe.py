"""Achiziții directe — cumpărările directe SICAP 2007-2025, agregate pe furnizor (SOLOMONAR)."""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from app import data
from app.theme import (ACCENT, ACCENT_2, TEXT_DIM, apply_theme, fmt_int, fmt_lei,
                       kpi_card, page_header, sidebar_brand)

st.set_page_config(page_title="Achiziții directe · SOLOMONAR", page_icon="🧾", layout="wide")
apply_theme()
sidebar_brand()
page_header("Achiziții directe — cumpărări directe SICAP",
            "21,9 milioane de cumpărări directe (sub pragul de licitație) 2007-2025, agregate pe "
            "furnizor. Al doilea canal de bani publici, pe lângă contractele de achiziție publică.")

df = data.achizitii_directe_df()
meta = data.achizitii_directe_meta()

if df.empty:
    st.warning("Nu există date de achiziții directe disponibile.")
    st.stop()

# ---------------- KPI ----------------
c1, c2, c3, c4 = st.columns(4)
kpi_card(c1, "Furnizori (total)", fmt_int(meta["total_furnizori"]))
kpi_card(c2, "Achiziții directe", fmt_int(meta["total_achizitii"]))
kpi_card(c3, "Valoare totală", fmt_lei(meta["valoare_totala_ron"]))
medie = meta["valoare_totala_ron"] / max(meta["total_achizitii"], 1)
kpi_card(c4, "Medie / achiziție", fmt_lei(medie))
st.caption(f"Sursă: {meta['sursa']}. Afișați primii {fmt_int(len(df))} furnizori după valoare. "
           "Valorile per achiziție sunt plafonate la 2M lei (sanitizare outlieri/garbage).")

# ---------------- top furnizori ----------------
st.subheader("Top 20 furnizori după valoarea totală")
top = df.nlargest(20, "total_ron").iloc[::-1]
fig = go.Figure(go.Bar(
    x=top["total_ron"], y=top["nume"].str.slice(0, 40), orientation="h",
    marker_color=ACCENT,
    customdata=top["nr"],
    hovertemplate="%{y}<br>%{x:,.0f} lei · %{customdata:,} achiziții<extra></extra>"))
fig.update_layout(height=560, margin=dict(l=10, r=10, t=10, b=10),
                  xaxis_title="lei (total 2007-2025)", yaxis_title=None)
st.plotly_chart(fig, use_container_width=True)

# ---------------- filtre + tabel ----------------
st.subheader("Caută furnizori")
fc1, fc2, fc3 = st.columns([2, 1, 1])
q = fc1.text_input("Nume furnizor", placeholder="ex. Dedeman, Selgros…")
min_nr = fc2.number_input("Min. achiziții", min_value=0, value=0, step=100)
min_val = fc3.number_input("Min. valoare (lei)", min_value=0, value=0, step=100_000)

f = df
if q.strip():
    f = f[f["nume"].str.contains(q.strip(), case=False, na=False, regex=False)]
if min_nr:
    f = f[f["nr"] >= min_nr]
if min_val:
    f = f[f["total_ron"] >= min_val]
f = f.sort_values("total_ron", ascending=False)
st.caption(f"{fmt_int(len(f))} furnizori — afișați primii 500.")

show = f.head(500)[["nume", "cui", "total_ron", "nr", "ani_activi", "top_autoritati"]]
st.dataframe(
    show, use_container_width=True, hide_index=True, height=480,
    column_config={
        "nume": st.column_config.TextColumn("Furnizor"),
        "cui": st.column_config.TextColumn("CUI"),
        "total_ron": st.column_config.NumberColumn("Total (lei)", format="%.0f"),
        "nr": st.column_config.NumberColumn("Achiziții", format="%d"),
        "ani_activi": st.column_config.TextColumn("Ani activi"),
        "top_autoritati": st.column_config.TextColumn("Top autorități contractante"),
    })

# ---------------- detaliu furnizor ----------------
if not f.empty:
    st.subheader("Fișă furnizor")
    sel = st.selectbox("Alege furnizor", f.head(500)["nume"].tolist())
    r = f[f["nume"] == sel].iloc[0]
    d1, d2, d3, d4 = st.columns(4)
    kpi_card(d1, "Total achiziții directe", fmt_lei(r["total_ron"]))
    kpi_card(d2, "Număr achiziții", fmt_int(int(r["nr"])))
    kpi_card(d3, "Medie / achiziție", fmt_lei(r["total_ron"] / max(int(r["nr"]), 1)))
    kpi_card(d4, "CUI", str(r["cui"]))
    if r["top_autoritati"]:
        st.markdown(f"**Top autorități contractante:** {r['top_autoritati']}")
    if r["ani_activi"]:
        st.markdown(f"**Ani activi:** {r['ani_activi']}")
    # legătura cu graful: e firmă cu administratori cunoscuți?
    comp = data.companii_df()
    hit = comp[comp["cui"].astype(str) == str(r["cui"])]
    if not hit.empty:
        st.info("Această firmă apare și în registrul companiilor SOLOMONAR (administratori cunoscuți) — "
                "vezi pagina Companii / Persoane pentru cine o conduce.")

st.caption("⚠️ Achizițiile directe sunt cumpărări legale sub pragul de licitație. Volumul mare la un "
           "furnizor NU implică nereguli — este context pentru analize (concentrare, dependență de un "
           "client public, fragmentare suspectă a achizițiilor).")
