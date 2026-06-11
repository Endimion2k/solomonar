"""Achiziții publice — firmele câștigătoare de contracte cu statul (ROMEGA)."""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from app import data
from app.theme import (ACCENT, ACCENT_2, TEXT_DIM, apply_theme, fmt_int, fmt_lei,
                       kpi_card, page_header, sidebar_brand)

st.set_page_config(page_title="Achiziții · ROMEGA", page_icon="📑", layout="wide")
apply_theme()
sidebar_brand()
page_header("Achiziții publice — firme câștigătoare",
            "Firmele care au câștigat contracte cu statul, valoarea totală și numărul de contracte. "
            "Date agregate din achizițiile publice.")

df = data.contracte_df()

if df.empty:
    st.warning("Nu există date de achiziții disponibile.")
    st.stop()

# ---------------- KPI ----------------
total_lei = float(df["total_ron"].fillna(0).sum())
total_contracte = int(df["nr_contracte"].fillna(0).sum())
c1, c2, c3, c4 = st.columns(4)
kpi_card(c1, "Firme câștigătoare", fmt_int(len(df)))
kpi_card(c2, "Valoare totală contracte", fmt_lei(total_lei))
kpi_card(c3, "Număr total contracte", fmt_int(total_contracte))
kpi_card(c4, "Contract mediu / firmă", fmt_lei(total_lei / len(df)) if len(df) else "—")

st.divider()

# ---------------- Top 20 firme (bar) ----------------
st.markdown("#### Top 20 firme după valoarea contractelor")
top = df.dropna(subset=["total_ron"]).sort_values("total_ron", ascending=False).head(20)
if not top.empty:
    fig = go.Figure(go.Bar(
        x=top["total_ron"], y=top["nume"], orientation="h",
        marker_color=ACCENT,
        customdata=top["nr_contracte"],
        hovertemplate="<b>%{y}</b><br>Total: %{x:,.0f} lei<br>"
                      "Contracte: %{customdata}<extra></extra>",
    ))
    fig.update_layout(height=560, yaxis=dict(autorange="reversed"),
                      xaxis_title="valoare contracte (lei)", margin=dict(l=10, r=20, t=10, b=40))
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Valorile mari pot include contracte-cadru multianuale; vezi numărul de contracte la hover.")

st.divider()

# ---------------- Tabel filtrabil ----------------
st.markdown("#### Caută o firmă")
fcol1, fcol2 = st.columns([3, 1])
q = fcol1.text_input("Nume firmă (sau fragment)", placeholder="ex: construct, electrica, drumuri…",
                     label_visibility="collapsed")
min_ctr = fcol2.number_input("Min. contracte", min_value=0, value=0, step=1)

view = df.copy()
if q:
    view = view[view["nume"].fillna("").str.contains(q, case=False, regex=False)]
if min_ctr:
    view = view[view["nr_contracte"].fillna(0) >= min_ctr]
view = view.sort_values("total_ron", ascending=False, na_position="last")

st.caption(f"{fmt_int(len(view))} firme afișate "
           f"· total filtrat: {fmt_lei(float(view['total_ron'].fillna(0).sum()))}")

if view.empty:
    st.info("Niciun rezultat pentru filtrele curente.")
else:
    show = view[["nume", "cui", "total_ron", "nr_contracte"]].head(500).copy()
    show["ani"] = view["ani"].head(500).apply(
        lambda a: ", ".join(str(x) for x in sorted(a)) if isinstance(a, list) else "")
    st.dataframe(
        show, use_container_width=True, hide_index=True,
        column_config={
            "nume": st.column_config.TextColumn("Firmă", width="large"),
            "cui": st.column_config.NumberColumn("CUI", format="%d"),
            "total_ron": st.column_config.NumberColumn("Total contracte (lei)", format="%.0f"),
            "nr_contracte": st.column_config.NumberColumn("Nr. contracte", format="%d"),
            "ani": st.column_config.TextColumn("Ani"),
        },
    )
    if len(view) > 500:
        st.caption("Se afișează primele 500 de rânduri. Rafinează căutarea pentru a vedea mai mult.")

st.divider()

# ---------------- Contracte pe sector (analytics) ----------------
st.markdown("#### Contracte pe sector (companii de stat)")
sec = data.analytics("sumar_sector")
if sec.empty or "contracte_totale" not in sec.columns:
    st.info("Nu există date agregate pe sector.")
else:
    sec = sec.dropna(subset=["contracte_totale"]).sort_values("contracte_totale", ascending=False)
    fig = go.Figure(go.Bar(
        x=sec["contracte_totale"], y=sec["sector"], orientation="h",
        marker_color=ACCENT_2,
        customdata=sec["n_companii"] if "n_companii" in sec.columns else None,
        hovertemplate="<b>%{y}</b><br>Contracte: %{x:,.0f} lei"
                      + ("<br>Companii: %{customdata}" if "n_companii" in sec.columns else "")
                      + "<extra></extra>",
    ))
    fig.update_layout(height=380, yaxis=dict(autorange="reversed"),
                      xaxis_title="contracte (lei)", margin=dict(l=10, r=20, t=10, b=40))
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Sursă: vederi analitice DuckDB (companii de stat agregate pe sector economic).")
