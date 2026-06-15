"""Persoane — căutare/filtrare în graful de persoane SOLOMONAR (56k) + fișă detaliu."""

from __future__ import annotations

import html
import re

import pandas as pd
import streamlit as st

from app import data, ui
from app.theme import (ACCENT, ACCENT_2, CONF_COLORS, TEXT_DIM, apply_theme,
                       fmt_int, fmt_lei, kpi_card, page_header, party_color,
                       sidebar_brand)

st.set_page_config(page_title="Persoane · SOLOMONAR", page_icon="📋", layout="wide")
apply_theme()
sidebar_brand()
page_header("Persoane",
            "Caută în cele 56.296 de persoane din graf: parlamentari, administratori de "
            "companii, declaranți de avere. Filtrează și deschide fișa individuală.")

# ---- nivel de încredere: etichete lizibile ----
CONF_LABEL = {"high": "🟢 High", "context": "🔵 Context", "candidat": "⚪ Candidat"}
CONF_DESC = {
    "high": "legătură puternic confirmată (mandat parlamentar / sursă oficială)",
    "context": "legătură susținută de context (instituție, declarații)",
    "candidat": "potrivire pe nume — neverificată, posibil omonim",
}


def conf_badge(level: str) -> str:
    c = CONF_COLORS.get(level, TEXT_DIM)
    lab = CONF_LABEL.get(level, level or "—")
    return (f"<span style='background:{c}22;border:1px solid {c};color:{c};"
            f"padding:2px 10px;border-radius:999px;font-size:12px;font-weight:600'>"
            f"{lab}</span>")


def clean_text(s: str) -> str:
    """CV-urile conțin entități HTML (&#536; etc.) și fragmente JS — curățăm pentru afișare."""
    if not s:
        return ""
    s = html.unescape(str(s))
    s = re.sub(r"function\s+\w+\([^)]*\)\s*\{?", "", s)  # scoate snippet-uri JS
    s = s.replace("|", " · ")
    return re.sub(r"\s{2,}", " ", s).strip(" ·\t\n")


df = data.persoane_df()

if df.empty:
    st.warning("Nu există date despre persoane (graf/persoane_gold.json lipsește).")
    st.stop()

# ============================ KPI ============================
parl = df[df["camera"].notna()]
c1, c2, c3, c4 = st.columns(4)
kpi_card(c1, "Persoane în graf", fmt_int(len(df)))
kpi_card(c2, "Parlamentari", fmt_int(len(parl)))
kpi_card(c3, "Cu companii conduse", fmt_int(int((df["n_companii"] > 0).sum())))
kpi_card(c4, "Cu contracte de stat", fmt_int(int((df["contracte_ron"] > 0).sum())))

st.divider()

# ============================ FILTRE ============================
st.markdown("#### Filtre")
fc1, fc2, fc3 = st.columns([2, 1, 1])
with fc1:
    q = st.text_input("Caută după nume", placeholder="ex: Popescu, Ion…").strip()
with fc2:
    conf_opt = st.selectbox("Nivel de încredere", ["Toate", "high", "context", "candidat"],
                            format_func=lambda x: x if x == "Toate" else CONF_LABEL.get(x, x))
with fc3:
    camera_opt = st.selectbox("Cameră", ["Toate", "deputat", "senator", "fără mandat"])

fc4, fc5, fc6 = st.columns([2, 1, 1])
with fc4:
    partide = sorted(df["partid"].dropna().unique().tolist())
    partid_opt = st.selectbox("Partid", ["Toate"] + partide)
with fc5:
    cv_opt = st.selectbox("Are CV", ["Toate", "Da", "Nu"])
with fc6:
    only_links = st.selectbox("Doar cu…", ["Toate", "companii", "contracte"])

# aplică filtrele
f = df
if q:
    f = f[f["nume"].str.contains(re.escape(q), case=False, na=False)]
if conf_opt != "Toate":
    f = f[f["incredere"] == conf_opt]
if camera_opt == "fără mandat":
    f = f[f["camera"].isna()]
elif camera_opt != "Toate":
    f = f[f["camera"] == camera_opt]
if partid_opt != "Toate":
    f = f[f["partid"] == partid_opt]
if cv_opt == "Da":
    f = f[f["are_cv"]]
elif cv_opt == "Nu":
    f = f[~f["are_cv"]]
if only_links == "companii":
    f = f[f["n_companii"] > 0]
elif only_links == "contracte":
    f = f[f["contracte_ron"] > 0]

# ============================ SORTARE + TABEL ============================
sc1, sc2 = st.columns([2, 1])
SORT_FIELDS = {
    "Contracte de stat (lei)": "contracte_ron",
    "Companii conduse": "n_companii",
    "Declarații": "n_declaratii",
    "Proiecte inițiate (PLx)": "plx_initiate",
    "Comisii": "comisii",
    "Nume (A→Z)": "nume",
}
with sc1:
    sort_label = st.selectbox("Sortează după", list(SORT_FIELDS.keys()))
