# 01 — ARHITECTURĂ: structura și logica sistemului

> Model **hibrid**: public = JSON static pe CDN (filozofia `cdep-api-poc`), build = bază de
> date (DuckDB/SQLite) pentru entity resolution și graf de acționariat.

---

## 1. De ce hibrid (decizia centrală)

`cdep-api-poc` a folosit JSON static + GitHub Pages: cost zero, scalare CDN, snapshot-uri
imuabile. Perfect pentru **o instituție** cu date tabelare.

Scopul nou introduce două lucruri pe care JSON-ul plat nu le rezolvă bine:

1. **Entity resolution** — aceeași persoană apare în zeci de surse (deputat → ministru →
   membru CA la SOE → asociat într-o firmă). Trebuie un registru canonic de persoane cu ID
   stabil și aliasuri.
2. **Graf de relații** — acționariatul e intrinsec un graf (persoană → firmă → subsidiară),
   la fel conflictele de interese (funcție publică ↔ firmă ↔ contract).

| Opțiune | Cost | Putere graf/resolution | Verdict |
|---|---|---|---|
| Static pur | zero | slabă (fără join-uri cross-entitate) | insuficient |
| Backend complet (Postgres+Neo4j+API) | hosting + operare | maximă | over-engineering pentru un proiect civic |
| **Hibrid** | **zero (build în CI)** | **completă la build** | **ales** |

**Cheia:** baza de date trăiește **doar la build** (în CI, pe runner-ul self-hosted).
Rezultatul build-ului = JSON static. Nu există server de bază de date de operat 24/7.

- **DuckDB** — engine analitic embedded: citește CSV/Parquet/JSON direct, CTE recursive
  pentru traversare de graf, rulează în CI fără server. Folosit pentru staging + gold + graf.
- **SQLite** — bază mică, durabilă, **commit-abilă în repo**: ține registrele canonice
  (`romega_id`-uri, aliasuri, crosswalk-uri) ca să fie **stabile între rulări**.

---

## 2. Vedere pe straturi (medallion: bronze → silver → gold)

```
┌──────────────────────────────────────────────────────────────────────────┐
│  L0  SURSE (în sălbăticie)                                                  │
│  cdep.ro · senat.ro · 16 ministere · ~250 agenții · ~1000 deconcentrate    │
│  ANAF API · ANI portal · data.gov.ro · SICAP · MF · ONRC dump · BNR · INS  │
└───────────────┬──────────────────────────────────────────────────────────┘
                │  connectors (3 arhetipuri: api | bulk | scrape/headless)
                ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  L1  BRONZE — data/raw/   (artefacte BRUTE, imuabile, cache)               │
│  {source_id, url, fetched_at, sha256, content}  ← provenance pentru tot    │
└───────────────┬──────────────────────────────────────────────────────────┘
                │  parsers + Pydantic (normalizare, encoding, PDF/OCR)
                ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  L2  SILVER — staging DuckDB   (tipizat, uniform, cu provenance pe rând)   │
│  staging.person · staging.org · staging.company · staging.declaration ...  │
└───────────────┬──────────────────────────────────────────────────────────┘
                │  entity resolution + graph build   ◄── creierul sistemului
                ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  L3  GOLD — DuckDB (fapte) + SQLite (registre canonice)                    │
│  registry: person · organization · company  (romega_id stabil)            │
│  graph: nodes + edges (HOLDS_POSITION, OWNS_SHARE, AWARDED_CONTRACT ...)   │
└───────────────┬──────────────────────────────────────────────────────────┘
                │  exporter (gold → JSON versionat) + Pagefind + feeds
                ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  L4  PUBLIC — data/v1/*.json   (API STATIC) + index Pagefind + Atom/JSON   │
│  servit prin GitHub Pages CDN                                              │
└───────────────┬──────────────────────────────────────────────────────────┘
                │  fetch JSON
                ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  L5  CLIENT (web/)  — profile: persoană · instituție · companie + graf     │
│  + consumatori terți (jurnaliști, ONG, dezvoltatori)                       │
└──────────────────────────────────────────────────────────────────────────┘
```

