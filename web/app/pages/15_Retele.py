"""Rețele & inele — analiză de graf pe administratorii ONRC (SOLOMONAR).

Inele de control (firme cu administratori comuni), administratori-hub și firme-pod, calculate
offline cu igraph (vezi pipeline/build_network.py) și citite din data/v1/graf/network_metrics.json.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st
from st_link_analysis import EdgeStyle, NodeStyle, st_link_analysis

from app import data, ui
from app.theme import (ACCENT, DANGER, TEXT_DIM, WARNING, apply_theme, fmt_int,
                       fmt_lei, kpi_card, page_header, sidebar_brand)

st.set_page_config(page_title="Rețele & inele · SOLOMONAR", page_icon="🕸️", layout="wide")
apply_theme()
sidebar_brand()
page_header("🕸️ Rețele & inele",
            "Firme legate prin ADMINISTRATORI COMUNI (date reale ONRC) — grupuri de control, "
            "administratori-hub și firme-pod. Calcul de graf cu igraph.")

net = data.network_metrics()
if not net or not net.get("inele"):
    st.warning("Nu există date de rețea. Rulează `python -m pipeline.build_network`.")
    st.stop()

meta = net.get("meta", {})
inele = net.get("inele", [])
huburi = net.get("huburi", [])
poduri = net.get("poduri", [])

st.warning(net.get("disclaimer", ""), icon="⚠️")

# ---------------- KPI ----------------
c1, c2, c3, c4 = st.columns(4)
kpi_card(c1, "Companii în graf", fmt_int(meta.get("companii_in_graf")))
kpi_card(c2, "Inele de control", fmt_int(meta.get("inele_total")),
         help="Grupuri de firme legate prin cel puțin un administrator comun.")
kpi_card(c3, "Inele cu ≥2 firme cu bani de stat", fmt_int(meta.get("inele_cu_2plus_firme_bani_stat")),
         help="Cele mai interesante: mai multe firme ale aceluiași grup iau bani publici.")
kpi_card(c4, "Firme-pod (intermediari)", fmt_int(len(poduri)))

st.divider()

tab_inele, tab_hub, tab_pod = st.tabs(
    ["🔗 Inele de control", "👤 Administratori-hub", "🌉 Firme-pod"])

# ============================ INELE ============================
with tab_inele:
    st.markdown("#### Inele de control cu bani de stat")
    st.caption("Grupuri de firme cu administratori comuni, în care cel puțin o firmă a luat bani de la "
               "stat. Sortate după valoarea totală. Un grup de firme controlate de aceiași oameni NU e "
               "ilegal — e context pentru investigație.")

    fc1, fc2 = st.columns([3, 1])
    q = fc1.text_input("Caută după administrator sau firmă",
                       placeholder="ex: Erbașu, Umbrărescu, o firmă…").strip().lower()
    doar_multi = fc2.checkbox("Doar inele cu ≥2 firme cu bani", value=True)

    def _match(r):
        if doar_multi and r["n_companii_bani_stat"] < 2:
            return False
        if not q:
            return True
        hay = " ".join(r.get("admini", [])).lower() + " " + \
              " ".join((f.get("nume") or "") for f in r.get("companii", [])).lower()
        return q in hay

    flt = [r for r in inele if _match(r)]
    st.caption(f"{fmt_int(len(flt))} inele afișate (din {fmt_int(len(inele))}). Se arată primele 40.")

    for r in flt[:40]:
        admini = ", ".join(a.title() for a in r.get("admini", [])[:4])
        head = (f"{r['n_companii']} firme · {r['n_companii_bani_stat']} cu bani de stat · "
                f"{fmt_lei(r['total_bani_stat_ron'])}  —  {admini}")
        with st.expander(head):
            cdf = pd.DataFrame(r["companii"])
            cdf["bani"] = cdf["bani_stat"].map(lambda b: "💰" if b else "")
            st.dataframe(
                cdf[["nume", "cui", "total_ron", "bani"]],
                use_container_width=True, hide_index=True,
                column_config={
                    "nume": st.column_config.TextColumn("Firmă", width="large"),
                    "cui": st.column_config.NumberColumn("CUI", format="%d"),
                    "total_ron": st.column_config.NumberColumn("Bani de la stat (lei)", format="%.0f"),
                    "bani": st.column_config.TextColumn(" ", width="small"),
                })
            if r.get("n_admini", 0) > len(r.get("admini", [])):
                st.caption(f"Administratori comuni: {admini} (+{r['n_admini'] - len(r['admini'])} alții)")
            # drill-down pe contractele unei firme din inel
            opts = {f"{(f.get('nume') or '').strip()} · CUI {f['cui']}": f["cui"]
                    for f in r["companii"] if f.get("cui")}
            if opts:
                pick = st.selectbox("Vezi contractele unei firme din inel", list(opts.keys()),
                                    key=f"ring_{r['companii'][0]['cui']}")
                ui.firma_bani_stat(opts[pick], titlu="")

    # ---- graf interactiv al unui inel (administratori <-> firme) ----
    st.divider()
    st.markdown("##### 🕸️ Graf interactiv (administratori ↔ firme)")
    if flt:
        ropts = {f"{', '.join(a.title() for a in r['admini'][:2])} · {r['n_companii']} firme · "
                 f"{fmt_lei(r['total_bani_stat_ron'])}": i for i, r in enumerate(flt[:40])}
        rk = st.selectbox("Alege un inel pentru graf", list(ropts.keys()), key="ring_graph_sel")
        ring = flt[ropts[rk]]
        nodes, edges, aid_of = [], [], {}
        for fr in ring["companii"]:
            cid = f"c{fr['cui']}"
            nodes.append({"data": {"id": cid, "label": "FIRMA",
                                   "name": (fr.get("nume") or str(fr["cui"]))[:36]}})
            for adm in fr.get("admini", []):
                if adm not in aid_of:
                    aid_of[adm] = f"a{len(aid_of)}"
                    nodes.append({"data": {"id": aid_of[adm], "label": "ADMIN", "name": adm.title()}})
                edges.append({"data": {"id": f"{aid_of[adm]}_{cid}", "source": aid_of[adm],
                                       "target": cid, "label": "admin"}})
        node_styles = [NodeStyle("FIRMA", "#8b5cf6", "name", "business"),
                       NodeStyle("ADMIN", "#22d3ee", "name", "person")]
        edge_styles = [EdgeStyle("admin", caption="label", directed=True)]
        st_link_analysis({"nodes": nodes, "edges": edges}, "cose",
                         node_styles, edge_styles, key="ring_net")
        st.caption("Cyan = administrator · violet = firmă. Un administrator conectat la mai multe firme "
                   "= nodul care leagă inelul. Poți trage nodurile și da zoom.")

# ============================ HUBURI ============================
with tab_hub:
    st.markdown("#### Administratori care controlează cele mai multe firme cu bani de stat")
    st.caption("⚠️ Numele se potrivesc pe text — nume comune (ex. „Pop Ioan”) pot reuni mai multe "
               "persoane diferite (omonimi). Tratează ca lead, verifică în ONRC după CNP.")
    hdf = pd.DataFrame([{
        "Administrator": h["admin"].title(),
        "Firme (total)": h["n_firme"],
        "Firme cu bani de stat": h["n_firme_bani_stat"],
        "Total de la stat (lei)": h["total_bani_stat_ron"],
    } for h in huburi])
    st.dataframe(
        hdf, use_container_width=True, hide_index=True, height=460,
        column_config={
            "Firme (total)": st.column_config.NumberColumn(format="%d"),
            "Firme cu bani de stat": st.column_config.NumberColumn(format="%d"),
            "Total de la stat (lei)": st.column_config.NumberColumn(format="%.0f"),
        })
    # detaliu hub
    if huburi:
        sel = st.selectbox("Vezi firmele unui administrator",
                           [h["admin"].title() for h in huburi])
        h = next(x for x in huburi if x["admin"].title() == sel)
        fdf = pd.DataFrame(h["companii"])
        st.dataframe(
            fdf[["nume", "cui", "total_ron"]], use_container_width=True, hide_index=True,
            column_config={
                "nume": st.column_config.TextColumn("Firmă", width="large"),
                "cui": st.column_config.NumberColumn("CUI", format="%d"),
                "total_ron": st.column_config.NumberColumn("Bani de la stat (lei)", format="%.0f"),
            })

# ============================ PODURI ============================
with tab_pod:
    st.markdown("#### Firme-pod (intermediari între grupuri)")
    st.caption("Firme care leagă mai multe grupuri altfel separate (puncte de articulație în graf). "
               "Au mai mulți administratori din clustere diferite — posibili intermediari.")
    pdf = pd.DataFrame([{
        "Firmă": b.get("nume") or f"CUI {b['cui']}",
        "CUI": b["cui"],
        "Administratori": b["n_admini"],
        "Conexiuni (grad)": b["grad"],
        "Bani de la stat (lei)": b["total_bani_stat_ron"],
    } for b in poduri])
    st.dataframe(
        pdf, use_container_width=True, hide_index=True, height=460,
        column_config={
            "CUI": st.column_config.NumberColumn(format="%d"),
            "Administratori": st.column_config.NumberColumn(format="%d"),
            "Conexiuni (grad)": st.column_config.NumberColumn(format="%d"),
            "Bani de la stat (lei)": st.column_config.NumberColumn(format="%.0f"),
        })

st.divider()
st.caption(f"Sursă: administratori legali ONRC (data/v1/graf/network_metrics.json), graf calculat cu "
           f"igraph. Generat: {net.get('generat', '')}. Legăturile = administrator comun (real); "
           "valorile sunt agregate SICAP (pot include acorduri-cadru / cumul multianual).")
