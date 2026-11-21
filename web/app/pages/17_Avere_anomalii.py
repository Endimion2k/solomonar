"""Anomalii de avere — profiluri statistic neobișnuite (PyOD/ECOD) pe declarațiile de avere.

Sursă: data/v1/avere_anomalii.json (vezi pipeline/build_avere_anomalii.py). Piste de verificat —
scorul mare = profil declarat neobișnuit față de restul, nu dovadă de îmbogățire ilicită.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, GridOptionsBuilder, JsCode

import sys as _sys, pathlib as _pl  # bootstrap: import 'app' fără PYTHONPATH (rulare directă/deploy)
for _a in _pl.Path(__file__).resolve().parents:
    if (_a / 'app').is_dir():
        _sys.path.insert(0, str(_a)); break

from app import data
from app.theme import apply_theme, despre, fmt_int, fmt_lei, kpi_card, page_header, sidebar_brand

st.set_page_config(page_title="Anomalii avere · SOLOMONAR", layout="wide")
apply_theme()
sidebar_brand()
page_header("Anomalii de avere",
            "Profiluri declarate statistic neobișnuite față de restul (PyOD/ECOD pe venituri, conturi, "
            "datorii, terenuri, clădiri, auto). Piste de verificat — nu dovezi de îmbogățire.")
despre(
    sursa="Declarațiile de avere publicate în PDF de ministere și alte instituții pe site-urile proprii "
          "(obligație din Legea 176/2010), din care textul este extras automat.",
    calcul="Pentru fiecare persoană se ia cea mai recentă declarație și se formează un profil din 6 "
           "valori: venituri, sume în conturi, datorii, număr de terenuri, de clădiri și de vehicule. "
           "Algoritmul ECOD (biblioteca PyOD) măsoară pe fiecare valoare cât de rar este profilul față "
           "de toate celelalte și adună aceste rarități într-un scor, rescalat între 0 și 100. "
           "„Driver” este valoarea care contribuie cel mai mult la scor.",
    legaturi="Declarațiile aceleiași persoane se grupează după numele normalizat, iar anul declarației "
             "se ia din adresa PDF-ului. Pagina nu leagă persoanele de firme sau contracte.",
    limite="Scorul arată doar cât de diferit este profilul față de restul, așa că o avere mare, declarată "
           "și legală, iese la fel de sus. Extragerea automată din PDF poate număra greșit bunurile sau "
           "sumele, iar doi oameni cu același nume pot fi tratați ca unul singur. Verifică în declarația "
           "originală.",
)

av = data.avere_anomalii()
items = (av or {}).get("items") or []
if not items:
    st.warning("Datele de anomalii avere nu sunt generate. Rulează `python -m pipeline.build_avere_anomalii`.")
    st.stop()

st.warning(av.get("disclaimer", ""))

c1, c2, c3 = st.columns(3)
kpi_card(c1, "Persoane analizate", fmt_int(av.get("n_persoane")))
kpi_card(c2, "Profiluri marcate", fmt_int(len(items)))
kpi_card(c3, "Metodă", "PyOD ECOD", help=av.get("metoda", ""))

st.caption("„Driver” = dimensiunea care trage scorul de anomalie (ex. clădiri, terenuri, conturi).")

df = pd.DataFrame(items).rename(columns={
    "nume": "Nume", "institutie": "Instituție", "an": "An", "scor": "Scor", "driver": "Driver",
    "venituri_ron": "Venituri (lei)", "conturi_ron": "Conturi (lei)", "datorii_ron": "Datorii (lei)",
    "terenuri": "Terenuri", "cladiri": "Clădiri", "auto": "Auto", "sursa": "Sursă"})
keep = [c for c in ["Scor", "Driver", "Nume", "Instituție", "An", "Venituri (lei)", "Conturi (lei)",
                    "Datorii (lei)", "Terenuri", "Clădiri", "Auto"] if c in df.columns]
df = df[keep]

_lei = JsCode("function(p){return p.value==null?'':Math.round(p.value).toLocaleString('ro-RO');}")
gob = GridOptionsBuilder.from_dataframe(df)
gob.configure_default_column(filter=True, sortable=True, resizable=True, floatingFilter=True)
gob.configure_pagination(paginationAutoPageSize=False, paginationPageSize=20)
gob.configure_column("Nume", width=200)
gob.configure_column("Instituție", width=240)
for col in ("Venituri (lei)", "Conturi (lei)", "Datorii (lei)"):
    gob.configure_column(col, type=["numericColumn"], valueFormatter=_lei, width=130)
AgGrid(df, gridOptions=gob.build(), theme="streamlit", height=560,
       fit_columns_on_grid_load=False, allow_unsafe_jscode=True, enable_enterprise_modules=False)

st.divider()
st.caption(f"Sursă: data/v1/avere_anomalii.json. {av.get('metoda', '')}. Generat: {av.get('generat', '')}. "
           "Scorul mare poate fi și artefact de extragere (numărări imperfecte din PDF) — verifică în "
           "declarația originală înainte de orice concluzie.")
