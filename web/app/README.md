# SOLOMONAR Insights — client Streamlit

Dashboard interactiv peste datele SOLOMONAR (declarații, companii de stat, achiziții, partide, bugete,
graf follow-the-money, DNA, comisii). Citește JSON-urile statice din `data/v1/`.

## Rulare

```bash
pip install -r web/app/requirements.txt
cd <rădăcina solomonar>
streamlit run web/app/Overview.py
```

Sursa de date: implicit `data/v1` local. Pentru datele LIVE (GitHub Pages):

```bash
SOLOMONAR_DATA=https://endimion2k.github.io/romega/data/v1 streamlit run web/app/Overview.py
```

## Pagini

| Pagină | Conținut |
|---|---|
| Overview | KPI globali + conflicte confirmate + participații stat |
| Persoane | 56k persoane canonice — căutare + detaliu (declarații, companii, CV, comisii, proiecte) |
| Companii | 1.256 SOE — bilanț, acționariat BVB %, contracte, reps |
| Achiziții | 11.945 firme câștigătoare + sumar pe sector |
| Follow-the-money | conflicte confirmate + candidați (cu avertismente) + rețele co-administrare |
| Partide | subvenții 2008-26 + RVC + membri |
| Bugete | UAT + BGC lunar + sumar județ |
| DNA | 8.998 comunicate (publice; prezumția de nevinovăție) |
| Comisii | comisii Senat + PLx↔inițiatori (guvern vs parlamentar) |
| Hartă / Analytics | distribuții județe + view-uri DuckDB gold |

## Arhitectură
`web/app/data.py` = data-layer cu cache (`@st.cache_data`) — contractul stabil folosit de pagini.
`web/app/theme.py` = temă dark + helpers. Adaptat din [`cdep-client`](https://github.com/Endimion2k/cdep-client).
