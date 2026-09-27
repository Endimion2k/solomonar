"""Componente UI reutilizabile SOLOMONAR (folosite pe mai multe pagini)."""

from __future__ import annotations

import streamlit as st

from app import data
from app.theme import fmt_int, fmt_lei


def firma_bani_stat(cui, *, use_columns: bool = True,
                    titlu: str = "💰 Bani de la stat (agregat per firmă)") -> bool:
    """Panou agregat (contracte licitații + achiziții directe) pentru o firmă, după CUI.

    Datele sunt agregate per firmă (total, număr, ani, top autorități) — nu contract-cu-contract.
    `use_columns=False` randează stacked (pentru a încăpea într-o coloană existentă, fără nesting).
    Întoarce True dacă a afișat ceva.
    """
    prof = data.firma_profil(cui)
    ctr = prof.get("contracte") or {}
    adr = prof.get("achizitii_directe") or {}
    onrc = prof.get("onrc") or {}
    if not (ctr or adr):
        return False

    if titlu:
        st.markdown(f"**{titlu}**")
    c1, c2 = st.columns(2) if use_columns else (st.container(), st.container())

    with c1:
        st.markdown("*Contracte publice (licitații SICAP)*")
        if ctr:
            nr = ctr.get("nr") or 0
            ani = ", ".join(str(a) for a in (ctr.get("ani") or [])) or "—"
            medie = (ctr.get("total_ron") or 0) / nr if nr else 0
            st.markdown(
                f"- Total: **{fmt_lei(ctr.get('total_ron'))}**  \n"
                f"- Contracte: **{fmt_int(nr)}**" + (f" · medie {fmt_lei(medie)}" if nr else "")
                + f"  \n- Ani: {ani}")
        else:
            st.caption("Fără contracte de licitație înregistrate.")

    with c2:
        st.markdown("*Achiziții directe (cumpărări sub prag)*")
        if adr:
            ani = ", ".join(str(a) for a in (adr.get("ani_activi") or [])) or "—"
            st.markdown(
                f"- Total: **{fmt_lei(adr.get('total_ron'))}**  \n"
                f"- Achiziții: **{fmt_int(adr.get('nr'))}**  \n- Ani: {ani}")
            tops = adr.get("top_autoritati") or []
            if tops:
                st.markdown("- Cu cine (top autorități):  \n"
                            + "  \n".join(f"  · {t}" for t in tops))
        else:
            st.caption("Fără achiziții directe înregistrate.")

    caen = onrc.get("caen_domeniu") or onrc.get("caen")
    st.caption(
        (f"Domeniu (CAEN): {caen}. " if caen else "")
        + "Cifrele sunt agregate per firmă (valoare, număr, ani, top autorități). Obiectul fiecărui "
          "contract nu e în setul public — verifică după CUI în SICAP / e-licitatie.ro.")
    return True


GUV_SURSA = "guvernanta.gov.ro (Guvernul României, OUG 109/2011 art. 51)"


def guvernanta_numiri(numiri: list, *, cu_companie: bool = True, key: str = "guv") -> None:
    """Tabel cu numiri oficiale (guvernanta.gov.ro): rol, persoană/companie, partid, brut lunar,
    mandat, CV oficial și legătura cu graful SOLOMONAR."""
    import pandas as pd

    if not numiri:
        st.caption("Nicio numire în registrul oficial.")
        return
    rows = [{
        **({"Companie": n.get("companie")} if cu_companie else {}),
        "Rol": n.get("rol"),
        "Persoană": n.get("nume"),
        "Afiliere politică": n.get("partid") or "nedeclarat",
        "Brut lunar (lei)": n.get("brut_lunar_ron"),
        "Mandat până la": n.get("mandat_pana_la") or "—",
        "În graf": {"confirmat": "✓ confirmat", "candidat": "? omonim posibil"}.get(n.get("potrivire"), "—"),
        "CV oficial": n.get("cv_url"),
    } for n in numiri]
    st.dataframe(
        pd.DataFrame(rows), use_container_width=True, hide_index=True, key=key,
        column_config={
            "Brut lunar (lei)": st.column_config.NumberColumn(format="%d"),
            "CV oficial": st.column_config.LinkColumn("CV oficial", display_text="PDF"),
            "În graf": st.column_config.TextColumn(
                help="✓ = același nume și aceeași companie în graful SOLOMONAR; "
                     "? = un singur om cu acest nume în graf, fără confirmare pe companie"),
        })
