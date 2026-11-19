"""Parlament — moțiuni (simple și de cenzură) și listele curente de deputați și senatori."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import sys as _sys, pathlib as _pl  # bootstrap: import 'app' fără PYTHONPATH (rulare directă/deploy)
for _a in _pl.Path(__file__).resolve().parents:
    if (_a / 'app').is_dir():
        _sys.path.insert(0, str(_a)); break

from app import data
from app.theme import (ACCENT, ACCENT_2, apply_theme, fmt_int, kpi_card, page_header,
                       party_color, sidebar_brand, tabel)

st.set_page_config(page_title="Parlament · SOLOMONAR", layout="wide")
apply_theme()
sidebar_brand()
page_header("Parlament",
            "Moțiunile depuse din legislatura 2000 încoace și componența actuală a Camerei Deputaților și a Senatului.")

TIP_MOTIUNE = {"cenzura": "de cenzură", "simpla_cdep": "simplă (Camera Deputaților)"}
PARTID_SCURT = (("Social Democrat", "PSD"), ("Național Liberal", "PNL"), ("Naţional Liberal", "PNL"),
                ("Salvați România", "USR"), ("Salvaţi România", "USR"), ("Unirea Românilor", "AUR"),
                ("Democrată Maghiară", "UDMR"), ("S.O.S.", "SOS"), ("Oamenilor Tineri", "POT"),
                ("minorităților", "Minorități"), ("Minorităţilor", "Minorități"))


def partid_scurt(nume) -> str:
    """Sigla partidului din numele lung al partidului sau al grupului parlamentar."""
    text = str(nume or "")
    for fragment, sigla in PARTID_SCURT:
        if fragment.lower() in text.lower():
            return sigla
    return "Neafiliați" if not text.strip() or "neafilia" in text.lower() else "Altele"


def bare_partide(df: pd.DataFrame, coloana: str) -> None:
    """Bare orizontale cu numărul de parlamentari pe partid."""
    numar = df[coloana].value_counts().sort_values()
    fig = go.Figure(go.Bar(x=numar.values, y=numar.index, orientation="h",
                           marker_color=[party_color(p) for p in numar.index],
                           text=numar.values, textposition="auto",
                           hovertemplate="<b>%{y}</b><br>%{x} mandate<extra></extra>"))
    fig.update_layout(height=max(220, 34 * len(numar)), margin=dict(l=90, r=20, t=10, b=30),
                      xaxis_title="mandate")
    st.plotly_chart(fig, width="stretch")


CAM_DEPUTATI = 2          # codul Camerei Deputaților în linkurile cdep.ro (1 = Senat)


@st.cache_data(show_spinner=False)
def partide_pe_idm(leg: int) -> dict:
    """idm deputat -> sigla partidului, pentru legislatura curentă (singura cu listă publicată)."""
    dep = data.deputati_df()
    if dep.empty or "legislatura" not in dep.columns:
        return {}
    dep = dep[dep["legislatura"] == leg]
    return dict(zip(dep["cdep_idm"], dep["current_party"].map(partid_scurt)))


def clasament_semnatari(motiuni: pd.DataFrame, partide: dict) -> pd.DataFrame:
    """Câte moțiuni a semnat fiecare parlamentar într-o legislatură (total și de cenzură)."""
    rows = [{"cam": s.get("cam"), "idm": s["idm"], "nume": s["nume"], "cenzura": m["tip"] == "cenzura"}
            for _, m in motiuni.iterrows() if isinstance(m["semnatari"], list) for s in m["semnatari"]]
    if not rows:
        return pd.DataFrame()
    d = pd.DataFrame(rows)
    out = d.groupby(["cam", "idm", "nume"], as_index=False, dropna=False).agg(
        motiuni=("cenzura", "size"), cenzura=("cenzura", "sum"))
    out["partid"] = [partide.get(i, "—") if c == CAM_DEPUTATI else "senator" for i, c in zip(out["idm"], out["cam"])]
    return out.sort_values(["motiuni", "nume"], ascending=[False, True])[["nume", "partid", "motiuni", "cenzura"]]


tab_motiuni, tab_deputati, tab_senatori = st.tabs(["Moțiuni", "Deputați", "Senatori"])

# ============================================================ MOȚIUNI
with tab_motiuni:
    mot = data.motiuni_df()
    if mot.empty:
        st.info("Nu există date despre moțiuni.")
    else:
        mot = mot.copy()
        mot["tip_text"] = mot["tip"].map(TIP_MOTIUNE).fillna(mot["tip"])
        mot["rezultat"] = mot["rezultat"].replace({"Respinsa": "Respinsă"})
        adoptate = mot["rezultat"].eq("Adoptată")
        c1, c2, c3, c4 = st.columns(4)
        kpi_card(c1, "Moțiuni", fmt_int(len(mot)))
        kpi_card(c2, "De cenzură", fmt_int(mot["tip"].eq("cenzura").sum()))
        kpi_card(c3, "Simple", fmt_int(mot["tip"].eq("simpla_cdep").sum()))
        kpi_card(c4, "Adoptate", fmt_int(adoptate.sum()),
                 help="Moțiuni cu rezultatul „Adoptată” în evidența Camerei Deputaților.")

        st.markdown("#### Moțiuni pe legislatură")
        pe_leg = mot.groupby(["leg", "tip_text"]).size().unstack(fill_value=0).sort_index()
        fig = go.Figure()
        for tip, culoare in zip(pe_leg.columns, (ACCENT_2, ACCENT)):
            fig.add_trace(go.Bar(x=pe_leg.index.astype(str), y=pe_leg[tip], name=tip, marker_color=culoare))
        fig.update_layout(barmode="stack", height=320, xaxis_title="legislatura (anul de început)",
                          yaxis_title="moțiuni", legend=dict(orientation="h", y=1.14),
                          margin=dict(l=50, r=20, t=30, b=40))
        st.plotly_chart(fig, width="stretch")

        st.markdown("#### Lista moțiunilor")
        f1, f2, f3 = st.columns([1, 1, 2])
        tip_ales = f1.selectbox("Tip", ["Toate"] + sorted(mot["tip_text"].unique()), key="mot_tip")
        leg_aleasa = f2.selectbox("Legislatură", ["Toate"] + sorted(mot["leg"].dropna().unique(), reverse=True),
                                  key="mot_leg")
        cautare = f3.text_input("Caută în titlu", placeholder="ex: buget, sănătate, guvern", key="mot_q")
        vedere = mot
        if tip_ales != "Toate":
            vedere = vedere[vedere["tip_text"] == tip_ales]
        if leg_aleasa != "Toate":
            vedere = vedere[vedere["leg"] == leg_aleasa]
        if cautare.strip():
            vedere = vedere[vedere["titlu"].str.contains(cautare.strip(), case=False, na=False, regex=False)]
        st.caption(f"{fmt_int(len(vedere))} moțiuni din {fmt_int(len(mot))}.")
        tabel(
            vedere.sort_values("data_iso", ascending=False, na_position="last")[
                ["data", "titlu", "tip_text", "leg", "rezultat", "voturi_pentru", "voturi_contra",
                 "nr_semnatari", "url", "pdf_url"]],
            use_container_width=True, hide_index=True,
            column_config={
                "data": st.column_config.TextColumn("Data"),
                "titlu": st.column_config.TextColumn("Titlu", width="large"),
                "tip_text": st.column_config.TextColumn("Tip"),
                "leg": st.column_config.NumberColumn("Legislatură", format="%d"),
                "rezultat": st.column_config.TextColumn("Rezultat"),
                "voturi_pentru": st.column_config.NumberColumn("Pentru", format="%d"),
                "voturi_contra": st.column_config.NumberColumn("Contra", format="%d"),
                "nr_semnatari": st.column_config.NumberColumn("Semnatari", format="%d"),
                "url": st.column_config.LinkColumn("Pagina", display_text="cdep.ro"),
                "pdf_url": st.column_config.LinkColumn("Text", display_text="PDF"),
            },
        )
        st.caption("Sursă: cdep.ro. „Dezbatere” înseamnă că evidența nu consemnează un vot final; "
                   "voturile lipsesc la moțiunile vechi.")

        # ---------------- detaliul unei moțiuni: semnatari + text
        st.markdown("#### O moțiune în detaliu")
        ordonate = vedere.sort_values("data_iso", ascending=False, na_position="last")
        if ordonate.empty:
            st.caption("Nicio moțiune nu se potrivește filtrelor de mai sus.")
        else:
            aleasa = st.selectbox(
                "Moțiune", ordonate.index,
                format_func=lambda i: f"{ordonate.at[i, 'data'] or 'fără dată'} — {ordonate.at[i, 'titlu'][:110]}",
                key="mot_detaliu")
            m = ordonate.loc[aleasa]
            semnatari = pd.DataFrame(m["semnatari"] if isinstance(m["semnatari"], list) else [])
            k1, k2, k3 = st.columns(3)
            kpi_card(k1, "Rezultat", m["rezultat"] or "—")
            kpi_card(k2, "Semnatari", fmt_int(len(semnatari)))
            kpi_card(k3, "Voturi pentru / contra",
                     f"{fmt_int(m['voturi_pentru']) if pd.notna(m['voturi_pentru']) else '—'} / "
                     f"{fmt_int(m['voturi_contra']) if pd.notna(m['voturi_contra']) else '—'}")
            if isinstance(m.get("initiatori"), str) and m["initiatori"].strip():
                st.caption(f"Inițiată de: {m['initiatori']}")
            if not semnatari.empty:
                partide = partide_pe_idm(int(m["leg"]))
                # identificatorii senatorilor (cam=1) sunt din altă evidență decât ai deputaților
                semnatari["partid"] = [partide.get(i, "necunoscut") if c == CAM_DEPUTATI else "senator"
                                       for i, c in zip(semnatari["idm"], semnatari["cam"])]
                if partide:
                    bare_partide(semnatari, "partid")
                tabel(semnatari.sort_values(["partid", "nume"])[["nume", "partid"]],
                      use_container_width=True, hide_index=True, height=320,
                      column_config={"nume": st.column_config.TextColumn("Semnatar"),
                                     "partid": st.column_config.TextColumn("Partid")})
                if not partide:
                    st.caption("Partidul e disponibil doar pentru legislatura curentă.")
            text = data.motiune_text(int(m["idm"]), int(m["leg"]), int(m["cam"]))
            if text.get("text"):
                with st.expander(f"Textul moțiunii ({fmt_int(text.get('pagini'))} pagini)"):
                    st.caption("Text citit automat din documentul scanat; poate conține erori de recunoaștere."
                               + (" Doar primele pagini au fost citite." if text.get("trunchiat") else ""))
                    st.text(text["text"])

        # ---------------- cine semnează cel mai des
        st.markdown("#### Cine semnează cel mai des")
        leg_clasament = st.selectbox("Legislatura", sorted(mot["leg"].dropna().unique(), reverse=True),
                                     key="mot_clasament")
        clasament = clasament_semnatari(mot[mot["leg"] == leg_clasament], partide_pe_idm(int(leg_clasament)))
        if clasament.empty:
            st.caption("Nu există semnatari înregistrați pentru această legislatură.")
        else:
            st.caption(f"{fmt_int(len(clasament))} parlamentari au semnat cel puțin o moțiune din cele "
                       f"{fmt_int((mot['leg'] == leg_clasament).sum())} ale legislaturii.")
            tabel(clasament.head(50), use_container_width=True, hide_index=True,
                  column_config={"nume": st.column_config.TextColumn("Parlamentar"),
                                 "partid": st.column_config.TextColumn("Partid"),
                                 "motiuni": st.column_config.NumberColumn("Moțiuni semnate", format="%d"),
                                 "cenzura": st.column_config.NumberColumn("din care de cenzură", format="%d")})

# ============================================================ DEPUTAȚI
with tab_deputati:
    dep = data.deputati_df()
    if dep.empty:
        st.info("Nu există lista deputaților.")
    else:
        dep = dep.copy()
        dep["partid"] = dep["current_party"].map(partid_scurt)
        c1, c2, c3 = st.columns(3)
        kpi_card(c1, "Deputați", fmt_int(len(dep)))
        kpi_card(c2, "Partide și grupuri", fmt_int(dep["partid"].nunique()))
        kpi_card(c3, "Județe", fmt_int(dep["judet"].nunique()))
        bare_partide(dep, "partid")

        d1, d2, d3 = st.columns([1, 1, 2])
        partid_ales = d1.selectbox("Partid", ["Toate"] + sorted(dep["partid"].unique()), key="dep_partid")
        judet_ales = d2.selectbox("Județ", ["Toate"] + sorted(dep["judet"].dropna().unique()), key="dep_judet")
        nume_cautat = d3.text_input("Caută după nume", key="dep_q")
        vedere = dep
        if partid_ales != "Toate":
            vedere = vedere[vedere["partid"] == partid_ales]
        if judet_ales != "Toate":
            vedere = vedere[vedere["judet"] == judet_ales]
        if nume_cautat.strip():
            vedere = vedere[vedere["name"].str.contains(nume_cautat.strip(), case=False, na=False, regex=False)]
        st.caption(f"{fmt_int(len(vedere))} deputați din {fmt_int(len(dep))}.")
        tabel(
            vedere.sort_values("name")[["name", "partid", "judet", "circumscriptie", "current_group", "profile_url"]],
            use_container_width=True, hide_index=True,
            column_config={
                "name": st.column_config.TextColumn("Nume"),
                "partid": st.column_config.TextColumn("Partid"),
                "judet": st.column_config.TextColumn("Județ"),
                "circumscriptie": st.column_config.NumberColumn("Circumscripție", format="%d"),
                "current_group": st.column_config.TextColumn("Grup parlamentar și funcție", width="large"),
                "profile_url": st.column_config.LinkColumn("Profil", display_text="cdep.ro"),
            },
        )
        st.caption("Sursă: cdep.ro, legislatura 2024. Declarațiile, firmele și CV-ul fiecărui deputat "
                   "sunt în pagina Persoane.")

# ============================================================ SENATORI
with tab_senatori:
    sen = data.senatori_df()
    if sen.empty:
        st.info("Nu există lista senatorilor.")
    else:
        sen = sen.copy()
        sen["partid"] = sen["party"].map(partid_scurt)
        c1, c2 = st.columns(2)
        kpi_card(c1, "Senatori", fmt_int(len(sen)))
        kpi_card(c2, "Partide și grupuri", fmt_int(sen["partid"].nunique()))
        bare_partide(sen, "partid")

        s1, s2 = st.columns([1, 2])
        partid_sen = s1.selectbox("Partid", ["Toate"] + sorted(sen["partid"].unique()), key="sen_partid")
        nume_sen = s2.text_input("Caută după nume", key="sen_q")
        vedere = sen
        if partid_sen != "Toate":
            vedere = vedere[vedere["partid"] == partid_sen]
        if nume_sen.strip():
            vedere = vedere[vedere["name"].str.contains(nume_sen.strip(), case=False, na=False, regex=False)]
        st.caption(f"{fmt_int(len(vedere))} senatori din {fmt_int(len(sen))}.")
        tabel(
            vedere.sort_values("name")[["name", "partid", "party", "profile_url"]],
            use_container_width=True, hide_index=True,
            column_config={
                "name": st.column_config.TextColumn("Nume"),
                "partid": st.column_config.TextColumn("Partid"),
                "party": st.column_config.TextColumn("Grup parlamentar", width="large"),
                "profile_url": st.column_config.LinkColumn("Profil", display_text="senat.ro"),
            },
        )
        st.caption("Sursă: senat.ro, legislatura 2024. Județul nu este publicat în lista Senatului.")