with sc2:
    asc = st.toggle("Crescător", value=(sort_label == "Nume (A→Z)"))

sort_col = SORT_FIELDS[sort_label]
f = f.sort_values(sort_col, ascending=asc, na_position="last")

st.caption(f"**{fmt_int(len(f))}** persoane găsite "
           f"(din {fmt_int(len(df))}). Se afișează maxim 1.000 de rânduri în tabel.")

view = f.head(1000).copy()
view["încredere"] = view["incredere"].map(CONF_LABEL).fillna(view["incredere"])
view["are_cv"] = view["are_cv"].map({True: "✓", False: ""})
show = view[["nume", "încredere", "camera", "partid", "judet",
             "n_declaratii", "n_companii", "contracte_ron",
             "comisii", "plx_initiate", "are_cv"]]

st.dataframe(
    show, use_container_width=True, hide_index=True, height=420,
    column_config={
        "nume": st.column_config.TextColumn("Nume", width="medium"),
        "încredere": st.column_config.TextColumn("Încredere"),
        "camera": st.column_config.TextColumn("Cameră"),
        "partid": st.column_config.TextColumn("Partid", width="medium"),
        "judet": st.column_config.TextColumn("Județ"),
        "n_declaratii": st.column_config.NumberColumn("Declarații", format="%d"),
        "n_companii": st.column_config.NumberColumn("Companii", format="%d"),
        "contracte_ron": st.column_config.NumberColumn("Contracte (lei)", format="%.0f"),
        "comisii": st.column_config.NumberColumn("Comisii", format="%d"),
        "plx_initiate": st.column_config.NumberColumn("PLx", format="%d"),
        "are_cv": st.column_config.TextColumn("CV"),
    },
)

st.divider()

# ============================ FIȘĂ DETALIU ============================
st.markdown("#### Fișă persoană")

if f.empty:
    st.info("Niciun rezultat. Relaxează filtrele pentru a deschide o fișă.")
    st.stop()

opts = f.head(1000)
# etichetă lizibilă în selector
labels = {}
for _, r in opts.iterrows():
    extra = []
    cam = r["camera"]
    if isinstance(cam, str) and cam.strip():
        extra.append(cam.strip())
    par = r["partid"]
    if isinstance(par, str) and par.strip():
        extra.append(par.strip()[:28])
    suffix = f"  ·  {' · '.join(extra)}" if extra else ""
    labels[r["romega_id"]] = f"{r['nume']}{suffix}"

sel_id = st.selectbox(
    "Alege o persoană din rezultatele filtrate",
    options=list(labels.keys()),
    format_func=lambda i: labels.get(i, i),
)

p = data.persoana(sel_id)
if not p:
    st.warning("Detaliile acestei persoane nu au putut fi încărcate.")
    st.stop()

nume = (p.get("nume_key") or "").title()
incr = p.get("incredere")
pl = p.get("parlamentar") or {}

# antet fișă
st.markdown(
    f"<div style='display:flex;align-items:center;gap:14px;margin:6px 0 2px'>"
    f"<span style='font-size:22px;font-weight:700;color:#e6e8ee'>{html.escape(nume)}</span>"
    f"{conf_badge(incr)}</div>",
    unsafe_allow_html=True,
)
st.caption(CONF_DESC.get(incr, ""))

# KPI fișă
d1, d2, d3, d4 = st.columns(4)
kpi_card(d1, "Declarații", fmt_int(p.get("n_declaratii", 0)))
kpi_card(d2, "Companii conduse", fmt_int(p.get("n_companii", 0)))
kpi_card(d3, "Contracte de stat", fmt_lei(p.get("total_contracte_ron") or 0))
kpi_card(d4, "Firme cu contracte", fmt_int(p.get("n_firme_cu_contracte", 0)))

# --- mandat parlamentar ---
if pl:
    pc = party_color(pl.get("partid", ""))
    chips = []
    if pl.get("camera"):
        chips.append(("Cameră", pl["camera"].capitalize(), ACCENT_2))
    if pl.get("partid"):
        chips.append(("Partid", pl["partid"], pc))
    if pl.get("judet"):
        chips.append(("Județ", pl["judet"], TEXT_DIM))
    if pl.get("legislatura"):
        chips.append(("Legislatură", str(pl["legislatura"]), TEXT_DIM))
    chips.append(("Comisii", fmt_int(len(pl.get("comisii") or [])), ACCENT))
    chips.append(("Proiecte (PLx)", fmt_int(pl.get("plx_initiate") or 0), ACCENT))

    st.markdown("##### Mandat parlamentar")
    html_chips = "".join(
        f"<span style='display:inline-block;margin:0 8px 8px 0;background:#141821;"
        f"border:1px solid #232838;border-radius:10px;padding:6px 12px'>"
        f"<span style='color:#8a92a6;font-size:11px'>{lbl}</span><br>"
        f"<span style='color:{col};font-weight:600;font-size:14px'>{html.escape(str(val))}</span>"
        f"</span>"
        for lbl, val, col in chips
    )
    st.markdown(f"<div>{html_chips}</div>", unsafe_allow_html=True)

    comisii = pl.get("comisii") or []
    if comisii:
        with st.expander(f"Comisii ({len(comisii)})"):
            for cm in comisii:
                if isinstance(cm, dict):
                    nm = cm.get("nume") or cm.get("comisie") or ""
                    rol = cm.get("rol")
                    st.markdown(f"- {html.escape(str(nm))}" + (f" — *{rol}*" if rol else ""))
                else:
                    st.markdown(f"- {html.escape(str(cm))}")

