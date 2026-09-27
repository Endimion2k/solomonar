"""SOLOMONAR — Companii de stat. Explorare a celor 1.256 companii cu capital de stat:
filtre pe sector / minister tutelar / județ / BVB / contracte, tabel financiar,
top contracte și fișă detaliată per companie."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import sys as _sys, pathlib as _pl  # bootstrap: import 'app' fără PYTHONPATH (rulare directă/deploy)
for _a in _pl.Path(__file__).resolve().parents:
    if (_a / 'app').is_dir():
        _sys.path.insert(0, str(_a)); break

from app import data, ui
from app.theme import (ACCENT, ACCENT_2, SUCCESS, TEXT_DIM, apply_theme, fmt_int,
                       fmt_lei, fmt_pct, kpi_card, page_header, sidebar_brand)

st.set_page_config(page_title="Companii · SOLOMONAR", page_icon="🏢", layout="wide")
apply_theme()
sidebar_brand()
page_header("Companii de stat",
            "Cele 1.256 de companii cu capital de stat — sector, minister tutelar, "
            "listare BVB, salariați și contracte cu statul.")

df = data.companii_df()
if df.empty:
    st.warning("Nu există date despre companii.")
    st.stop()

# ---------------- filtre ----------------
fc1, fc2, fc3 = st.columns(3)
sectoare = sorted(df["sector"].dropna().unique().tolist())
tutele = sorted(df["tutela"].dropna().unique().tolist())
judete = sorted(df["judet"].dropna().unique().tolist())

sel_sector = fc1.multiselect("Sector", sectoare, placeholder="Toate sectoarele")
sel_tutela = fc2.multiselect("Minister tutelar", tutele, placeholder="Toate ministerele")
sel_judet = fc3.multiselect("Județ", judete, placeholder="Toate județele")

fc4, fc5, fc6 = st.columns([1, 1, 2])
doar_bvb = fc4.checkbox("Doar listate BVB")
doar_contracte = fc5.checkbox("Doar cu contracte")
q = fc6.text_input("Caută după nume", placeholder="ex: Hidroelectrica, Romgaz…")

f = df.copy()
if sel_sector:
    f = f[f["sector"].isin(sel_sector)]
if sel_tutela:
    f = f[f["tutela"].isin(sel_tutela)]
if sel_judet:
    f = f[f["judet"].isin(sel_judet)]
if doar_bvb:
    f = f[f["bvb"]]
if doar_contracte:
    f = f[f["contracte_ron"].notna()]
if q.strip():
    f = f[f["nume"].str.contains(q.strip(), case=False, na=False)]

# ---------------- KPI ----------------
c1, c2, c3, c4 = st.columns(4)
kpi_card(c1, "Companii (filtrate)", fmt_int(len(f)),
         help=f"din {fmt_int(len(df))} total")
kpi_card(c2, "Listate BVB", fmt_int(int(f["bvb"].sum())))
kpi_card(c3, "Cu raportare (salariați)", fmt_int(int(f["salariati"].notna().sum())))
kpi_card(c4, "Total contracte cu statul", fmt_lei(f["contracte_ron"].sum()))

st.divider()

if f.empty:
    st.info("Nicio companie nu corespunde filtrelor selectate.")
    st.stop()

# ---------------- tabel ----------------
st.markdown("#### Listă companii")
tbl = f[["nume", "sector", "tutela", "judet", "bvb", "salariati", "cifra_afaceri",
         "profit", "procent_stat", "contracte_ron", "contracte_nr", "nr_reps"]].copy()
tbl = tbl.sort_values("contracte_ron", ascending=False, na_position="last")

st.dataframe(
    tbl, use_container_width=True, hide_index=True,
    column_config={
        "nume": st.column_config.TextColumn("Companie", width="large"),
        "sector": st.column_config.TextColumn("Sector"),
        "tutela": st.column_config.TextColumn("Minister tutelar", width="medium"),
        "judet": st.column_config.TextColumn("Județ"),
        "bvb": st.column_config.CheckboxColumn("BVB"),
        "salariati": st.column_config.NumberColumn("Salariați", format="%d"),
        "cifra_afaceri": st.column_config.NumberColumn("Cifră afaceri (lei)", format="%.0f"),
        "profit": st.column_config.NumberColumn("Profit net (lei)", format="%.0f"),
        "procent_stat": st.column_config.NumberColumn("% stat", format="%.2f%%"),
        "contracte_ron": st.column_config.NumberColumn("Contracte (lei)", format="%.0f"),
        "contracte_nr": st.column_config.NumberColumn("Nr. contracte", format="%d"),
        "nr_reps": st.column_config.NumberColumn("Reprez. legali", format="%d"),
    },
)
st.caption(f"{fmt_int(len(f))} companii afișate. Sortate descrescător după valoarea contractelor cu statul.")

# ---------------- grafic: top 15 după contracte ----------------
st.divider()
st.markdown("#### Top 15 companii după contracte cu statul")
top = f[f["contracte_ron"].notna()].sort_values("contracte_ron", ascending=False).head(15)
if top.empty:
    st.info("Nicio companie din selecție nu are contracte cu statul înregistrate.")
else:
    top = top.iloc[::-1]  # cea mai mare sus în bara orizontală
    fig = go.Figure(go.Bar(
        x=top["contracte_ron"], y=top["nume"], orientation="h",
        marker_color=ACCENT,
        customdata=top["contracte_nr"],
        hovertemplate="<b>%{y}</b><br>Contracte: %{x:,.0f} lei"
                      "<br>Nr. contracte: %{customdata}<extra></extra>",
    ))
    fig.update_layout(height=480, margin=dict(l=10, r=20, t=10, b=40),
                      xaxis_title="valoare contracte (lei)")
    st.plotly_chart(fig, use_container_width=True)

# ---------------- guvernanță: date oficiale guvernanta.gov.ro ----------------
guv = data.guvernanta()
if guv.get("numiri"):
    st.divider()
    st.markdown("#### Conducerea companiilor de stat centrale — date oficiale")
    st.caption(f"Sursă: {ui.GUV_SURSA} · registru generat la {str(guv.get('source_generated_at'))[:10]}. "
               "Consilii de administrație, directori, remunerație brută lunară declarată, afiliere politică.")
    afil = guv.get("afiliere_politica") or {}
    cu_partid = sum(v for k, v in afil.items() if k not in ("Fără apartenență politică", "nedeclarat"))
    g1, g2, g3, g4 = st.columns(4)
    kpi_card(g1, "Companii în registru", fmt_int(guv.get("n_companii")))
    kpi_card(g2, "Numiri (CA + conducere)", fmt_int(guv.get("n_numiri")),
             help=f"{fmt_int(guv.get('n_persoane'))} persoane distincte")
    kpi_card(g3, "Persoane cu afiliere politică", fmt_int(cu_partid),
             help=" · ".join(f"{k}: {v}" for k, v in afil.items()))
    kpi_card(g4, "Cumul de funcții", fmt_int(len(guv.get("cumul") or [])),
             help="Persoane numite în conducerea a cel puțin două companii")

    ga, gb = st.columns(2)
    with ga:
        st.markdown("**Afiliere politică declarată (persoane)**")
        parts = [(k, v) for k, v in afil.items()]
        figa = go.Figure(go.Bar(x=[v for _, v in parts], y=[k for k, _ in parts], orientation="h",
                                marker_color=[ACCENT if k not in ("Fără apartenență politică", "nedeclarat")
                                              else "#2a3142" for k, _ in parts],
                                text=[v for _, v in parts], textposition="outside", cliponaxis=False))
        # axa X cu 20% loc în plus: eticheta barei celei mai lungi nu mai e tăiată (371 apărea „37”)
        figa.update_layout(height=280, yaxis=dict(autorange="reversed"),
                           xaxis=dict(range=[0, max([v for _, v in parts] or [1]) * 1.2]),
                           margin=dict(l=10, r=40, t=10, b=10))
        st.plotly_chart(figa, use_container_width=True)
    with gb:
        st.markdown("**Remunerație brută lunară pe rol (lei)**")
        rol_lbl = {"board_chair": "Președinte CA", "board_member": "Membru CA / CS",
                   "executive_director": "Director general", "director": "Director", "other": "Altele"}
        rem = guv.get("remuneratie_pe_rol") or {}
        st.dataframe(pd.DataFrame([{"Rol": rol_lbl.get(k, k), "Numiri cu date": v["n"],
                                    "Mediană": v["median"], "Maxim": v["max"]} for k, v in rem.items()]),
                     use_container_width=True, hide_index=True,
                     column_config={"Mediană": st.column_config.NumberColumn(format="%d"),
                                    "Maxim": st.column_config.NumberColumn(format="%d")})
        st.caption("Valorile sunt cele raportate la sursă; câteva par incomplete (sume foarte mici).")

    with st.expander(f"Cumul de funcții ({len(guv.get('cumul') or [])} persoane)"):
        st.dataframe(pd.DataFrame([{
            "Persoană": c["nume"], "Companii": c["n_companii"],
            "Brut lunar total (lei)": c.get("brut_lunar_total_ron"),
            "Funcții": " · ".join(f"{x['rol']} — {x['companie']}" for x in c["functii"]),
        } for c in guv.get("cumul") or []]), use_container_width=True, hide_index=True,
            column_config={"Brut lunar total (lei)": st.column_config.NumberColumn(format="%d")})
    with st.expander("Cele mai mari remunerații declarate (top 25)"):
        top_rem = sorted((n for n in guv["numiri"] if n.get("brut_lunar_ron")),
                         key=lambda n: -n["brut_lunar_ron"])[:25]
        ui.guvernanta_numiri(top_rem, key="guv_top")

# ---------------- detaliu companie ----------------
st.divider()
st.markdown("#### Fișă companie")
nume_to_cui = dict(zip(f["nume"], f["cui"]))
opt = ["—"] + sorted(f["nume"].tolist())
pick = st.selectbox("Selectează o companie", opt, index=0)

if pick != "—":
    row = f[f["cui"] == nume_to_cui[pick]].iloc[0]
    st.markdown(f"### {row['nume']}")

    badges = []
    if isinstance(row["sector"], str) and row["sector"].strip():
        badges.append(f"<span class='badge'>{row['sector']}</span>")
    if isinstance(row["judet"], str) and row["judet"].strip():
        badges.append(f"<span class='badge'>{row['judet']}</span>")
    if row["bvb"]:
        badges.append(f"<span class='badge'>listată BVB</span>")
    if badges:
        st.markdown(" ".join(badges), unsafe_allow_html=True)

    m1, m2, m3, m4 = st.columns(4)
    sal = row["salariati"]
    kpi_card(m1, "CUI", fmt_int(row["cui"]))
    kpi_card(m2, "Salariați", fmt_int(sal) if pd.notna(sal) else "—")
    pct = row["procent_stat"]
    kpi_card(m3, "% deținut de stat", fmt_pct(pct) if pd.notna(pct) else "—",
             help="Sursă acționariat BVB" if pd.notna(pct) else "Disponibil doar pentru companii listate BVB")
    kpi_card(m4, "Reprezentanți legali", fmt_int(row["nr_reps"]))

    dl, dr = st.columns(2)
    with dl:
        st.markdown("**Date generale**")
        ca = row["cifra_afaceri"]
        pf = row["profit"]
        info = pd.DataFrame([
            {"câmp": "Minister tutelar", "valoare": row["tutela"] or "—"},
            {"câmp": "Sector", "valoare": row["sector"] or "—"},
            {"câmp": "Județ", "valoare": row["judet"] or "—"},
            {"câmp": "Cifră de afaceri", "valoare": fmt_lei(ca) if pd.notna(ca) else "—"},
            {"câmp": "Profit net", "valoare": fmt_lei(pf) if pd.notna(pf) else "—"},
        ])
        st.dataframe(info, use_container_width=True, hide_index=True)

    with dr:
        st.markdown("**Contracte și achiziții cu statul**")
        if not ui.firma_bani_stat(row["cui"], use_columns=False, titlu=""):
            st.info("Nu sunt înregistrate contracte sau achiziții directe pentru această companie.")

    gc = data.guvernanta_companie(row["cui"])
    if gc:
        st.markdown("**Conducerea oficială — guvernanta.gov.ro**")
        c1, c2, c3 = st.columns(3)
        kpi_card(c1, "Persoane în conducere", fmt_int(gc.get("n_conducere")))
        kpi_card(c2, "Cu afiliere politică", fmt_int(gc.get("n_cu_partid")))
        kpi_card(c3, "Brut lunar total (lei)", fmt_lei(gc.get("brut_lunar_total_ron"))
                 if gc.get("brut_lunar_total_ron") else "—")
        ui.guvernanta_numiri(gc.get("numiri") or [], cu_companie=False, key="guv_comp")
        docs = (gc.get("rapoarte_remunerare") or []) + (gc.get("contracte_mandat_model") or [])
        if docs:
            st.markdown("Documente oficiale: " + " · ".join(f"[{d['nume']}]({d['url']})" for d in docs if d.get("url")))
        cmp = gc.get("comparatie_onrc")
        if cmp and (cmp.get("doar_oficial") or cmp.get("doar_onrc")):
            with st.expander(f"Comparație cu reprezentanții legali ONRC — {len(cmp.get('doar_oficial') or [])} "
                             f"doar în lista oficială, {len(cmp.get('doar_onrc') or [])} doar în ONRC"):
                o1, o2 = st.columns(2)
                o1.markdown("**Numiți oficial, absenți din ONRC**  \n" +
                            ("  \n".join(f"· {x}" for x in cmp.get("doar_oficial") or []) or "—"))
                o2.markdown("**În ONRC, absenți din lista oficială**  \n" +
                            ("  \n".join(f"· {x}" for x in cmp.get("doar_onrc") or []) or "—"))
                st.caption("Semnal de verificat, nu o neregulă: registrul ONRC din SOLOMONAR poate fi mai vechi "
                           "decât lista oficială, iar mențiunile ONRC se actualizează cu întârziere.")

    if pd.notna(pct):
        st.markdown("**Structură acționariat**")
        rest = max(0.0, 100.0 - float(pct))
        figp = go.Figure(go.Pie(
            labels=["Stat", "Alți acționari"],
            values=[float(pct), rest], hole=0.55,
            marker_colors=[ACCENT_2, "#2a3142"], sort=False,
            textinfo="label+percent",
        ))
        figp.update_layout(height=280, showlegend=False,
                           margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(figp, use_container_width=True)

st.caption("Notă: cifra de afaceri și profitul net pot lipsi când raportarea financiară "
           "nu este disponibilă; procentul deținut de stat provine din acționariatul BVB "
           "(doar companii listate).")
