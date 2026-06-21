"""Activitate comisii (recentă) — ședințe din ultima lună, PLx discutate + actele de bază.

Sursă: data/v1/comisii/activitate_recenta.json (vezi pipeline/build_comisii_recent.py).
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

import sys as _sys, pathlib as _pl  # bootstrap: import 'app' fără PYTHONPATH (rulare directă/deploy)
for _a in _pl.Path(__file__).resolve().parents:
    if (_a / 'app').is_dir():
        _sys.path.insert(0, str(_a)); break

from app import data
from app.theme import TEXT_DIM, apply_theme, fmt_int, kpi_card, page_header, sidebar_brand

st.set_page_config(page_title="Activitate comisii · SOLOMONAR", page_icon="📋", layout="wide")
apply_theme()
sidebar_brand()
page_header("📋 Activitate comisii (recentă)",
            "Ședințele comisiilor Camerei Deputaților din ultima lună, proiectele (PLx) discutate și "
            "actele care au stat la baza lor (forma inițiatorului, expunere de motive, avize).")

ac = data.comisii_recent()
if not ac or not ac.get("sedinte"):
    st.warning("Nu există date de activitate recentă. Rulează `python -m pipeline.harvest_comisii` "
               "apoi `python -m pipeline.build_comisii_recent`.")
    st.stop()

per = ac.get("perioada", {})
c1, c2, c3, c4 = st.columns(4)
kpi_card(c1, "Ședințe", fmt_int(ac.get("n_sedinte")))
kpi_card(c2, "Comisii active", fmt_int(ac.get("n_comisii_active")))
kpi_card(c3, "PLx discutate (unice)", fmt_int(ac.get("n_plx_unice")))
kpi_card(c4, "Perioada", f"{per.get('de_la','')} → {per.get('pana_la','')}")

st.caption("„Acte de bază” = documentele fundamentale ale proiectului (forma inițiatorului, expunere de "
           "motive, aviz Consiliul Legislativ, punct de vedere Guvern), nu rapoartele comisiei.")

tab_sed, tab_plx = st.tabs(["🗓️ Ședințe (cronologic)", "📜 PLx discutate + acte de bază"])

# ---------------- ședințe ----------------
with tab_sed:
    cf1, cf2 = st.columns([2, 1])
    q = cf1.text_input("Caută comisie sau PLx", placeholder="ex: sănătate, buget…").strip().lower()
    doar_plx = cf2.checkbox("Doar ședințe cu PLx", value=True)

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

# ---------------- PLx unice ----------------
with tab_plx:
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

st.divider()
st.caption(f"Sursă: cdep.ro (ordini de zi comisii + dosare PLx). Generat: {ac.get('generat', '')}. "
           "Agenda fiecărei ședințe e PDF-ul oficial; actele de bază sunt linkuri directe la documentele PLx.")
