"""ROMEGA · Alerte & semnale — semnale de interes generate automat (NU acuzații).

Sursă: data/v1/alerte.json. Semnalele sunt produse prin reguli deterministe peste date
deschise. Singurele defensabile fără verificare suplimentară sunt cele de tip
'conflict_confirmat' (firma apare în PROPRIA declarație de interese a persoanei).
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app import data
from app.theme import (DANGER, SUCCESS, TEXT_DIM, WARNING, apply_theme, fmt_int,
                       fmt_lei, kpi_card, page_header, sidebar_brand)

st.set_page_config(page_title="Alerte · ROMEGA", page_icon="🚨", layout="wide")
apply_theme()
sidebar_brand()

page_header("Alerte & semnale",
            "Semnale de interes generate automat din date deschise prin reguli deterministe. "
            "Acestea sunt indicii de verificat, NU acuzații.")

raw = data.alerte()
alerte = raw.get("alerte", []) if isinstance(raw, dict) else []

if not alerte:
    st.info("Nu există alerte în setul de date.")
    st.stop()

# ---------------- disclaimer (din json) ----------------
disclaimer = (raw.get("disclaimer") or "").strip()
if disclaimer:
    st.warning(disclaimer, icon="⚠️")

# ---------------- etichete lizibile pe tip ----------------
TIP_ETICHETE = {
    "conflict_confirmat": "Conflict documentat (în propria declarație)",
    "soe_pierdere_contracte_mari": "Companie de stat pe pierdere cu contracte mari",
    "partid_subventie_fara_parlamentari": "Partid cu subvenție fără parlamentari",
    "parlamentar_conduce_soe": "Parlamentar la conducerea unei companii de stat",
    "firma_noua_bani_stat": "Firmă nou-înființată cu bani de stat",
    "outlier_valoare_contract": "Valoare medie/contract neobișnuit de mare",
    "concentrare_persoana": "Persoană prezentă în multe companii",
    "firma_mama_straina": "Firmă cu mamă în străinătate cu bani de stat",
}


def tip_label(t: str) -> str:
    return TIP_ETICHETE.get(t, (t or "").replace("_", " ").capitalize())


# ---------------- helpers ----------------
SEV_ORDER = {"mare": 0, "medie": 1, "mica": 2}
SEV_COLOR = {"mare": DANGER, "medie": WARNING, "mica": TEXT_DIM}
SEV_LABEL = {"mare": "MARE", "medie": "medie", "mica": "mică"}


def entitate_text(ent) -> str:
    """entitate poate fi string sau dict (ex. {cui, forma_juridica, an_infiintare, caen})."""
    if isinstance(ent, dict):
        cui = ent.get("cui")
        bits = []
        if cui:
            bits.append(f"CUI {cui}")
        for k in ("forma_juridica", "caen", "tara_mama", "an_infiintare"):
            if ent.get(k):
                bits.append(str(ent[k]))
        return " · ".join(bits) if bits else "—"
    return str(ent) if ent not in (None, "") else "—"


# ---------------- normalizare în DataFrame ----------------
rows = []
for i, a in enumerate(alerte):
    sev = a.get("severitate", "")
    rows.append({
        "_idx": i,
        "tip": a.get("tip", ""),
        "tip_lbl": tip_label(a.get("tip", "")),
        "severitate": sev,
        "_sev_rank": SEV_ORDER.get(sev, 9),
        "titlu": (a.get("titlu") or "").strip(),
        "entitate": entitate_text(a.get("entitate")),
        "provenance": (a.get("provenance") or "").strip(),
        "scor": a.get("scor"),
    })
df = pd.DataFrame(rows)

# ---------------- KPI pe severitate ----------------
pe_sev = raw.get("pe_severitate") or {}
total = raw.get("total", len(df))
n_mare = int(pe_sev.get("mare", int((df["severitate"] == "mare").sum())))
n_medie = int(pe_sev.get("medie", int((df["severitate"] == "medie").sum())))
n_mica = int(pe_sev.get("mica", int((df["severitate"] == "mica").sum())))

c1, c2, c3, c4 = st.columns(4)
kpi_card(c1, "Total semnale", fmt_int(total))
kpi_card(c2, "Severitate mare", fmt_int(n_mare),
         help="Cele mai importante — în special conflictele documentate.")
kpi_card(c3, "Severitate medie", fmt_int(n_medie))
kpi_card(c4, "Severitate mică", fmt_int(n_mica))

# evidențiere vizuală mare = roșu
if n_mare:
    st.markdown(
        f"<div style='margin:-4px 0 4px;font-size:13px'>"
        f"<span style='color:{DANGER};font-weight:700'>● {n_mare}</span> "
        f"<span style='color:{TEXT_DIM}'>semnale de severitate mare</span> · "
        f"<span style='color:{WARNING};font-weight:700'>● {fmt_int(n_medie)}</span> "
        f"<span style='color:{TEXT_DIM}'>medie</span> · "
        f"<span style='color:{TEXT_DIM};font-weight:700'>● {fmt_int(n_mica)}</span> "
        f"<span style='color:{TEXT_DIM}'>mică</span></div>",
        unsafe_allow_html=True)

# ---------------- agregat (notă) ----------------
agregate = raw.get("agregate") or {}
if isinstance(agregate, dict) and agregate:
    firme_noi = agregate.get("firme_noi_cu_bani_stat_total")
    doar_ad = agregate.get("firme_noi_doar_achizitii_directe")
    nota = agregate.get("nota_agregat", "")
    if firme_noi:
        msg = (f"**Agregat:** {fmt_int(firme_noi)} firme nou-înființate cu bani de stat în total")
        if doar_ad:
            msg += f" (din care {fmt_int(doar_ad)} doar cu achiziții directe mici, nelistate individual)"
        msg += "."
        if nota:
            msg += f" {nota}"
        st.info(msg, icon="📌")

st.divider()

# ---------------- conflict_confirmat — sus, separat ----------------
conf = df[df["tip"] == "conflict_confirmat"].sort_values("titlu")
if not conf.empty:
    st.markdown(f"#### 🔴 Conflicte documentate ({fmt_int(len(conf))})")
    st.caption("Cele mai importante: firma apare în PROPRIA declarație de interese a persoanei. "
               "Singurele semnale defensabile fără verificare suplimentară.")
    for _, r in conf.iterrows():
        full = alerte[int(r["_idx"])]
        det = full.get("detalii") or {}
        firme = det.get("firme") or []
        with st.container():
            st.markdown(
                f"<div style='border:1px solid {DANGER};border-radius:10px;padding:10px 14px;"
                f"margin-bottom:8px;background:rgba(239,68,68,.06)'>"
                f"<div style='font-weight:600'>{r['titlu']}</div>"
                f"<div style='font-size:12px;color:{TEXT_DIM};margin-top:2px'>"
                f"Entitate: {r['entitate']}"
                + (f" · contracte: {fmt_lei(det.get('total_contracte_ron'))}"
                   if det.get("total_contracte_ron") else "")
                + (f" · {len(firme)} firmă/firme" if firme else "")
                + "</div></div>",
                unsafe_allow_html=True)
    st.divider()

# ---------------- filtre ----------------
st.markdown("#### Filtrează semnalele")
pe_tip = raw.get("pe_tip") or {}
tipuri_disp = sorted(df["tip"].unique(), key=lambda t: -int(pe_tip.get(t, 0)))
tip_optiuni = {f"{tip_label(t)} ({fmt_int(pe_tip.get(t, int((df['tip'] == t).sum())))})": t
               for t in tipuri_disp}

fc1, fc2, fc3 = st.columns([2, 1, 2])
with fc1:
    tip_sel_lbls = st.multiselect("Tip semnal", list(tip_optiuni.keys()),
                                  placeholder="Toate tipurile")
with fc2:
    sev_optiuni = ["Toate", "mare", "medie", "mică"]
    sev_sel = st.selectbox("Severitate", sev_optiuni)
with fc3:
    q = st.text_input("Caută în titlu sau entitate",
                      placeholder="ex: un nume, o firmă, un CUI…").strip()

flt = df
if tip_sel_lbls:
    tipuri_alese = {tip_optiuni[l] for l in tip_sel_lbls}
    flt = flt[flt["tip"].isin(tipuri_alese)]
if sev_sel != "Toate":
    sev_key = {"mare": "mare", "medie": "medie", "mică": "mica"}[sev_sel]
    flt = flt[flt["severitate"] == sev_key]
if q:
    ql = q.lower()
    mask = (flt["titlu"].str.lower().str.contains(ql, regex=False, na=False)
            | flt["entitate"].str.lower().str.contains(ql, regex=False, na=False))
    flt = flt[mask]

flt = flt.sort_values(["_sev_rank", "tip", "titlu"])

st.caption(f"{fmt_int(len(flt))} semnale afișate (din {fmt_int(len(df))})"
           + (f" · căutare: „{q}”" if q else ""))

# ---------------- tabel ----------------
CAP = 500
if flt.empty:
    st.info("Niciun semnal nu corespunde filtrelor. Schimbă tipul, severitatea sau căutarea.")
else:
    show = flt.head(CAP).copy()
    show["sev_afis"] = show["severitate"].map(lambda s: SEV_LABEL.get(s, s or "—"))
    table = show[["sev_afis", "titlu", "tip_lbl", "entitate", "provenance"]].rename(columns={
        "sev_afis": "severitate", "tip_lbl": "tip", "provenance": "sursă",
    })

    def _sev_style(col):
        return [f"color:{SEV_COLOR.get(s, TEXT_DIM)};font-weight:700"
                for s in show["severitate"]]

    styled = table.style.apply(_sev_style, subset=["severitate"])
    st.dataframe(
        styled, use_container_width=True, hide_index=True,
        column_config={
            "severitate": st.column_config.TextColumn(width="small"),
            "titlu": st.column_config.TextColumn(width="large"),
            "tip": st.column_config.TextColumn(width="medium"),
            "entitate": st.column_config.TextColumn(width="medium"),
            "sursă": st.column_config.TextColumn("sursă / provenance", width="medium"),
        },
    )
    if len(flt) > CAP:
        st.caption(f"Se afișează primele {CAP} din {fmt_int(len(flt))}. "
                   "Restrânge cu filtre sau căutare pentru a vedea mai mult.")

    st.divider()

    # ---------------- detalii pe alertă selectată ----------------
    st.markdown("#### Detalii complete pe un semnal")
    opt = {f"[{SEV_LABEL.get(r['severitate'], r['severitate'])}] {r['titlu']}": int(r["_idx"])
           for _, r in show.iterrows()}
    if opt:
        sel_lbl = st.selectbox("Alege un semnal", list(opt.keys()),
                               label_visibility="collapsed")
        full = alerte[opt[sel_lbl]]
        with st.expander("Detalii complete", expanded=True):
            sev = full.get("severitate", "")
            st.markdown(
                f"**{full.get('titlu', '')}**  \n"
                f"<span style='color:{SEV_COLOR.get(sev, TEXT_DIM)};font-weight:700'>"
                f"severitate {SEV_LABEL.get(sev, sev)}</span> · "
                f"<span class='badge'>{tip_label(full.get('tip', ''))}</span>"
                + (f" · scor {full.get('scor')}" if full.get("scor") is not None else ""),
                unsafe_allow_html=True)

            ent = full.get("entitate")
            st.markdown("**Entitate**")
            if isinstance(ent, dict):
                st.json(ent)
            else:
                st.write(entitate_text(ent))

            det = full.get("detalii")
            if det:
                st.markdown("**Detalii**")
                if isinstance(det, dict):
                    st.json(det)
                else:
                    st.write(det)

            prov = full.get("provenance")
            if prov:
                st.markdown("**Provenance (sursă)**")
                st.markdown(f"<span style='color:{TEXT_DIM};font-size:12px'>{prov}</span>",
                            unsafe_allow_html=True)

st.divider()
st.caption("Sursă: data/v1/alerte.json — semnale deterministe peste date deschise (ONRC, SICAP, "
           "declarații de interese, romega.duckdb). Legăturile pe nume pot fi omonime; verifică "
           "întotdeauna în sursele originale. Acestea sunt indicii de verificat, nu acuzații.")
