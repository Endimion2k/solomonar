"""Sancțiuni & PEP — entități cu legătură RO din OpenSanctions (referință, NU acuzație)."""

from __future__ import annotations

import streamlit as st

from app import data
from app.theme import (ACCENT_2, DANGER, SUCCESS, TEXT_DIM, WARNING, apply_theme,
                       fmt_int, kpi_card, page_header, sidebar_brand)

st.set_page_config(page_title="Sancțiuni & PEP · SOLOMONAR", page_icon="🌐", layout="wide")
apply_theme()
sidebar_brand()
page_header("Sancțiuni & PEP",
            "Entități cu legătură ROMÂNIA care apar pe liste internaționale de sancțiuni "
            "(EU / OFAC / UN ș.a.) sau sunt Politically Exposed Persons (PEP). "
            "Sursă: OpenSanctions. Lista este o REFERINȚĂ, nu o acuzație.")

# -------- etichete prietenoase pentru coduri liste / țări --------
LISTE_LABEL = {
    "us_ofac_sdn": "OFAC SDN (SUA)", "us_trade_csl": "US Consolidated Screening",
    "us_klepto_hr_visa": "US Kleptocracy/HR Visa", "us_cia_world_leaders": "CIA World Leaders",
    "eu_fsf": "EU Financial Sanctions", "eu_meps": "Membri PE", "eu_cor_members": "Comitetul Regiunilor UE",
    "ch_seco_sanctions": "Elveția (SECO)", "mc_fund_freezes": "Monaco", "fr_tresor_gels_avoir": "Franța (Trésor)",
    "fr_assemblee": "Adunarea Națională FR", "ca_dfatd_sema_sanctions": "Canada (SEMA)",
    "ca_foreign_reps": "Reprezentanți străini Canada", "be_fod_sanctions": "Belgia (FOD)",
    "lv_fiu_sanctions": "Letonia (FIU)", "tw_shtc": "Taiwan", "ua_nsdc_sanctions": "Ucraina (NSDC)",
    "un_ga_protocol": "Protocol ONU", "ro_fiu_declarations": "Declarații ONPCSB (RO)",
    "ann_pep_positions": "Poziții PEP", "wd_peps": "Wikidata PEP", "wd_categories": "Wikidata",
    "everypolitician": "EveryPolitician", "de_bundestag": "Bundestag DE", "il_knesset_members": "Knesset IL",
    "bg_parliament": "Parlament BG",
}
TARA_LABEL = {
    "ro": "România", "md": "Moldova", "ru": "Rusia", "ua": "Ucraina", "eu": "UE", "fr": "Franța",
    "ca": "Canada", "hu": "Ungaria", "bg": "Bulgaria", "ae": "EAU", "fi": "Finlanda", "cy": "Cipru",
    "at": "Austria", "pl": "Polonia", "nl": "Olanda", "pt": "Portugalia", "es": "Spania", "be": "Belgia",
    "sn": "Senegal", "cu": "Cuba", "il": "Israel", "de": "Germania", "us": "SUA",
}


def liste_str(codes) -> str:
    return ", ".join(LISTE_LABEL.get(c, c) for c in (codes or []))


def tari_str(codes) -> str:
    return ", ".join(TARA_LABEL.get(c, (c or "").upper()) for c in (codes or []))


bundle = data.sanctiuni()
meta, df = bundle["meta"], bundle["df"]

if df.empty:
    st.warning("Nu există date de sancțiuni / PEP disponibile.")
    st.stop()

# ---------------- KPI ----------------
c1, c2, c3, c4 = st.columns(4)
kpi_card(c1, "Entități RO (total)", fmt_int(meta["total"]),
         help="Entități cu legătură România din OpenSanctions.")
kpi_card(c2, "Sancționați (liste oficiale)", fmt_int(meta["sanctiuni"]),
         help="Persoane/entități pe liste internaționale de sancțiuni (EU/OFAC/UN ș.a.).")
kpi_card(c3, "PEP (expunere politică)", fmt_int(meta["pep"]),
         help="Politically Exposed Persons — demnitari/funcții publice. NU este o acuzație.")
kpi_card(c4, "În graful SOLOMONAR", fmt_int(meta["in_graf"]),
         help="Apar și în datele SOLOMONAR (match pe nume — posibil omonim).")

# ---------------- Disclaimer ----------------
st.markdown(
    f"<div style='background:rgba(245,158,11,.08);border:1px solid {WARNING};"
    f"border-radius:10px;padding:12px 16px;margin:6px 0 4px;font-size:13px;color:{TEXT_DIM}'>"
    f"<b style='color:{WARNING}'>De citit înainte:</b> "
    f"<b>Match pe nume</b> — o potrivire poate fi un <b>omonim</b> (altă persoană cu același nume). "
    f"<b>PEP</b> = expunere politică, ceva <b>normal și așteptat</b> pentru demnitari și funcționari publici "
    f"— <b>nu</b> este o acuzație de corupție. "
    f"<b>Sancțiunile</b> sunt măsuri internaționale documentate pe liste oficiale (OpenSanctions)."
    f"</div>", unsafe_allow_html=True)

st.divider()