st.markdown("")
left, right = st.columns(2)

# --- declarații (instituții) ---
with left:
    st.markdown("##### Declarații de avere / interese")
    decl = p.get("declaratii") or []
    if decl:
        ddf = pd.DataFrame(decl)
        for c in ("tip", "institutie", "venituri_ron"):
            if c not in ddf.columns:
                ddf[c] = None
        st.dataframe(
            ddf[["tip", "institutie", "venituri_ron"]],
            use_container_width=True, hide_index=True,
            column_config={
                "tip": st.column_config.TextColumn("Tip"),
                "institutie": st.column_config.TextColumn("Instituție", width="medium"),
                "venituri_ron": st.column_config.NumberColumn("Venituri (lei)", format="%.0f"),
            },
        )
    else:
        st.caption("Fără declarații înregistrate.")

# --- companii conduse ---
with right:
    st.markdown("##### Companii conduse")
    comp = p.get("companii") or []
    if comp:
        rows = []
        for c in comp:
            cs = c.get("contracte_stat") or {}
            rows.append({
                "firmă": c.get("nume"),
                "rol": c.get("rol"),
                "sector": c.get("sector") or "—",
                "contracte_lei": cs.get("total_ron"),
                "nr_contracte": cs.get("nr"),
            })
        cdf = pd.DataFrame(rows).sort_values("contracte_lei", ascending=False, na_position="last")
        st.dataframe(
            cdf, use_container_width=True, hide_index=True,
            column_config={
                "firmă": st.column_config.TextColumn("Firmă", width="medium"),
                "rol": st.column_config.TextColumn("Rol"),
                "sector": st.column_config.TextColumn("Sector"),
                "contracte_lei": st.column_config.NumberColumn("Contracte (lei)", format="%.0f"),
                "nr_contracte": st.column_config.NumberColumn("Nr.", format="%d"),
            },
        )
    else:
        st.caption("Nu apare ca administrator/asociat la nicio companie.")

# --- contracte & achiziții ale unei firme conduse (component comun, full-width) ---
firme_cu_cui = [c for c in (p.get("companii") or []) if c.get("cui")]
if firme_cu_cui:
    st.markdown("##### Contracte & achiziții ale unei firme conduse")
    opts = {f"{(c.get('nume') or '').strip()} · CUI {c.get('cui')}": c.get("cui")
            for c in firme_cu_cui}
    pick = st.selectbox("Alege firma", list(opts.keys()), key="pers_firma_bani")
    if not ui.firma_bani_stat(opts[pick]):
        st.caption("Această firmă nu are contracte sau achiziții directe înregistrate în set.")

# --- conflicte confirmate: firme din propria declarație de interese cu contracte de stat ---
fa = p.get("firme_contracte_autodeclarate") or []
if fa:
    st.markdown("##### ⚠️ Firme autodeclarate cu contracte de stat")
    st.caption("Firme menționate chiar în declarația de interese a persoanei și care au "
               "câștigat contracte publice — legătură defensabilă (nu doar potrivire pe nume).")
    fadf = pd.DataFrame(fa).sort_values("total_ron", ascending=False, na_position="last")
    keep = [c for c in ("cui", "nume", "total_ron") if c in fadf.columns]
    st.dataframe(
        fadf[keep], use_container_width=True, hide_index=True,
        column_config={
            "cui": st.column_config.TextColumn("CUI"),
            "nume": st.column_config.TextColumn("Firmă", width="medium"),
            "total_ron": st.column_config.NumberColumn("Contracte (lei)", format="%.0f"),
        },
    )

# --- CV ---
cv = p.get("cv") or {}
studii = clean_text(cv.get("studii", "")) if isinstance(cv, dict) else ""
exp = clean_text(cv.get("experienta", "")) if isinstance(cv, dict) else ""
if studii or exp:
    with st.expander("CV — studii & experiență"):
        if studii:
            st.markdown("**Studii**")
            st.write(studii)
        if exp:
            st.markdown("**Experiență**")
            st.write(exp)
elif not p.get("are_cv"):
    st.caption("Fără CV disponibil pentru această persoană.")
