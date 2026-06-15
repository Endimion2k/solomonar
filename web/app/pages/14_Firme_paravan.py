"""Firme noi cu bani de stat — lead-uri de verificat (posibil paravan) (SOLOMONAR).

FILTRU: firmele cu flag 'firmă nouă cu bani de stat' (înființate cu ≤1 an înainte de
prima achiziție) ȘI care au contracte (canalul mare). Restul firmelor noi ajung la stat
doar prin achiziții directe — apar ca agregat în notă.

ATENȚIE: o firmă tânără cu contract NU înseamnă neregulă. E un LEAD de verificat, nu o acuzație.
"""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from app import data
from app.theme import (ACCENT, DANGER, TEXT_DIM, WARNING, apply_theme, fmt_int,
                       kpi_card, page_header, sidebar_brand)

st.set_page_config(page_title="Firme noi cu bani de stat · SOLOMONAR", page_icon="🚩",
                   layout="wide")
apply_theme()
sidebar_brand()
page_header("🚩 Firme noi cu bani de stat",
            "Firme înființate cu cel mult un an înainte de prima achiziție de la stat, "
            "care au câștigat contracte publice — canalul mare. Sunt lead-uri de verificat, "
            "nu acuzații.")

df = data.firme_onrc()
meta = data.firme_onrc_meta()

if df.empty:
    st.warning("Nu există date ONRC despre firme disponibile.")
    st.stop()

# ---------------- DISCLAIMER (puternic, sus) ----------------
st.markdown(
    f"<div style='background:rgba(245,158,11,.10);border:1px solid {WARNING};"
    f"border-radius:12px;padding:14px 18px;margin-bottom:6px;font-size:13px;color:{TEXT_DIM}'>"
    f"<b style='color:{WARNING}'>⚠ Citește înainte:</b> o firmă tânără care a câștigat un "
    f"contract cu statul <b>NU înseamnă automat o neregulă</b>. Multe sunt perfect legitime "
    f"(antreprenori noi, spin-off-uri, firme de proiect). Această listă este un set de "
    f"<b>lead-uri de verificat</b> — semnale de tip „paravan posibil” —, "
    f"<b>nu o acuzație</b>. Verifică fiecare caz individual înainte de orice concluzie.</div>",
    unsafe_allow_html=True)

# ---------------- filtru de bază: firmă nouă + are contracte ----------------
core = df[df["este_noua"] & df["are_contracte"].fillna(False)].copy()

# agregat: toate firmele noi (canalul mare + achiziții directe)
nr_noua_total = int(df["este_noua"].sum())
nr_noua_ad = int((df["este_noua"] & df["are_achizitii_directe"].fillna(False)).sum())

if core.empty:
    st.info("Nicio firmă nouă cu contracte în datele curente.")
    st.stop()

# ---------------- KPI ----------------
c1, c2, c3, c4 = st.columns(4)
kpi_card(c1, "Firme noi cu contracte", fmt_int(len(core)),
         help="Înființate cu ≤1 an înainte de prima achiziție ȘI au contracte publice (canalul mare).")
kpi_card(c2, "Județe acoperite", fmt_int(core["judet"].fillna("").replace("", float("nan")).nunique()))
kpi_card(c3, "An mediu înființare",
         fmt_int(round(core["an_infiintare"].dropna().mean())) if core["an_infiintare"].notna().any() else "—")
kpi_card(c4, "Cu firmă-mamă străină", fmt_int(int(core["mama_straina"].sum())))

st.caption(
    f"Notă de context: în total **{fmt_int(nr_noua_total)}** firme poartă flag-ul "
    f"„firmă nouă cu bani de stat”; dintre ele **{fmt_int(nr_noua_ad)}** ajung la stat și prin "
    f"achiziții directe (canalul mic). Pagina se concentrează pe cele cu contracte — canalul mare.")

st.divider()

# ---------------- filtre ----------------
st.markdown("#### Filtre")
fc1, fc2, fc3 = st.columns([2, 2, 1])

