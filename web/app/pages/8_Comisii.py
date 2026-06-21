"""SOLOMONAR · Comisii & Legislativ — activitate recentă + comisiile Senatului + inițiatori PLx.

Trei tab-uri: (1) activitatea recentă a comisiilor Camerei Deputaților (ședințe din ultima lună,
PLx discutate + actele de bază), (2) componența comisiilor Senatului, (3) inițiatorii PLx.
"""

from __future__ import annotations

import collections

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import sys as _sys, pathlib as _pl  # bootstrap: import 'app' fără PYTHONPATH (rulare directă/deploy)
for _a in _pl.Path(__file__).resolve().parents:
    if (_a / 'app').is_dir():
        _sys.path.insert(0, str(_a)); break

from app import data
from app.theme import (ACCENT, ACCENT_2, WARNING, apply_theme,
                       fmt_int, kpi_card, page_header, sidebar_brand)

st.set_page_config(page_title="Comisii & Legislativ · SOLOMONAR", page_icon="🏛️", layout="wide")
apply_theme()
sidebar_brand()

page_header("Comisii & Legislativ",
            "Activitatea recentă a comisiilor Camerei Deputaților (ședințe + proiecte discutate), "
            "componența comisiilor Senatului și inițiatorii proiectelor legislative (PLx).")

# etichete + ordinea de afișare a tipurilor de documente la dosarul unui PLx
DOC_LABEL = {
    "forma_initiator": "📜 Forma inițiatorului", "expunere_motive": "📝 Expunere de motive",
    "aviz_consiliu_legislativ": "⚖️ Aviz Consiliul Legislativ", "punct_vedere_guvern": "🏛️ Punct de vedere Guvern",
    "sesizare": "✉️ Sesizare", "aviz_comisie": "✅ Aviz comisie", "raport": "📄 Raport",
    "raport_suplimentar": "📄 Raport suplimentar", "aviz_csm": "⚖️ Aviz CSM", "alt": "📎 Alt document"}
DOC_ORDER = ["forma_initiator", "expunere_motive", "aviz_consiliu_legislativ", "punct_vedere_guvern",
             "sesizare", "aviz_comisie", "raport", "raport_suplimentar", "aviz_csm", "alt"]


