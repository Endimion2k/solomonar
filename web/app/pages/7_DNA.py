"""SOLOMONAR · DNA — comunicate publice DNA (8.998). Căutare text, filtru an, link sursă.

PREZUMȚIA DE NEVINOVĂȚIE: comunicatele DNA descriu trimiteri în judecată / urmăriri penale,
NU condamnări definitive. Orice persoană este nevinovată până la o hotărâre judecătorească definitivă.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import sys as _sys, pathlib as _pl  # bootstrap: import 'app' fără PYTHONPATH (rulare directă/deploy)
for _a in _pl.Path(__file__).resolve().parents:
    if (_a / 'app').is_dir():
        _sys.path.insert(0, str(_a)); break

from app import data
from app.theme import (ACCENT, ACCENT_2, DANGER, TEXT_DIM, WARNING, apply_theme,
                       fmt_int, kpi_card, page_header, sidebar_brand)

st.set_page_config(page_title="DNA · SOLOMONAR", page_icon="⚖️", layout="wide")
apply_theme()
sidebar_brand()

page_header("Comunicate DNA",
            "Comunicate publice ale Direcției Naționale Anticorupție. Căutare în titlu și "
            "în numele extrase. Date publice, agregate din sursa oficială.")

st.warning(
    "**Prezumția de nevinovăție.** Comunicatele DNA se referă la trimiteri în judecată, "
    "rechizitorii și măsuri procesuale — **nu** la condamnări definitive. Orice persoană "
    "menționată este nevinovată până la o hotărâre judecătorească definitivă.",
    icon="⚖️",
)

df = data.dna_df()

if df.empty:
    st.info("Nu există comunicate DNA în setul de date.")
    st.stop()

# ---- normalizare ----
df = df.copy()
for col in ("titlu", "nr", "url", "data"):
    if col not in df.columns:
        df[col] = ""
    df[col] = df[col].fillna("").astype(str).str.strip()
if "nume_extrase" not in df.columns:
    df["nume_extrase"] = [[] for _ in range(len(df))]
df["nume_extrase"] = df["nume_extrase"].apply(lambda x: x if isinstance(x, list) else [])
df["nume_join"] = df["nume_extrase"].apply(lambda lst: " ; ".join(str(n) for n in lst))
df["an_int"] = pd.to_numeric(df.get("an"), errors="coerce")

# ---- KPI ----
ani_valide = df["an_int"].dropna()
an_min = int(ani_valide.min()) if not ani_valide.empty else None
an_max = int(ani_valide.max()) if not ani_valide.empty else None
c1, c2, c3, c4 = st.columns(4)
kpi_card(c1, "Comunicate totale", fmt_int(len(df)))
kpi_card(c2, "Cu nume extrase", fmt_int(int((df["nume_extrase"].apply(len) > 0).sum())))
kpi_card(c3, "Interval ani", f"{an_min}–{an_max}" if an_min else "—")
kpi_card(c4, "Ani acoperiți", fmt_int(int(ani_valide.nunique())))

st.divider()

# ---- distribuție pe an ----
st.markdown("#### Comunicate pe an")
per_an = (df.dropna(subset=["an_int"]).groupby(df["an_int"].astype("Int64"))
          .size().reset_index(name="n").sort_values("an_int"))
if not per_an.empty:
    fig = go.Figure(go.Bar(x=per_an["an_int"].astype(int), y=per_an["n"], marker_color=ACCENT))
    fig.update_layout(height=260, xaxis_title="an", yaxis_title="comunicate",
                      xaxis=dict(dtick=2))
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# ---- filtre ----
st.markdown("#### Căutare și filtrare")
fc1, fc2 = st.columns([3, 1])
with fc1:
    q = st.text_input("Caută în titlu sau nume extrase",
                      placeholder="ex: primar, achiziții, abuz în serviciu, un nume…").strip()
with fc2:
    ani_optiuni = ["Toți anii"] + [str(a) for a in sorted(ani_valide.unique().astype(int), reverse=True)]
    an_sel = st.selectbox("An", ani_optiuni)

flt = df
if an_sel != "Toți anii":
    flt = flt[flt["an_int"] == int(an_sel)]
if q:
    ql = q.lower()
    mask = (flt["titlu"].str.lower().str.contains(ql, regex=False, na=False)
            | flt["nume_join"].str.lower().str.contains(ql, regex=False, na=False))
    flt = flt[mask]

st.caption(f"{fmt_int(len(flt))} comunicate găsite"
           + (f" · căutare: „{q}”" if q else "")
           + (f" · an {an_sel}" if an_sel != 'Toți anii' else ""))

# ---- tabel ----
if flt.empty:
    st.info("Niciun comunicat nu corespunde criteriilor. Încearcă alți termeni sau alt an.")
else:
    out = flt.sort_values("an_int", ascending=False, na_position="last").copy()
    out["titlu_scurt"] = out["titlu"].str.slice(0, 140).str.strip()
    out.loc[out["titlu"].str.len() > 140, "titlu_scurt"] += "…"
    out["an_afis"] = out["an_int"].apply(lambda v: str(int(v)) if pd.notna(v) else "—")
    show = out[["an_afis", "data", "nr", "titlu_scurt", "nume_join", "url"]].rename(columns={
        "an_afis": "an", "data": "dată", "nr": "nr.", "titlu_scurt": "titlu",
        "nume_join": "nume extrase", "url": "sursă",
    })
    st.dataframe(
        show.head(1000), use_container_width=True, hide_index=True,
        column_config={
            "an": st.column_config.TextColumn(width="small"),
            "dată": st.column_config.TextColumn(width="small"),
            "nr.": st.column_config.TextColumn(width="small"),
            "titlu": st.column_config.TextColumn(width="large"),
            "nume extrase": st.column_config.TextColumn(width="medium"),
            "sursă": st.column_config.LinkColumn("sursă DNA", display_text="deschide ↗"),
        },
    )
    if len(flt) > 1000:
        st.caption(f"Se afișează primele 1.000 din {fmt_int(len(flt))}. Restrânge cu căutare sau filtru de an.")

st.caption("Sursă: comunicatele publice DNA (dna.ro). Numele sunt extrase automat din text și "
           "pot conține zgomot (instituții, antete). Verifică întotdeauna comunicatul original prin link.")
