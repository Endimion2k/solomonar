"""SOLOMONAR Insights — punct de intrare și meniu. Rulează: streamlit run web/app/Overview.py"""

from __future__ import annotations

import pathlib as _pl
import sys as _sys

import streamlit as st

for _a in _pl.Path(__file__).resolve().parents:  # import 'app' fără PYTHONPATH (rulare directă/deploy)
    if (_a / "app").is_dir():
        _sys.path.insert(0, str(_a))
        break

# (fișier din pages/, titlu în meniu) pe secțiuni; cheia goală = fără titlu de secțiune
MENU: dict[str, list[tuple[str, str]]] = {
    "": [
        ("0_Sinteza.py", "Sinteză"),
        ("10_Analytics.py", "Analize agregate"),
    ],
    "Oameni și firme": [
        ("1_Persoane.py", "Persoane"),
        ("2_Companii.py", "Companii de stat"),
        ("9_Harta.py", "Harta companiilor"),
        ("15_Retele.py", "Rețele de firme"),
        ("13_Sanctiuni.py", "Sancțiuni și PEP"),
    ],
    "Bani publici": [
        ("3_Achizitii.py", "Achiziții publice"),
        ("11_Achizitii_directe.py", "Achiziții directe"),
        ("4_Follow_the_money.py", "De la contract la persoană"),
        ("6_Bugete.py", "Bugete"),
    ],
    "Parlament și partide": [
        ("8_Comisii.py", "Comisii și legislație"),
        ("5_Partide.py", "Partide"),
    ],
    "Semnale de verificat": [
        ("12_Alerte.py", "Alerte"),
        ("16_Red_flags.py", "Indicatori de risc în achiziții"),
        ("14_Firme_paravan.py", "Firme noi cu bani de stat"),
        ("17_Avere_anomalii.py", "Anomalii de avere"),
        ("7_DNA.py", "Comunicate DNA"),
    ],
    "Despre": [
        ("18_Despre.py", "Surse și metodologie"),
    ],
}

pages = {
    sectiune: [st.Page(f"pages/{fisier}", title=titlu, default=(fisier == "0_Sinteza.py"))
               for fisier, titlu in intrari]
    for sectiune, intrari in MENU.items()
}
st.navigation(pages, expanded=True).run()
