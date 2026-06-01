# ROMEGA — Romania Open Mega-Graph of the State

> Platformă de transparență care agregă, normalizează și interconectează datele publice
> ale întregului aparat de stat românesc: Parlament, Guvern, ministere, agenții, servicii
> deconcentrate, companii de stat, acționariat, declarații de avere și achiziții publice.
>
> Construit pe fundația [`cdep-api-poc`](https://github.com/Endimion2k/cdep-api-poc) și
> extins de la *o instituție* la *tot statul*.

---

## Ce este ROMEGA

`cdep-api-poc` a demonstrat că datele Camerei Deputaților pot fi transformate din HTML/PDF
într-un **API JSON static**, gratuit, servit prin CDN. ROMEGA generalizează acel model și
adaugă ceea ce un singur parlament nu cerea: **rezoluție de entități** (aceeași persoană e
deputat *și* ministru *și* membru CA la o companie de stat) și un **graf de relații**
(persoană → funcție → instituție → companie → contract → acționariat).

Întrebări la care ROMEGA răspunde și pe care surse izolate nu le pot acoperi:

- *Cine conduce compania de stat X și ce a declarat în declarația de avere?*
- *Ce firme deținute de rude/asociați ai unui demnitar au câștigat contracte publice?*
- *Cum s-a modificat averea unui oficial pe durata mandatului?*
- *Ce instituții finanțează aceeași firmă și cu ce sume?*

## Arhitectură (rezumat)

Model **hibrid**, ales deliberat (vezi [`docs/01-ARCHITECTURE.md`](docs/01-ARCHITECTURE.md)):

```
SURSE → connectors → raw/ (bronze)  → staging DuckDB (silver)
      → entity resolution + graph (gold, DuckDB/SQLite)
      → export → data/v1/*.json (API static) + Pagefind
      → GitHub Pages CDN → client + terți
```

- **Public = static** (JSON pe GitHub Pages): zero cost de hosting, scalare CDN, provenance imuabil — exact filozofia din `cdep-api-poc`.
- **Build = bază de date** (DuckDB la build în CI + SQLite pentru registrele canonice): putere relațională și de graf pentru entity resolution și acționariat, fără server de operat.

## Documentație

| Document | Conținut |
|---|---|
| [`docs/00-MASTERPLAN.md`](docs/00-MASTERPLAN.md) | Planul de implementare pe faze/valuri, cu pași concreți |
| [`docs/01-ARCHITECTURE.md`](docs/01-ARCHITECTURE.md) | Structura și logica sistemului (straturi, flux de date, componente) |
| [`docs/02-DATA-MODEL.md`](docs/02-DATA-MODEL.md) | Modelul canonic de entități, rezoluția de entități, schema grafului |
| [`docs/03-SOURCES.md`](docs/03-SOURCES.md) | Catalogul complet de surse (Senat, ministere, direcții, companii, ANAF, ANI, tot) |
| [`docs/04-LEGAL-GDPR.md`](docs/04-LEGAL-GDPR.md) | Bază legală, redactări obligatorii, GDPR, ToS pe surse |
| [`config/sources.yaml`](config/sources.yaml) | Registrul **machine-readable** al surselor (config pentru connectors) |
| [`STATE.md`](STATE.md) | Decizii, blocaje, poziția curentă (memorie de proiect) |

## Structura repo

```
romega/
├── docs/              # Documentația de arhitectură și plan
├── config/            # sources.yaml — registrul de surse (single source of truth)
├── packages/
│   └── romega_core/   # Bibliotecă comună: HTTP, parsing, modele Pydantic, exporter, resolution
├── connectors/        # Un modul per familie de surse
│   ├── parlament/     #   Camera Deputaților (cdep) + Senat
│   ├── ani/           #   Declarații de avere/interese (integritate.eu)
│   ├── companii/      #   Companii de stat (AMEPIP) + acționariat (ONRC/agregatori)
│   ├── achizitii/     #   Achiziții publice (SICAP / e-licitatie)
│   ├── fiscal/        #   ANAF (API CUI) + Ministerul Finanțelor (bilanțuri)
│   └── opendata/      #   data.gov.ro (CKAN) + INS Tempo + BNR
├── pipeline/          # Build bronze→silver→gold (DuckDB/SQLite), entity resolution, exporter
├── data/
│   ├── raw/           # Bronze: artefacte brute cache-uite (gitignored)
│   ├── build/         # DuckDB/SQLite de build (gitignored)
│   └── v1/            # Gold: JSON static publicat (API)
├── web/               # Client (succesorul cdep-client)
└── .github/workflows/ # CI: runner self-hosted, un workflow per sursă
```

## Status

🟢 **Faze 0–6 implementate · 93 teste verzi · API static publicat.** Vezi [`STATE.md`](STATE.md) pentru detalii.

| Domeniu | Stare | Validare |
|---|---|---|
| Fundație (core + pipeline DuckDB/SQLite + CI) | ✅ | 93 teste |
| Parlament — Camera + Senat + **unificare bicamerală** | ✅ | HTML real cdep.ro |
| Declarații avere/interese (ANI) + **guard redactare PII** + delta | ✅ | template ANI |
| Companii de stat — ANAF API + AMEPIP + ONRC + `CONTROLS` | ✅ | **live** (Romgaz, Hidroelectrica…) |
| Achiziții (SICAP) + `AWARDED_CONTRACT` + **follow-the-money** | ✅ | live (28 XLSX) |
| Instituții — generic config-driven: **1.429** (centrale + deconcentrate + locale) | ✅ | din `sources.yaml` |
| Legislație (parsare referințe + SOAP) · BNR · INS Tempo · CKAN | ✅ | **live** (BNR, INS 1915 matrici) |
| Export → `data/v1/*.json` (API static) + client web | ✅ | publicat |

**Întrebări pe care le modelează deja:** *aceeași persoană = deputat+senator+membru CA* · *stat→SOE→subsidiară* · *firmă de demnitar care ia bani publici*.

### Cum rulezi
```bash
python -m venv .venv && .venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m pip install -e packages/romega_core
.venv/Scripts/python -m pytest .                       # 93 teste
.venv/Scripts/python -m pipeline.run --list            # listează sursele
.venv/Scripts/python -m pipeline.run --build           # generează data/v1/*.json
# client: deschide web/index.html
```

> Validat live de pe o mașină din RO: cdep.ro (SSL legacy), ANAF API (v9), data.gov.ro, BNR, INS, SICAP.
> Rularea programată/la volum → runner self-hosted (geo-block cloud).

## Licență

- **Cod:** Open Government License v3.0 (consecvent cu `cdep-api-poc`).
- **Date:** vezi `docs/04-LEGAL-GDPR.md` — date despre oficiali în calitate oficială (exceptate GDPR), cu redactările impuse de Legea 176/2010 păstrate.

---

*Proiect inițiat de Cătălin Popa. Construit ca extensie a `cdep-api-poc`.*
