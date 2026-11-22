"""Sinteză — cifrele-cheie și conflictele confirmate (prima pagină a dashboard-ului)."""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

import sys as _sys, pathlib as _pl  # bootstrap: import 'app' fără PYTHONPATH (rulare directă/deploy)
for _a in _pl.Path(__file__).resolve().parents:
    if (_a / 'app').is_dir():
        _sys.path.insert(0, str(_a)); break

from app import data
from app.theme import tabel
from app.theme import (ACCENT, ACCENT_2, apply_theme, data_freshness, fmt_int, kpi_card,
                       page_header, despre, sidebar_brand)

st.set_page_config(page_title="Sinteză · SOLOMONAR", layout="wide",
                   initial_sidebar_state="expanded")
apply_theme()
sidebar_brand()

page_header("Cine conduce statul și pe unde trec banii publici",
            "Declarații de avere, conducerile companiilor de stat, contracte publice, partide și "
            "bugete, legate între ele din surse oficiale.")
despre(
    sursa="Declarații de avere și de interese publicate de instituții și companii de stat pe site-urile "
          "proprii și de deputați pe cdep.ro; reprezentanții legali din dump-ul ONRC și contractele din "
          "exportul SICAP, ambele de pe data.gov.ro. Lista companiilor de stat vine din raportul anual "
          "AMEPIP și de pe companiidestat.ro, acționariatul de pe bvb.ro, comunicatele de pe dna.ro.",
    calcul="Cifrele de sus numără înregistrările din setul publicat. Graficul pe sectoare adună, pentru "
           "companiile de stat din fiecare sector, valoarea contractelor SICAP asociate CUI-ului lor și "
           "arată primele 8 sectoare. Graficul BVB arată, pentru companiile listate, procentul deținut de "
           "acționarii recunoscuți ca stat (Statul Român, ministere, Fondul Proprietatea, consilii "
           "județene sau locale, primării).",
    legaturi="Tabelul de conflicte cuprinde persoanele care apar în ONRC ca reprezentant legal al unei "
             "firme cu contracte publice, firmă trecută și în propria lor declarație de interese "
             "(cuvintele distinctive din denumire apar printre entitățile declarate). Se afișează "
             "primele 10 persoane, cu o singură firmă fiecare.",
    limite="Valorile contractelor sunt estimări nete: fiecare contract e numărat o dată, iar la cele cu "
           "mai mulți semnatari suma se împarte egal (exportul SICAP nu dă cota fiecăruia). Legătura persoană-firmă din "
           "ONRC se face după nume, fără CNP. Dacă fișierul unei surse lipsește la o actualizare, cifra "
           "ei rămâne la valoarea anterioară.",
)

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
    st.markdown("#### Conflicte trecute în propria declarație de interese")
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
        tabel(df, use_container_width=True, hide_index=True,
                     column_config={"contracte_lei": st.column_config.NumberColumn(format="%.0f")})
    st.caption("Sursă defensabilă: firma apare în declarația de interese a persoanei. "
               "Restul legăturilor nume-bazate = candidați (vezi pagina Follow-the-money).")

# top sectoare companii (din DuckDB analytics)
with col_r:
    st.markdown("#### Contracte ale companiilor de stat, pe sector (valoare netă estimată)")
    sec = data.analytics("sumar_sector")
    if not sec.empty and "contracte_totale" in sec.columns:
        sec = sec.dropna(subset=["contracte_totale"]).head(8)
        fig = go.Figure(go.Bar(x=sec["contracte_totale"], y=sec["sector"], orientation="h",
                               marker_color=ACCENT))
        fig.update_layout(height=320, yaxis=dict(autorange="reversed"),
                          xaxis_title="contracte (lei)")
        st.plotly_chart(fig, width="stretch")

st.divider()
st.markdown("#### Participații de stat (BVB) — companiile mari listate")
ps = data.analytics("participatii_stat")
if not ps.empty:
    fig = go.Figure(go.Bar(x=ps["nume"].head(12), y=ps["procent_stat"].head(12), marker_color=ACCENT_2))
    fig.update_layout(height=300, yaxis_title="% deținut de stat", xaxis_tickangle=-30)
    st.plotly_chart(fig, width="stretch")

st.caption(f"{data_freshness()}. Paginile din bara laterală intră în detaliu pe fiecare temă.")
