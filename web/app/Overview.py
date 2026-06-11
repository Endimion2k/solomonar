"""ROMEGA Insights — pagina principală (Overview). Rulează: streamlit run web/app/Overview.py"""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from app import data
from app.theme import (ACCENT, ACCENT_2, SUCCESS, TEXT_DIM, apply_theme, fmt_int,
                       fmt_lei, kpi_card, page_header, sidebar_brand)

st.set_page_config(page_title="ROMEGA Insights", page_icon="🏛️", layout="wide",
                   initial_sidebar_state="expanded")
apply_theme()
sidebar_brand()

page_header("ROMEGA — transparența aparatului de stat",
            "Declarații de avere · companii de stat · achiziții · partide · bugete · graf "
            "follow-the-money. Date publice agregate și interconectate.")

s = data.stats()
d = s.get("declaratii", {})
g = s.get("gold", {})
c1, c2, c3, c4 = st.columns(4)
kpi_card(c1, "Declarații avere+interese", fmt_int(d.get("total")))
kpi_card(c2, "Persoane în graf", fmt_int(g.get("persoane_canonice")))
kpi_card(c3, "Companii de stat", fmt_int((s.get("companii_stat") or {}).get("total") or len(data.companii_df())))
kpi_card(c4, "Firme cu contracte", fmt_int((s.get("achizitii") or {}).get("firme_castigatoare")))

c1, c2, c3, c4 = st.columns(4)
kpi_card(c1, "CV-uri", fmt_int((s.get("cv_uri") or {}).get("total")))
kpi_card(c2, "DNA comunicate", fmt_int((s.get("audit") or {}).get("dna_comunicate")))
kpi_card(c3, "Partide", fmt_int((s.get("partide") or {}).get("total")))
kpi_card(c4, "Bugete UAT", fmt_int((s.get("bugete") or {}).get("uat_inreg")))

st.divider()
col_l, col_r = st.columns(2)

# follow-the-money confirmate
with col_l:
    st.markdown("#### ⚠️ Conflicte confirmate (firmă cu contracte în propria declarație)")
    fm = data.follow_money()
    conf = fm.get("confirmate", [])[:10]
    if conf:
        rows = []
        for r in conf:
            firme = r.get("firme_contracte_autodeclarate", [])
            for f in firme[:1]:
                rows.append({"persoană": (r.get("nume_key") or "").title(),
                             "firmă": f.get("nume"), "contracte_lei": f.get("total_ron")})
        import pandas as pd
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True,
                     column_config={"contracte_lei": st.column_config.NumberColumn(format="%.0f")})
    st.caption("Sursă defensabilă: firma apare în declarația de interese a persoanei. "
               "Restul legăturilor nume-bazate = candidați (vezi pagina Follow-the-money).")

# top sectoare companii (din DuckDB analytics)
with col_r:
    st.markdown("#### Companii de stat pe sector (contracte)")
    sec = data.analytics("sumar_sector")
    if not sec.empty and "contracte_totale" in sec.columns:
        sec = sec.dropna(subset=["contracte_totale"]).head(8)
        fig = go.Figure(go.Bar(x=sec["contracte_totale"], y=sec["sector"], orientation="h",
                               marker_color=ACCENT))
        fig.update_layout(height=320, yaxis=dict(autorange="reversed"),
                          xaxis_title="contracte (lei)")
        st.plotly_chart(fig, use_container_width=True)

st.divider()
st.markdown("#### Participații de stat (BVB) — companiile mari listate")
ps = data.analytics("participatii_stat")
if not ps.empty:
    fig = go.Figure(go.Bar(x=ps["nume"].head(12), y=ps["procent_stat"].head(12), marker_color=ACCENT_2))
    fig.update_layout(height=300, yaxis_title="% deținut de stat", xaxis_tickangle=-30)
    st.plotly_chart(fig, use_container_width=True)

st.caption(f"Date din `{data.DATA}` · Folosește paginile din bara laterală pentru explorare detaliată.")