**De ce medallion:** separă „ce-am descărcat" (bronze, imuabil) de „ce-am înțeles" (silver)
de „adevărul canonic" (gold). Poți reprocesa silver/gold fără să re-descarci. Fiecare fapt
publicat e trasabil înapoi la artefactul bronze + URL + dată.

---

## 3. Componentele sistemului

### 3.1 `packages/romega_core` — biblioteca comună
Extrasă din `cdep-api-poc`, generalizată:

| Modul | Responsabilitate |
|---|---|
| `http` | client `requests`+`truststore` (SSL legacy cdep.ro), retry/backoff, rate-limit per host, cache bronze, user-agent politicos |
| `parse` | helpers parsel (CSS/XPath), conversie encoding ISO-8859-2, extractor PDF (text + hook OCR), parser XLSX/CSV/XML/SOAP |
| `headless` | driver Playwright pentru SPA-uri JS (ANI portal) |
| `models` | modele Pydantic v2 canonice (vezi `02-DATA-MODEL.md`) |
| `resolve` | normalizare nume, blocking, matching, atribuire `romega_id` |
| `io` | exporter JSON versionat, generator Pagefind, feed-uri Atom/JSON |
| `provenance` | `SourceRef` atașat fiecărui fapt; registru bronze |

### 3.2 `connectors/` — un modul per familie de surse
Fiecare connector implementează aceeași interfață (`fetch → emit_bronze → parse → emit_silver`)
și e configurat din `config/sources.yaml`. Trei **arhetipuri**:

| Arhetip | Pentru | Exemple |
|---|---|---|
| `api` | surse structurate | ANAF REST, data.gov.ro CKAN, INS Tempo, BNR XML, legislatie SOAP |
| `bulk` | dump-uri descărcabile | ONRC CSV, situații financiare TXT, SICAP XLSX |
| `scrape` | HTML/PDF | cdep.ro, senat.ro, site-uri ministere, board-uri Art. 51 |
| `headless` | SPA-uri JS | ANI `declaratii.integritate.eu` |

> Connector-ul `parlament/cdep` e portarea 1:1 a scriptelor `run_*.py` din `cdep-api-poc`.
> Țintă în Faza 0: output identic (diff gol) = test de regresie.

### 3.3 `pipeline/` — orchestrarea build-ului
```
pipeline/
├── bronze.py    # registru artefacte brute (sha256, timestamp, path)
├── silver.py    # brut → modele → tabele staging DuckDB
├── gold/
│   ├── resolve.py   # entity resolution → registre SQLite (romega_id)
│   ├── graph.py     # construiește nodes + edges în DuckDB
│   └── derive.py    # vederi derivate (delta avere, agregate contracte, semnale conflict)
└── export.py    # gold → data/v1/*.json + Pagefind + feeds
```

### 3.4 Entity Resolution — creierul (detaliu)
Cel mai important subsistem. Vezi `02-DATA-MODEL.md` pentru algoritm. Pe scurt:
1. **Normalizare** — diacritice, ordine nume (NUME Prenume vs Prenume NUME), titluri (dr., ing.), variante.
2. **Blocking** — grupează candidați după chei ieftine (nume normalizat, an naștere, județ) ca să nu compari tot-cu-tot.
3. **Matching** — scor pe nume + DOB + context (instituție, funcție, perioadă). ANI (Faza 2) e ancoră puternică pentru că dă funcția+instituția.
4. **ID stabil** — `romega_id` în SQLite, persistat între rulări; tabel `alias` pentru toate formele văzute; tabel `crosswalk` (cdep_idm ↔ senat GUID ↔ CUI ↔ ...).
5. **Confidence + human-in-the-loop** — match-uri sub prag → coadă de revizuire manuală (homonimi).

### 3.5 Graful
Stocat relațional în DuckDB (tabele `node` + `edge`), interogat prin CTE recursive. Exportat
în JSON per-nod (pentru client) și opțional ca dump de graf (GraphML/JSON) pentru analiză.

