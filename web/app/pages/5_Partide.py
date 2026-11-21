"""SOLOMONAR — Partide: subvenții de stat, evoluție anuală, rapoarte RVC."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import sys as _sys, pathlib as _pl  # bootstrap: import 'app' fără PYTHONPATH (rulare directă/deploy)
for _a in _pl.Path(__file__).resolve().parents:
    if (_a / 'app').is_dir():
        _sys.path.insert(0, str(_a)); break

from app import data, ui
from app.theme import tabel
from app.theme import (ACCENT, ACCENT_2, TEXT_DIM, apply_theme, fmt_int, fmt_lei,
                       despre, kpi_card, page_header, party_color, sidebar_brand)

st.set_page_config(page_title="Partide · SOLOMONAR", layout="wide")
apply_theme()
sidebar_brand()
page_header("Partide", "Subvenții de stat alocate partidelor, evoluție anuală și prezență parlamentară.")
despre(
    sursa="Subvențiile de la bugetul de stat, pe ani: platforma banipartide.ro a Expert Forum (EFOR). "
          "Rapoartele financiare anuale: Portalul Legislativ (legislatie.just.ro), care preia situațiile "
          "publicate de partide în Monitorul Oficial. Parlamentarii: cdep.ro și senat.ro; numirile în "
          "conducerea companiilor de stat: registrul guvernanta.gov.ro.",
    calcul="Subvenția totală a unui partid este suma subvențiilor din toți anii disponibili. Graficul pe ani "
           "arată implicit cele 6 partide cu cea mai mare sumă cumulată. „Numiți în conducere SOE” numără "
           "persoanele distincte din registru care și-au declarat afilierea la acel partid.",
    legaturi="Denumirile aceluiași partid din surse diferite (siglă, nume complet, nume de grup parlamentar) "
             "sunt aduse la o siglă comună prin potrivire de text, fără diacritice. Unele sigle sunt grupate "
             "(de exemplu PLUS intră la USR). Numirile din registrul Guvernului se adună doar când afilierea "
             "declarată este exact sigla partidului.",
    limite="Numărul de deputați și senatori arată doar mandatul curent. Deputații minorităților naționale și "
           "grupurile parlamentare fără partid corespondent (de exemplu PACE la Senat) nu se atribuie niciunui "
           "partid. Graficul pe ani folosește denumirile din sursă. Subvențiile sunt disponibile doar pe an, "
           "fără detaliu lunar.",
)

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
    st.plotly_chart(fig, width="stretch")

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
        st.plotly_chart(fig2, width="stretch")

st.divider()

# ---------------- Tabel partide ----------------
st.markdown("#### Detaliu partide")
guv = data.guvernanta()
guv_afil = guv.get("afiliere_politica") or {}
p = p.assign(nr_soe=p["cod"].map(lambda c: guv_afil.get(c, 0)))
tbl = (p[["cod", "total_subventie_lei", "nr_deputati", "nr_senatori", "nr_rapoarte_rvc", "nr_soe"]]
       .sort_values("total_subventie_lei", ascending=False)
       .rename(columns={
           "cod": "Partid", "total_subventie_lei": "Subvenție totală (lei)",
           "nr_deputati": "Deputați", "nr_senatori": "Senatori",
           "nr_rapoarte_rvc": "Rapoarte RVC", "nr_soe": "Numiți în conducere SOE",
       }))
tabel(
    tbl, use_container_width=True, hide_index=True,
    column_config={
        "Subvenție totală (lei)": st.column_config.NumberColumn(format="%.0f"),
        "Deputați": st.column_config.NumberColumn(format="%d"),
        "Senatori": st.column_config.NumberColumn(format="%d"),
        "Rapoarte RVC": st.column_config.NumberColumn(
            format="%d", help="Rapoarte de venituri și cheltuieli depuse la AEP."),
        "Numiți în conducere SOE": st.column_config.NumberColumn(
            format="%d", help="Persoane din CA / conducerea companiilor de stat centrale care și-au declarat "
                              "afilierea la partid (guvernanta.gov.ro)."),
    },
)

# ---------------- rapoarte financiare anuale ----------------
rvc = data.rapoarte_rvc_df()
if not rvc.empty:
    st.divider()
    st.markdown("#### Rapoarte financiare anuale")
    st.caption("Situațiile pe care partidele le publică anual în Monitorul Oficial (Legea 334/2006). "
               "Veniturile sunt suma cotizațiilor, a donațiilor și a veniturilor din alte surse (chirii, "
               "dobânzi), citite din totalul fiecărui tabel al raportului. Împrumuturile sunt arătate "
               "separat și nu intră în venituri; subvenția de la stat e în graficele de mai sus.")
    rvc = rvc.copy()
    rvc["partid"] = rvc["partid_cod"].fillna("").str.upper().where(rvc["partid_cod"].notna(), rvc["partid_nume"])
    rvc["an"] = pd.to_numeric(rvc["an"], errors="coerce")
    r1, r2 = st.columns([2, 1])
    partide_rvc = sorted(rvc["partid"].dropna().unique(), key=lambda s: (len(s) > 12, s))
    alese = r1.multiselect("Partide", partide_rvc, key="rvc_partide",
                           placeholder="Toate partidele")
    ani_rvc = sorted(rvc["an"].dropna().astype(int).unique(), reverse=True)
    an_ales = r2.selectbox("An de raportare", ["Toți anii"] + ani_rvc, key="rvc_an")
    vedere = rvc
    if alese:
        vedere = vedere[vedere["partid"].isin(alese)]
    if an_ales != "Toți anii":
        vedere = vedere[vedere["an"] == an_ales]
    st.caption(f"{fmt_int(len(vedere))} rapoarte din {fmt_int(len(rvc))}.")
    tabel(
        vedere.sort_values(["an", "partid"], ascending=[False, True])[
            ["partid", "an", "venituri", "cotizatii", "donatii", "alte_venituri", "imprumuturi",
             "data_publicare", "reprezentant_legal", "url"]],
        use_container_width=True, hide_index=True,
        column_config={
            "partid": st.column_config.TextColumn("Partid", width="medium"),
            "an": st.column_config.NumberColumn("An", format="%d"),
            "venituri": st.column_config.NumberColumn(
                "Venituri (lei)", format="localized",
                help="Cotizații + donații + venituri din alte surse. Fără subvenția de la stat și fără împrumuturi."),
            "cotizatii": st.column_config.NumberColumn("Cotizații", format="localized"),
            "donatii": st.column_config.NumberColumn("Donații", format="localized"),
            "alte_venituri": st.column_config.NumberColumn(
                "Alte venituri", format="localized", help="Chirii, dobânzi, vânzări și alte surse (art. 16)."),
            "imprumuturi": st.column_config.NumberColumn("Împrumuturi primite", format="localized"),
            "data_publicare": st.column_config.TextColumn("Publicat"),
            "reprezentant_legal": st.column_config.TextColumn("Reprezentant legal"),
            "url": st.column_config.LinkColumn("Document", display_text="deschide"),
        },
    )

# ---------------- afiliere politică în conducerea SOE ----------------
if guv.get("numiri"):
    st.divider()
    st.markdown("#### Afiliere politică în conducerea companiilor de stat")
    st.caption(f"Sursă: {ui.GUV_SURSA} · registru generat la {str(guv.get('source_generated_at'))[:10]}. "
               "Afilierea e cea declarată în registrul oficial.")
    partide_soe = [k for k in guv_afil if k not in ("Fără apartenență politică", "nedeclarat")]
    if partide_soe:
        alege = st.selectbox("Partid", partide_soe,
                             format_func=lambda k: f"{k} — {guv_afil[k]} persoane")
        ui.guvernanta_numiri([n for n in guv["numiri"] if n.get("partid") == alege], key="guv_partid")
st.caption("Surse: subvenții de la bugetul de stat (date Expert Forum, banipartide.ro) și rapoartele de venituri/cheltuieli ale partidelor. "
           "Numărul de deputați/senatori reflectă mandatul curent.")
