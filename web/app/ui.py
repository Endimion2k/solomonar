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