```
NODURI:  Person · Organization · Company · Document
MUCHII:  HOLDS_POSITION (Person→Org)      OWNS_SHARE (Person/Company→Company, %)
         MEMBER_OF_BOARD (Person→Company)  SUBSIDIARY_OF (Company→Company)
         CONTROLS (Org→Company, stat→SOE)  AWARDED_CONTRACT (Org→Company, sumă)
         DECLARED (Person→Document)         SUBORDINATE_OF (Org→Org)
```

---

## 4. Logica de execuție (flux end-to-end)

```
                       ┌─────────────────────────────────────────┐
   GitHub Actions      │  pentru fiecare source_id din            │
   (self-hosted, RO)   │  config/sources.yaml, după cadență:      │
                       └───────────────────┬─────────────────────┘
                                           ▼
   1. connector.fetch()  ──►  data/raw/{source}/{hash}  (BRONZE, dacă s-a schimbat)
                                           ▼
   2. connector.parse()  ──►  staging.* în DuckDB        (SILVER)
                                           ▼
   3. pipeline.gold.resolve()  ──►  romega_id (SQLite, stabil)
                                           ▼
   4. pipeline.gold.graph()    ──►  nodes + edges (DuckDB)
                                           ▼
   5. pipeline.gold.derive()   ──►  delta avere, agregate, semnale conflict
                                           ▼
   6. pipeline.export()        ──►  data/v1/*.json + Pagefind + feeds
                                           ▼
   7. git commit + push  ──►  GitHub Pages CDN  ──►  client + terți
```

**Incremental:** ca în `cdep-api-poc`, fetch doar ce s-a schimbat (timestamp/hash); flag
`--full` pentru re-scrape complet. Bronze-ul cache-uit face reprocesarea ieftină.

**Cadență per sursă** (din `sources.yaml`):
- zilnic: parlament (voturi, proiecte), feed-uri;
- săptămânal: declarații noi, board-uri;
- lunar: dump-uri ONRC/MF, XLSX SICAP, bugete.

---

## 5. De ce runner self-hosted (constrângere moștenită)
`cdep.ro` și `senat.ro` **geo-blochează IP-urile de cloud** (confirmat în `cdep-api-poc`).
Deci CI rulează pe un PC Windows în România (setup existent). ANI la scară (~1.6M PDF-uri) și
headless-ul vor cere capacitate — de monitorizat (tensiunea T4 în `STATE.md`).

---

## 6. Provenance, audit și încredere
Fiecare fapt publicat poartă un `SourceRef`: `{source_id, source_url, fetched_at, bronze_sha256}`.
Clientul afișează „sursă + dată" pentru orice afirmație. Asta e esențial pentru un proiect de
transparență: **nicio afirmație fără sursă verificabilă**. Corecții via GitHub issues (ca în
`cdep-api-poc`).

---

## 7. Ce NU facem (limite deliberate)
- **Fără server de DB în producție** — DB doar la build.
- **Fără date redactate** — CNP, adrese, semnături rămân redactate (Legea 176/2010 + GDPR).
- **Fără UBO scrapat** — registrul beneficiarilor reali e restricționat legal (Legea 86/2025).
- **Fără re-identificare** — nu reconstruim date anonimizate la sursă.
- **Fără bypass de autentificare/ToS** — doar date publice, prin metode permise.

---

## 8. Stack tehnic (consolidat din `cdep-api-poc` + adăugiri)

| Strat | Tehnologie |
|---|---|
| Limbaj | Python 3.11+ |
| HTTP/scrape | `requests`, `truststore`, `parsel` |
| Headless | `playwright` |
| PDF/OCR | `pdfplumber`/`pypdf` + `tesseract` (RO) |
| Modele | Pydantic v2 |
| Build DB | DuckDB (analitic) + SQLite (registre canonice) |
| Export | JSON versionat + Pagefind + Atom/JSON Feed |
| Hosting public | GitHub Pages (CDN) |
| CI | GitHub Actions, runner self-hosted (RO) |
| Client | HTML/JS + i18n (RO/EN), vizualizare graf |

---

*Următorul document:* [`02-DATA-MODEL.md`](02-DATA-MODEL.md) — modelul de entități și graful.
