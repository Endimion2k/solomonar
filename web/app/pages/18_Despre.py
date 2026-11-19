"""Surse și metodologie — de unde vin datele, cum se citesc și cum se cere o corecție."""

from __future__ import annotations

import streamlit as st

import sys as _sys, pathlib as _pl  # bootstrap: import 'app' fără PYTHONPATH (rulare directă/deploy)
for _a in _pl.Path(__file__).resolve().parents:
    if (_a / 'app').is_dir():
        _sys.path.insert(0, str(_a)); break

from app import data
from app.theme import (CLIENT_URL, apply_theme, data_freshness, fmt_int, page_header,
                       sidebar_brand, tabel)

REPO = "https://github.com/Endimion2k/solomonar"

st.set_page_config(page_title="Surse și metodologie · SOLOMONAR", layout="wide")
apply_theme()
sidebar_brand()

page_header("Surse și metodologie",
            "De unde vin datele, cât de sigură e fiecare legătură și cum ceri o corecție.")

s = data.stats()
gold = s.get("gold") or {}
inc = gold.get("incredere") or {}

st.markdown("#### Ce este Solomonar")
st.markdown(
    "Solomonar adună date publice despre instituțiile statului, despre oamenii care le conduc și "
    "despre banii publici, și le leagă între ele: aceeași persoană poate fi parlamentar, membru "
    "într-un consiliu de administrație și administrator al unei firme cu contracte publice. "
    f"{data_freshness()}.")
st.markdown(
    "Pentru o căutare rapidă după nume sau pentru graful de legături, folosește "
    f"[varianta simplă a site-ului]({CLIENT_URL}).")

st.markdown("#### De unde vin datele")
import pandas as pd

surse = pd.DataFrame([
    ("Parlament", "cdep.ro, senat.ro", "deputați, senatori, comisii, proiecte de lege, moțiuni"),
    ("Declarații de avere și de interese", "site-urile instituțiilor și ale companiilor de stat",
     "PDF-uri publicate conform Legii 176/2010, citite automat"),
    ("Companii de stat", "ANAF, AMEPIP, ONRC (data.gov.ro), Ministerul Finanțelor, BVB",
     "conducere, bilanțuri, participația statului"),
    ("Achiziții publice", "SICAP, prin data.gov.ro", "contracte atribuite și achiziții directe"),
    ("Partide", "raportul EFOR de pe banipartide.ro, Monitorul Oficial (legislatie.just.ro)",
     "subvenții de la stat și rapoartele anuale de venituri și cheltuieli"),
    ("Bugete", "Ministerul Dezvoltării (bugete locale), Ministerul Finanțelor (bugetul consolidat)",
     "veniturile și cheltuielile unităților administrativ-teritoriale, execuția lunară a bugetului general"),
    ("Semnale externe", "DNA, Curtea de Conturi, OpenSanctions, guvernanta.gov.ro",
     "comunicate, rapoarte, liste de sancțiuni și de persoane expuse politic"),
], columns=["Domeniu", "Sursă", "Ce preluăm"])
tabel(surse, use_container_width=True, hide_index=True)

st.markdown("#### Cât de sigură e o legătură")
st.markdown(
    "Sursele publice nu conțin CNP-ul, care este redactat prin lege. De aceea, legătura dintre o "
    "persoană și o firmă se face după nume și după context. Fiecare persoană are un nivel de încredere:")
niveluri = pd.DataFrame([
    ("Confirmată", inc.get("high"), "Identitate stabilită cu date suplimentare, de exemplu data nașterii la parlamentari."),
    ("Cu context", inc.get("context"), "Același nume și aceeași instituție sau companie în două surse diferite."),
    ("Candidat", inc.get("candidat"), "Potrivire doar după nume. Poate fi un omonim și trebuie verificată."),
], columns=["Nivel", "Persoane", "Ce înseamnă"])
tabel(niveluri, use_container_width=True, hide_index=True)
if gold.get("persoane_canonice") and inc.get("candidat"):
    pct = 100 * inc["candidat"] / gold["persoane_canonice"]
    st.caption(f"Din {fmt_int(gold['persoane_canonice'])} de persoane, {pct:.0f}% sunt la nivelul „candidat”.")

st.markdown("#### Limite de care să ții cont")
st.markdown(
    "- **Conflictele de interese** sunt confirmate doar când firma apare în propria declarație de "
    "interese a persoanei. Restul potrivirilor sunt piste, nu concluzii.\n"
    "- **Valorile de contracte sunt brute.** Același contract este numărat la fiecare ofertant, deci "
    "totalurile pe firmă și pe sector sunt mai mari decât sumele încasate. Folosește-le pentru "
    "comparații, nu ca sume exacte.\n"
    "- **Sumele din declarații** sunt extrase automat din PDF-uri, uneori scanate. Verifică "
    "documentul original înainte de a cita o cifră.\n"
    "- **Comunicatele DNA** descriu trimiteri în judecată și măsuri procesuale, nu condamnări. "
    "Orice persoană este nevinovată până la o hotărâre definitivă.\n"
    "- **Alertele și indicatorii de risc** sunt calculați automat. Semnalează ce merită verificat, "
    "nu ce este ilegal.")

st.markdown("#### Date personale")
st.markdown(
    "Publicăm date despre persoane în calitatea lor oficială, pe baza Legii 544/2001 (accesul la "
    "informații de interes public), a Legii 176/2010 (declarațiile de avere și de interese sunt "
    "publice) și a OUG 109/2011 (transparența companiilor de stat). Nu publicăm CNP-uri, adrese "
    "complete, semnături, telefoane personale sau date despre minori; un filtru automat verifică "
    "asta înainte de fiecare publicare.")

st.markdown("#### Cum ceri o corecție")
st.markdown(
    f"Dacă o informație este greșită sau te privește și vrei să fie corectată, deschide o "
    f"[sesizare pe GitHub]({REPO}/issues) cu pagina, numele și sursa corectă. Codul și datele "
    f"sunt publice în [depozitul proiectului]({REPO}).")