# ====================================================================
# TAB 1 — Activitate recentă a comisiilor (Camera Deputaților)
# ====================================================================
def _render_activitate() -> None:
    ac = data.comisii_recent()
    if not ac or not ac.get("sedinte"):
        st.warning("Nu există date de activitate recentă. Rulează `python -m pipeline.harvest_comisii` "
                   "apoi `python -m pipeline.build_comisii_recent`.")
        return

    per = ac.get("perioada", {})
    c1, c2, c3, c4 = st.columns(4)
    kpi_card(c1, "Ședințe", fmt_int(ac.get("n_sedinte")))
    kpi_card(c2, "Comisii active", fmt_int(ac.get("n_comisii_active")))
    kpi_card(c3, "PLx discutate (unice)", fmt_int(ac.get("n_plx_unice")))
    kpi_card(c4, "Perioada", f"{per.get('de_la', '')} → {per.get('pana_la', '')}")
    st.caption("„Acte de bază” = documentele fundamentale ale proiectului (forma inițiatorului, expunere "
               "de motive, aviz Consiliul Legislativ, punct de vedere Guvern), nu rapoartele comisiei.")

    sub_sed, sub_plx = st.tabs(["🗓️ Ședințe (cronologic)", "📜 PLx discutate + acte de bază"])

    with sub_sed:
        cf1, cf2 = st.columns([2, 1])
        q = cf1.text_input("Caută comisie sau PLx", placeholder="ex: sănătate, buget…",
                           key="act_q").strip().lower()
        doar_plx = cf2.checkbox("Doar ședințe cu PLx", value=True, key="act_doar")
        sed = ac["sedinte"]
        if doar_plx:
            sed = [s for s in sed if s.get("n_plx")]
        if q:
            sed = [s for s in sed if q in (s.get("comisie") or "").lower()
                   or any(q in (p.get("titlu") or "").lower() for p in s.get("plx", []))]
        st.caption(f"{fmt_int(len(sed))} ședințe afișate.")
        for s in sed[:80]:
            head = f"{s['data']} · {s['comisie']} · {s.get('n_plx', 0)} PLx"
            with st.expander(head):
                if s.get("agenda_url"):
                    st.markdown(f"📄 [Ordinea de zi (PDF)]({s['agenda_url']})")
                if not s.get("plx"):
                    st.caption("Agenda nu listează PLx (sau nu a putut fi parsată).")
                for p in s.get("plx", []):
                    line = f"- **[{p['titlu']}]({p['url']})**" if p.get("url") else f"- **{p['titlu']}**"
                    acte = p.get("acte_baza", [])
                    if acte:
                        line += ("  \n  ↳ *acte de bază:* "
                                 + " · ".join(f"[{a['tip']}]({a['url']})" for a in acte))
                    elif p.get("n_documente"):
                        line += f"  \n  ↳ *{p['n_documente']} documente la dosar (fără acte de bază marcate)*"
                    st.markdown(line)

    with sub_plx:
        st.caption("Proiectele discutate în perioadă (deduplicate), cu numărul de documente la dosar.")
        plx = ac.get("plx_unice", [])
        if not plx:
            st.info("Niciun PLx în perioadă.")
        else:
            rows = [{
                "PLx / titlu": p.get("titlu"),
                "Comisii": ", ".join(p.get("comisii", [])),
                "Acte de bază": ", ".join(a["tip"] for a in p.get("acte_baza", [])) or "—",
                "Documente": p.get("n_documente", 0),
                "Link": p.get("url"),
            } for p in plx]
            st.dataframe(
                pd.DataFrame(rows), use_container_width=True, hide_index=True, height=520,
                column_config={
                    "PLx / titlu": st.column_config.TextColumn(width="medium"),
                    "Comisii": st.column_config.TextColumn(width="medium"),
                    "Acte de bază": st.column_config.TextColumn(width="medium"),
                    "Documente": st.column_config.NumberColumn(format="%d"),
                    "Link": st.column_config.LinkColumn("cdep.ro", display_text="deschide"),
                })

    st.caption(f"Sursă: cdep.ro (ordini de zi comisii + dosare PLx). Generat: {ac.get('generat', '')}.")


# ====================================================================
# TAB 2 — Comisiile Senatului
# ====================================================================
def _render_senat() -> None:
    comisii = data.comisii_senat()
    if not comisii:
        st.info("Nu există comisii în setul de date.")
        return

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

    st.markdown("#### Mărimea comisiilor")
    ov = pd.DataFrame([{"comisie": c.get("nume", ""),
                        "membri": int(c.get("n_membri") or len(c.get("membri") or []))}
                       for c in comisii]).sort_values("membri", ascending=True)
    fig = go.Figure(go.Bar(x=ov["membri"], y=ov["comisie"], orientation="h", marker_color=ACCENT))
    fig.update_layout(height=max(320, 22 * len(ov)), xaxis_title="număr membri", margin=dict(l=10))
    st.plotly_chart(fig, use_container_width=True)


