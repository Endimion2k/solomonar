"""ROMEGA · Comisii & Legislativ — comisiile Senatului (23) + inițiatori PLx (1.852).

Comisii Senat: selectează o comisie -> membri + rol. Legislativ: distribuția inițiativelor
(guvern vs. parlamentar) și un tabel filtrabil al proiectelor PLx.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app import data
from app.theme import (ACCENT, ACCENT_2, SUCCESS, TEXT_DIM, WARNING, apply_theme,
                       fmt_int, kpi_card, page_header, sidebar_brand)

st.set_page_config(page_title="Comisii & Legislativ · ROMEGA", page_icon="🏛️", layout="wide")
apply_theme()
sidebar_brand()

page_header("Comisii & Legislativ",
            "Comisiile permanente ale Senatului și componența lor · inițiatorii proiectelor "
            "legislative (PLx). Date publice, agregate.")

# ====================================================================
# SECȚIUNEA 1 — Comisiile Senatului
# ====================================================================
st.markdown("### Comisiile Senatului")

comisii = data.comisii_senat()

if not comisii:
    st.info("Nu există comisii în setul de date.")
else:
    total_membri = sum(int(c.get("n_membri") or len(c.get("membri") or [])) for c in comisii)
    c1, c2, c3 = st.columns(3)
    kpi_card(c1, "Comisii Senat", fmt_int(len(comisii)))
    kpi_card(c2, "Mandate în comisii", fmt_int(total_membri))
    medie = total_membri / len(comisii) if comisii else 0
    kpi_card(c3, "Membri / comisie (medie)", f"{medie:.1f}")

    nume_comisii = sorted(c.get("nume", "(fără nume)") for c in comisii)
    sel = st.selectbox("Alege o comisie", nume_comisii)
    comisia = next((c for c in comisii if c.get("nume") == sel), None)

    if comisia:
        membri = comisia.get("membri") or []
        st.markdown(f"**{sel}** — {fmt_int(len(membri))} membri")

        if membri:
            mdf = pd.DataFrame(membri)
            for col in ("nume", "rol", "parlamentar_id"):
                if col not in mdf.columns:
                    mdf[col] = ""
            mdf["rol"] = mdf["rol"].fillna("Membru").replace("", "Membru")

            # ordine birou comisie întâi
            ord_rol = {"Președinte": 0, "Preşedinte": 0, "Vicepreședinte": 1,
                       "Vicepreşedinte": 1, "Secretar": 2, "Membru": 3}
            mdf["_o"] = mdf["rol"].map(lambda r: ord_rol.get(r, 9))
            mdf = mdf.sort_values(["_o", "nume"]).drop(columns="_o")

            col_t, col_g = st.columns([3, 2])
            with col_t:
                show = mdf[["nume", "rol"]].rename(columns={"nume": "membru", "rol": "rol"})
                st.dataframe(show, use_container_width=True, hide_index=True,
                             column_config={"membru": st.column_config.TextColumn(width="large")})
            with col_g:
                rol_cnt = mdf["rol"].value_counts().reset_index()
                rol_cnt.columns = ["rol", "n"]
                fig = go.Figure(go.Bar(x=rol_cnt["n"], y=rol_cnt["rol"], orientation="h",
                                       marker_color=ACCENT_2, text=rol_cnt["n"],
                                       textposition="outside"))
                fig.update_layout(height=240, yaxis=dict(autorange="reversed"),
                                  xaxis_title="număr membri", title="Roluri în comisie")
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.caption("Comisia nu are membri înregistrați în setul de date.")

    # privire de ansamblu peste toate comisiile
    st.markdown("#### Mărimea comisiilor")
    ov = pd.DataFrame([{"comisie": c.get("nume", ""),
                        "membri": int(c.get("n_membri") or len(c.get("membri") or []))}
                       for c in comisii]).sort_values("membri", ascending=True)
    fig = go.Figure(go.Bar(x=ov["membri"], y=ov["comisie"], orientation="h",
                           marker_color=ACCENT))
    fig.update_layout(height=max(320, 22 * len(ov)), xaxis_title="număr membri",
                      margin=dict(l=10))
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# ====================================================================
# SECȚIUNEA 2 — Inițiatori legislativi (PLx)
# ====================================================================
st.markdown("### Inițiative legislative (PLx)")

plx = data.plx_initiatori_df()

if plx.empty:
    st.info("Nu există date PLx în setul de date.")
else:
    plx = plx.copy()
    for col in ("titlu", "idp"):
        if col not in plx.columns:
            plx[col] = ""
        plx[col] = plx[col].fillna("").astype(str)
    plx["guvern"] = plx.get("guvern", False).fillna(False).astype(bool)
    plx["n_initiatori"] = pd.to_numeric(plx.get("n_initiatori"), errors="coerce").fillna(0).astype(int)

    n_guvern = int(plx["guvern"].sum())
    n_parl = len(plx) - n_guvern
    k1, k2, k3, k4 = st.columns(4)
    kpi_card(k1, "Proiecte PLx", fmt_int(len(plx)))
    kpi_card(k2, "Inițiative guvern", fmt_int(n_guvern),
             help=f"{n_guvern/len(plx)*100:.0f}% din total")
    kpi_card(k3, "Inițiative parlamentare", fmt_int(n_parl),
             help=f"{n_parl/len(plx)*100:.0f}% din total")
    medie_init = plx.loc[~plx["guvern"], "n_initiatori"]
    medie_init = medie_init[medie_init > 0]
    kpi_card(k4, "Inițiatori / proiect parlamentar",
             f"{medie_init.mean():.1f}" if not medie_init.empty else "—")

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("#### Guvern vs. parlamentar")
        fig = go.Figure(go.Bar(
            x=["Guvern", "Parlamentar"], y=[n_guvern, n_parl],
            marker_color=[WARNING, ACCENT],
            text=[fmt_int(n_guvern), fmt_int(n_parl)], textposition="outside"))
        fig.update_layout(height=300, yaxis_title="număr proiecte")
        st.plotly_chart(fig, use_container_width=True)
    with col_b:
        st.markdown("#### Număr inițiatori / proiect")
        parl = plx.loc[~plx["guvern"] & (plx["n_initiatori"] > 0), "n_initiatori"]
        if not parl.empty:
            fig = go.Figure(go.Histogram(x=parl, marker_color=ACCENT_2, nbinsx=40))
            fig.update_layout(height=300, xaxis_title="inițiatori per proiect",
                              yaxis_title="proiecte (doar parlamentare)")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.caption("Fără date de inițiatori pentru proiecte parlamentare.")

    st.markdown("#### Proiecte PLx")
    fc1, fc2 = st.columns([3, 1])
    with fc1:
        q = st.text_input("Caută în titlu", placeholder="ex: PL nr. 201, cod fiscal…").strip()
    with fc2:
        sursa = st.selectbox("Sursă inițiativă", ["Toate", "Guvern", "Parlamentar"])

    flt = plx
    if sursa == "Guvern":
        flt = flt[flt["guvern"]]
    elif sursa == "Parlamentar":
        flt = flt[~flt["guvern"]]
    if q:
        flt = flt[flt["titlu"].str.lower().str.contains(q.lower(), regex=False, na=False)]

    st.caption(f"{fmt_int(len(flt))} proiecte găsite"
               + (f" · sursă: {sursa.lower()}" if sursa != "Toate" else ""))

    if flt.empty:
        st.info("Niciun proiect nu corespunde criteriilor.")
    else:
        out = flt.copy()
        out["tip"] = out["guvern"].map({True: "Guvern", False: "Parlamentar"})
        show = out[["idp", "titlu", "tip", "n_initiatori"]].rename(columns={
            "idp": "id PLx", "titlu": "titlu", "tip": "sursă", "n_initiatori": "nr. inițiatori",
        }).sort_values("nr. inițiatori", ascending=False)
        st.dataframe(
            show.head(1000), use_container_width=True, hide_index=True,
            column_config={
                "id PLx": st.column_config.TextColumn(width="small"),
                "titlu": st.column_config.TextColumn(width="large"),
                "sursă": st.column_config.TextColumn(width="small"),
                "nr. inițiatori": st.column_config.NumberColumn(format="%d", width="small"),
            },
        )
        if len(flt) > 1000:
            st.caption(f"Se afișează primele 1.000 din {fmt_int(len(flt))}.")

st.caption("Sursă: componența comisiilor Senatului și fișele de inițiatori ale proiectelor "
           "legislative (PLx). Date publice agregate.")