judete = sorted(j for j in core["judet"].dropna().unique() if str(j).strip())
sel_judet = fc1.multiselect("Județ", judete, default=[], placeholder="toate județele")

forme = sorted(f for f in core["forma_juridica"].dropna().unique() if str(f).strip())
sel_forma = fc2.multiselect("Formă juridică", forme, default=[], placeholder="toate formele")

doar_mama = fc3.checkbox("Doar firmă-mamă străină", value=False)

ani = core["an_infiintare"].dropna().astype(int)
an_min, an_max = int(ani.min()), int(ani.max())
if an_min < an_max:
    sel_an = st.slider("An înființare", min_value=an_min, max_value=an_max,
                       value=(an_min, an_max), step=1)
else:
    sel_an = (an_min, an_max)
    st.caption(f"An înființare: toate firmele sunt din {an_min}.")

q = st.text_input("Caută firmă (nume sau CUI)", placeholder="ex: Classicbuild, 51161591…").strip()

view = core.copy()
if sel_judet:
    view = view[view["judet"].isin(sel_judet)]
if sel_forma:
    view = view[view["forma_juridica"].isin(sel_forma)]
if doar_mama:
    view = view[view["mama_straina"]]
view = view[view["an_infiintare"].fillna(-1).astype(int).between(sel_an[0], sel_an[1])]
if q:
    ql = q.lower()
    view = view[view["nume"].fillna("").str.lower().str.contains(ql, regex=False, na=False)
                | view["cui"].astype(str).str.contains(ql, regex=False, na=False)]

st.caption(f"{fmt_int(len(view))} firme afișate din {fmt_int(len(core))} firme noi cu contracte.")

st.divider()

# ---------------- grafic: distribuție pe an de înființare ----------------
st.markdown("#### Distribuția pe an de înființare")
if view.empty:
    st.info("Niciun rezultat pentru filtrele curente.")
else:
    by_year = view["an_infiintare"].dropna().astype(int).value_counts().sort_index()
    fig = go.Figure(go.Bar(
        x=by_year.index.astype(str), y=by_year.values,
        marker_color=ACCENT,
        hovertemplate="An: %{x}<br>Firme: %{y}<extra></extra>",
    ))
    fig.update_layout(height=340, xaxis_title="an înființare", yaxis_title="firme",
                      margin=dict(l=10, r=20, t=10, b=40))
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Anii recenți (multe firme tinere cu contracte) merită cea mai atentă verificare.")

st.divider()

# ---------------- tabel ----------------
st.markdown("#### Firmele — lead-uri de verificat")
if view.empty:
    st.info("Niciun rezultat pentru filtrele curente.")
else:
    show = view.copy()
    show["canale"] = show.apply(
        lambda r: " + ".join(
            ([f"contracte"] if r.get("are_contracte") else [])
            + (["achiziții directe"] if r.get("are_achizitii_directe") else [])
        ) or "—", axis=1)
    cols = ["nume", "cui", "forma_juridica", "an_infiintare", "judet", "caen_domeniu",
            "tara_mama", "canale"]
    show = show[cols].sort_values("an_infiintare", ascending=False, na_position="last").head(1000)
    st.dataframe(
        show, use_container_width=True, hide_index=True,
        column_config={
            "nume": st.column_config.TextColumn("Firmă", width="large"),
            "cui": st.column_config.NumberColumn("CUI", format="%d"),
            "forma_juridica": st.column_config.TextColumn("Formă"),
            "an_infiintare": st.column_config.NumberColumn("An", format="%d"),
            "judet": st.column_config.TextColumn("Județ"),
            "caen_domeniu": st.column_config.TextColumn("CAEN domeniu", width="medium"),
            "tara_mama": st.column_config.TextColumn("Țară-mamă"),
            "canale": st.column_config.TextColumn("Canale", width="medium"),
        },
    )
    if len(view) > 1000:
        st.caption("Se afișează primele 1.000 de rânduri. Rafinează filtrele pentru a vedea mai mult.")

st.divider()
st.caption(
    f"Sursă: {meta.get('sursa') or 'ONRC (data.gov.ro)'}. "
    f"{meta.get('nota') or ''}")
