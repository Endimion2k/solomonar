"""Follow the money — legături persoane ↔ firme cu contracte de stat (ROMEGA).

Două niveluri de încredere:
  • CONFIRMATE — firma apare explicit în declarația de interese a persoanei (defensabil).
  • Candidați — potriviri pe nume (posibili omonimi), NU acuzații; necesită verificare.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app import data
from app.theme import (ACCENT, ACCENT_2, DANGER, SUCCESS, WARNING, TEXT_DIM,
                       apply_theme, fmt_int, fmt_lei, kpi_card, page_header, sidebar_brand)

st.set_page_config(page_title="Follow the money · ROMEGA", page_icon="🔎", layout="wide")
apply_theme()
sidebar_brand()
page_header("Follow the money",
            "Legături între persoane publice și firme care au contracte cu statul. "
            "Separăm strict legăturile confirmate de potrivirile pe nume neverificate.")

fm = data.follow_money()

if not fm:
    st.warning("Nu există date follow-the-money disponibile.")
    st.stop()

confirmate = fm.get("confirmate", []) or []
leaduri = fm.get("leaduri_neverificate", []) or []


def _parlamentar_txt(p) -> str:
    if not p:
        return "—"
    parts = [p.get("camera"), p.get("partid"), p.get("judet")]
    return " · ".join(str(x) for x in parts if x)


# ---------------- KPI ----------------
total_confirmate_lei = sum(
    f.get("total_ron") or 0 for r in confirmate
    for f in (r.get("firme_contracte_autodeclarate") or [])
)
total_leaduri_lei = sum(r.get("total_contracte_ron") or 0 for r in leaduri)
c1, c2, c3, c4 = st.columns(4)
kpi_card(c1, "Legături confirmate", fmt_int(fm.get("CONFIRMATE_autodeclarate") or len(confirmate)),
         help="Firma figurează în declarația de interese a persoanei.")
kpi_card(c2, "Valoare contracte (confirmate)", fmt_lei(total_confirmate_lei))
kpi_card(c3, "Candidați (neverificați)", fmt_int(fm.get("total_leaduri") or len(leaduri)),
         help="Potriviri pe nume — posibili omonimi, necesită verificare.")
kpi_card(c4, "Din care parlamentari", fmt_int(fm.get("din_care_parlamentari")))

if fm.get("nota"):
    st.caption(f"ℹ️ {fm.get('nota')}")

st.divider()

# ============================================================
# SECȚIUNEA 1 — CONFIRMATE
# ============================================================
st.markdown(f"### ✅ Legături confirmate ({len(confirmate)})")
st.markdown(
    f"<div style='background:rgba(16,185,129,.08);border:1px solid {SUCCESS};"
    f"border-radius:10px;padding:10px 14px;font-size:13px;color:{TEXT_DIM};margin-bottom:12px'>"
    "Sursă <b>defensabilă</b>: firma cu contracte de stat apare explicit în "
    "<b>declarația de interese</b> a persoanei. Persoana a declarat ea însăși legătura.</div>",
    unsafe_allow_html=True)

conf_rows = []
for r in confirmate:
    nume = (r.get("nume_key") or "").title()
    parl = _parlamentar_txt(r.get("parlamentar"))
    inc = r.get("incredere") or "—"
    for f in (r.get("firme_contracte_autodeclarate") or []):
        conf_rows.append({
            "Persoană": nume, "Calitate": parl, "Încredere": inc,
            "Firmă": f.get("nume"), "CUI": f.get("cui"),
            "Contracte (lei)": f.get("total_ron"),
        })

if conf_rows:
    conf_df = pd.DataFrame(conf_rows).sort_values("Contracte (lei)", ascending=False, na_position="last")
    st.dataframe(
        conf_df, use_container_width=True, hide_index=True,
        column_config={
            "Persoană": st.column_config.TextColumn(width="medium"),
            "Calitate": st.column_config.TextColumn(width="medium"),
            "Firmă": st.column_config.TextColumn(width="large"),
            "CUI": st.column_config.NumberColumn(format="%d"),
            "Contracte (lei)": st.column_config.NumberColumn(format="%.0f"),
        },
    )
else:
    st.info("Nicio legătură confirmată disponibilă.")

st.divider()

# ============================================================
# SECȚIUNEA 2 — CANDIDAȚI (LEADURI NEVERIFICATE)
# ============================================================
st.markdown(f"### 🔎 Candidați — potriviri pe nume, neverificate ({len(leaduri)})")
st.markdown(
    f"<div style='background:rgba(245,158,11,.10);border:1px solid {WARNING};"
    f"border-radius:10px;padding:12px 16px;font-size:13px;color:#f1d6a0;margin-bottom:12px'>"
    "<b>⚠️ AVERTISMENT.</b> Aceste legături sunt deduse din <b>potrivirea numelui</b> dintre o persoană "
    "publică și administratorul/asociatul unei firme cu contracte de stat. "
    "Pot fi <b>omonime</b> (persoane diferite cu același nume) și <b>NU constituie acuzații</b>. "
    "Sunt piste de cercetare care necesită verificare independentă (CUI, CNP, surse oficiale) "
    "înainte de orice concluzie.</div>",
    unsafe_allow_html=True)

if leaduri:
    only_parl = st.checkbox("Doar parlamentari", value=False)
    lead_view = [r for r in leaduri if r.get("parlamentar")] if only_parl else leaduri

    lead_rows = []
    for r in lead_view:
        comp = r.get("companii") or []
        firme_nume = ", ".join(str(c.get("nume")) for c in comp if c.get("nume"))[:120]
        lead_rows.append({
            "Nume (potrivire)": (r.get("nume_key") or "").title(),
            "Calitate": _parlamentar_txt(r.get("parlamentar")),
            "Încredere": r.get("incredere") or "—",
            "Firme (administrator/asociat)": firme_nume,
            "Nr. firme": r.get("n_firme_cu_contracte") or len(comp),
            "Contracte (lei)": r.get("total_contracte_ron"),
        })

    if lead_rows:
        lead_df = pd.DataFrame(lead_rows).sort_values(
            "Contracte (lei)", ascending=False, na_position="last")
        st.dataframe(
            lead_df, use_container_width=True, hide_index=True,
            column_config={
                "Nume (potrivire)": st.column_config.TextColumn(width="medium"),
                "Calitate": st.column_config.TextColumn(width="medium"),
                "Firme (administrator/asociat)": st.column_config.TextColumn(width="large"),
                "Nr. firme": st.column_config.NumberColumn(format="%d"),
                "Contracte (lei)": st.column_config.NumberColumn(format="%.0f"),
            },
        )
        st.caption(f"{fmt_int(len(lead_rows))} candidați afișați. "
                   "Repetăm: potriviri pe nume — a se trata ca ipoteze, nu fapte.")
    else:
        st.info("Niciun candidat pentru filtrul curent.")
else:
    st.info("Niciun candidat (lead neverificat) disponibil.")

st.divider()

# ============================================================
# SECȚIUNEA 3 — REȚELE DE CO-ADMINISTRARE
# ============================================================
st.markdown("### 🕸️ Rețele de co-administrare")
st.caption("Firme cu contracte de stat care au mai mulți administratori — indicator de structuri "
           "comune/interconectate. Mai mulți administratori pe aceeași firmă = nod mai dens.")

rc = data.retele_coadministrare()
if rc.empty:
    st.info("Nu există date de co-administrare.")
else:
    rc = rc.copy()
    min_admin = st.slider("Minim administratori per firmă", min_value=1,
                          max_value=int(rc["n_administratori"].max()), value=2)
    rcv = rc[rc["n_administratori"] >= min_admin].sort_values(
        "contracte", ascending=False, na_position="last")

    colA, colB = st.columns([3, 2])
    with colA:
        top = rcv.head(20)
        if not top.empty:
            fig = go.Figure(go.Bar(
                x=top["contracte"], y=top["firma"], orientation="h",
                marker_color=ACCENT,
                customdata=top["n_administratori"],
                hovertemplate="<b>%{y}</b><br>Contracte: %{x:,.0f} lei<br>"
                              "Administratori: %{customdata}<extra></extra>",
            ))
            fig.update_layout(height=520, yaxis=dict(autorange="reversed"),
                              xaxis_title="contracte (lei)", margin=dict(l=10, r=20, t=10, b=40))
            st.plotly_chart(fig, use_container_width=True)
    with colB:
        st.markdown("**Detaliu administratori**")
        det = rcv.head(40).copy()
        det["administratori"] = det["administratori"].apply(
            lambda a: ", ".join(str(x).title() for x in a) if isinstance(a, list) else "")
        st.dataframe(
            det[["firma", "n_administratori", "contracte", "administratori"]],
            use_container_width=True, hide_index=True,
            column_config={
                "firma": st.column_config.TextColumn("Firmă", width="medium"),
                "n_administratori": st.column_config.NumberColumn("Nr. admin", format="%d"),
                "contracte": st.column_config.NumberColumn("Contracte (lei)", format="%.0f"),
                "administratori": st.column_config.TextColumn("Administratori", width="large"),
            },
        )
    st.caption(f"{fmt_int(len(rcv))} firme cu cel puțin {min_admin} administratori comuni.")