# ================= SANCȚIUNI =================
sanc = df[df["dataset"] == "sanctions"].copy()
st.markdown(f"### 🚫 Sancțiuni internaționale — {fmt_int(len(sanc))} entități")
st.caption("Persoane și entități cu legătură RO aflate pe liste oficiale de sancțiuni "
           "(EU FSF, OFAC SDN, ONU ș.a.). Acestea sunt cele importante.")

if sanc.empty:
    st.info("Nicio entitate sancționată în set.")
else:
    sanc = sanc.sort_values("nume")
    for _, r in sanc.iterrows():
        tari = tari_str(r["tara"])
        liste = liste_str(r["liste"])
        graf_badge = (f"<span class='badge' style='border-color:{ACCENT_2};color:{ACCENT_2}'>"
                      f"în graful SOLOMONAR</span>" if r["in_graf"] else "")
        schema_lbl = {"Person": "Persoană", "Organization": "Organizație",
                      "LegalEntity": "Entitate juridică"}.get(r["schema"], r["schema"])
        with st.container(border=True):
            st.markdown(
                f"<div style='font-size:15px;font-weight:600;color:{DANGER}'>{r['nume']}</div>"
                f"<div style='font-size:12px;color:{TEXT_DIM};margin:2px 0 6px'>"
                f"{schema_lbl}{' · ' + tari if tari else ''} {graf_badge}</div>",
                unsafe_allow_html=True)
            if r["pozitie"]:
                st.markdown(f"<div style='font-size:13px;margin-bottom:4px'>"
                            f"<b>Poziție:</b> {r['pozitie']}</div>", unsafe_allow_html=True)
            if liste:
                st.markdown(f"<div style='font-size:12px;color:{TEXT_DIM};margin-bottom:4px'>"
                            f"<b>Liste:</b> {liste}</div>", unsafe_allow_html=True)
            if r["motiv"]:
                with st.expander("Motivul sancțiunii"):
                    st.markdown(f"<div style='font-size:13px;color:{TEXT_DIM}'>{r['motiv']}</div>",
                                unsafe_allow_html=True)

st.divider()

# ================= PEP =================
pep = df[df["dataset"] == "peps"].copy()
n_pep_graf = int(pep["in_graf"].sum())
st.markdown(f"### 🏛️ Politically Exposed Persons (PEP) — {fmt_int(len(pep))}")
st.caption("Demnitari, parlamentari și funcționari publici. Expunerea politică este firească "
           "pentru aceste funcții — apariția în listă NU înseamnă o problemă.")

fcol1, fcol2 = st.columns([1, 2])
doar_graf = fcol1.toggle(f"Doar cei din graful SOLOMONAR ({fmt_int(n_pep_graf)})", value=True,
                         help="Persoane PEP care apar și în datele SOLOMONAR (match pe nume).")
q = fcol2.text_input("Caută nume", placeholder="ex: popescu, ionescu…",
                     label_visibility="collapsed")

view = pep.copy()
if doar_graf:
    view = view[view["in_graf"]]
if q:
    ql = q.strip().lower()
    view = view[view["nume"].str.lower().str.contains(ql, regex=False)
                | view["nume_key"].str.lower().str.contains(ql, regex=False)]

view = view.sort_values(["in_graf", "nume"], ascending=[False, True])
total_view = len(view)
st.caption(f"{fmt_int(total_view)} persoane afișate"
           + ("" if total_view <= 500 else " · se afișează primele 500"))

if view.empty:
    st.info("Niciun rezultat pentru filtrele curente.")
else:
    show = view.head(500).copy()
    show["graf"] = show["in_graf"].map({True: "✓ în graf", False: "—"})
    show["tara_lbl"] = show["tara"].apply(tari_str)
    show["liste_lbl"] = show["liste"].apply(liste_str)
    show["pozitie_lbl"] = show["pozitie"].fillna("")
    st.dataframe(
        show[["nume", "graf", "pozitie_lbl", "tara_lbl", "liste_lbl",
              "n_declaratii", "n_companii"]],
        use_container_width=True, hide_index=True,
        column_config={
            "nume": st.column_config.TextColumn("Nume", width="medium"),
            "graf": st.column_config.TextColumn("SOLOMONAR", width="small"),
            "pozitie_lbl": st.column_config.TextColumn("Poziție / funcție", width="large"),
            "tara_lbl": st.column_config.TextColumn("Țări", width="small"),
            "liste_lbl": st.column_config.TextColumn("Surse (liste)", width="medium"),
            "n_declaratii": st.column_config.NumberColumn("Declarații", format="%d", width="small"),
            "n_companii": st.column_config.NumberColumn("Companii", format="%d", width="small"),
        },
    )

st.divider()
st.markdown(
    f"<div style='font-size:12px;color:{TEXT_DIM}'>"
    f"<b style='color:{SUCCESS}'>Sursă:</b> OpenSanctions (agregat al listelor oficiale de sancțiuni "
    f"și al pozițiilor PEP). Datele sunt filtrate la entitățile cu legătură România. "
    f"„În graful SOLOMONAR” = potrivire pe nume cu persoanele din SOLOMONAR și poate fi un omonim."
    f"</div>", unsafe_allow_html=True)