# ====================================================================
# TAB 3 — Inițiative legislative (PLx)
# ====================================================================
def _render_legislativ() -> None:
    plx = data.plx_initiatori_df()
    docmap = data.plx_docs_by_idp()
    if plx.empty:
        st.info("Nu există date PLx în setul de date.")
        return

    plx = plx.copy()
    for col in ("titlu", "idp"):
        if col not in plx.columns:
            plx[col] = ""
        plx[col] = plx[col].fillna("").astype(str)
    plx["guvern"] = plx.get("guvern", False).fillna(False).astype(bool)
    plx["n_initiatori"] = pd.to_numeric(plx.get("n_initiatori"), errors="coerce").fillna(0).astype(int)

    plx["nr_docs"] = plx["idp"].astype(str).map(lambda i: len(docmap.get(i, {}).get("documente", [])))

    n_guvern = int(plx["guvern"].sum())
    n_parl = len(plx) - n_guvern
    total_docs = int(plx["nr_docs"].sum())
    k1, k2, k3, k4 = st.columns(4)
    kpi_card(k1, "Proiecte PLx", fmt_int(len(plx)))
    kpi_card(k2, "Inițiative guvern", fmt_int(n_guvern), help=f"{n_guvern/len(plx)*100:.0f}% din total")
    kpi_card(k3, "Inițiative parlamentare", fmt_int(n_parl), help=f"{n_parl/len(plx)*100:.0f}% din total")
    kpi_card(k4, "Documente la dosar (total)", fmt_int(total_docs),
             help="Suma documentelor pentru toate cele "
                  f"{fmt_int((plx['nr_docs'] > 0).sum())} de proiecte cu dosar complet.")

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
        return

    out = flt.copy()
    out["tip"] = out["guvern"].map({True: "Guvern", False: "Parlamentar"})
    out["cdep"] = out["idp"].astype(str).map(
        lambda i: f"https://www.cdep.ro/ords/pls/proiecte/upl_pck2015.proiect?cam=2&idp={i}")
    show = out[["idp", "titlu", "tip", "n_initiatori", "nr_docs", "cdep"]].rename(columns={
        "idp": "id PLx", "titlu": "titlu", "tip": "sursă", "n_initiatori": "nr. inițiatori",
        "nr_docs": "documente", "cdep": "pagina",
    }).sort_values("nr. inițiatori", ascending=False)
    st.dataframe(
        show.head(1000), use_container_width=True, hide_index=True,
        column_config={
            "id PLx": st.column_config.TextColumn(width="small"),
            "titlu": st.column_config.TextColumn(width="large"),
            "sursă": st.column_config.TextColumn(width="small"),
            "nr. inițiatori": st.column_config.NumberColumn(format="%d", width="small"),
            "documente": st.column_config.NumberColumn(format="%d", width="small",
                                                       help="Documente la dosarul PLx (toate tipurile)."),
            "pagina": st.column_config.LinkColumn("cdep.ro", display_text="deschide", width="small"),
        },
    )
    if len(flt) > 1000:
        st.caption(f"Se afișează primele 1.000 din {fmt_int(len(flt))}.")

    # ---- dosarul complet al unui PLx (toate documentele, grupate pe tip) ----
    st.markdown("#### Dosarul unui proiect — toate documentele")
    opts = flt.sort_values("n_initiatori", ascending=False)
    labels = {f"{r['titlu']} · {int(r['nr_docs'])} documente": str(r["idp"])
              for _, r in opts.iterrows()}
    if not labels:
        st.caption("Niciun PLx în selecție.")
        return
    sel_lbl = st.selectbox("Alege un PLx din rezultatele filtrate", list(labels.keys()))
    idp = labels[sel_lbl]
    rec = docmap.get(idp, {})
    docs = rec.get("documente", [])
    cdep = f"https://www.cdep.ro/ords/pls/proiecte/upl_pck2015.proiect?cam=2&idp={idp}"
    st.markdown(f"**{rec.get('titlu', sel_lbl)}** · [pagina cdep.ro]({cdep}) · {len(docs)} documente")
    if not docs:
        st.caption("Fără documente la dosar pentru acest proiect.")
        return
    by_tip = collections.defaultdict(list)
    for d in docs:
        by_tip[d.get("tip", "alt")].append(d.get("url"))
    for tip in DOC_ORDER + [t for t in by_tip if t not in DOC_ORDER]:
        urls = by_tip.get(tip)
        if not urls:
            continue
        lbl = DOC_LABEL.get(tip, tip)
        if len(urls) == 1:
            links = f"[deschide]({urls[0]})"
        else:
            links = " · ".join(f"[{i + 1}]({u})" for i, u in enumerate(urls))
        st.markdown(f"- {lbl}: {links}")


tab_act, tab_sen, tab_leg = st.tabs([
    "🗓️ Activitate recentă (Camera)",
    "🏛️ Comisiile Senatului",
    "📜 Inițiative legislative (PLx)"])
with tab_act:
    _render_activitate()
with tab_sen:
    _render_senat()
with tab_leg:
    _render_legislativ()

st.divider()
st.caption("Sursă: cdep.ro (activitatea comisiilor Camerei) · componența comisiilor Senatului · "
           "fișele de inițiatori ale proiectelor legislative (PLx). Date publice agregate.")
