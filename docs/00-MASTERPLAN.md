# 00 — MASTERPLAN ROMEGA

> Planul de implementare pas-cu-pas, organizat pe **faze** (valuri). Fiecare fază are:
> scop, livrabile, pași atomici, criterii „done" și surse (din `03-SOURCES.md`).
>
> Filozofie de execuție (din `~/.claude/CLAUDE.md`): spec → research → design → execute →
> verify. Task-uri atomice, commit-uri atomice, verificare înainte de „done".

---

## Principii directoare

1. **Refolosește, nu rescrie.** `cdep-api-poc` are deja HTTP cu SSL legacy, parsel helpers,
   modele Pydantic, exporter JSON, Pagefind. Faza 0 le extrage într-o bibliotecă comună.
2. **Sursa de adevăr e `config/sources.yaml`.** Orice connector citește de acolo. Lista de
   surse și execuția nu diverg niciodată.
3. **Bronze imuabil.** Orice fetch se salvează brut, cu timestamp + hash, în `data/raw/`.
   Reprocesarea nu re-descarcă. Provenance pentru fiecare fapt publicat.
4. **Entity resolution e continuă.** Nu e o fază — fiecare val alimentează registrele de
   Person/Organization/Company. Calitatea grafului crește monoton.
5. **Publici doar ce e public.** Redactările legale (CNP, adrese, semnături) rămân redactate.
6. **Fiecare val livrează valoare vizibilă** în client, nu doar JSON.

---

## Harta valurilor (vedere de ansamblu)

```
FAZA 0 — Fundație (core + pipeline + entity resolution v0)
   │
   ├── FAZA 1 — Senat ................... unifică Parlamentul (bicameral)
   │
   ├── FAZA 2 — Declarații ANI ......... avere + interese, central, pentru TOȚI demnitarii
   │
   ├── FAZA 3 — Companii de stat + acționariat ... follow-the-money (SOE + board + ownership)
   │
   ├── FAZA 4 — Achiziții publice (SICAP) ........ contractele care leagă firmele de stat
   │
   └── FAZA 5+ — Restul statului ........ agenții centrale (Tier 2), deconcentrate (Tier 3),
                                          bugete, salarii, legislație, audit, enrichment
```

Dependențe: **0 blochează tot**. 1–4 sunt în ordinea cerută. Entity resolution (cross-cutting)
devine tot mai valoroasă pe măsură ce se adaugă valuri (ex.: Faza 3 depinde de Faza 2 pentru
a lega membrii CA de declarațiile lor).

---

## FAZA 0 — Fundație

**Scop:** scheletul tehnic care face posibile toate celelalte valuri. Fără date noi de
instituții — doar infrastructura + portarea `cdep`.

### Livrabile
- `packages/romega_core` — bibliotecă comună.
- `pipeline/` — build bronze→silver→gold pe DuckDB + registre SQLite.
- Entity resolution v0 (normalizare nume + tabel de aliasuri + `romega_id` stabil).
- Framework de connector (3 arhetipuri: `api`, `bulk`, `scrape`/`headless`).
- `config/sources.yaml` populat (deja schițat).
- CI: runner self-hosted + un workflow generic parametrizat pe sursă.
- Migrarea connector-ului `parlament` (Camera Deputaților) pe noul core — test de regresie:
  output identic cu `cdep-api-poc`.

### Pași atomici
1. **`romega_core/http`** — extrage clientul `requests`+`truststore` cu adaptor SSL legacy din `cdep-api-poc`. Adaugă: retry/backoff, cache pe disc (bronze), user-agent + rate-limit per host.
2. **`romega_core/parse`** — helpers parsel (CSS/XPath), conversie encoding (ISO-8859-2), extractor PDF (text + fallback OCR hook).
3. **`romega_core/models`** — modele Pydantic v2 canonice (vezi `02-DATA-MODEL.md`): `Person`, `Organization`, `Company`, `Position`, `Declaration`, `OwnershipStake`, `Contract`, `Document`, `SourceRef`.
4. **`romega_core/io`** — exporter JSON versionat + generator Pagefind + feed Atom/JSON (portate din `cdep`).
5. **`pipeline/bronze`** — registru de artefacte brute: `{source_id, url, fetched_at, sha256, path}`.
6. **`pipeline/silver`** — încarcă brut → modele → tabele staging DuckDB, cu coloane de provenance pe fiecare rând.
7. **`pipeline/gold/resolve`** — entity resolution v0: normalizare (diacritice, ordine nume, titluri), blocking, tabel `person_alias`, atribuire `romega_id` (SQLite, commit-abil).
8. **`pipeline/gold/graph`** — tabele de noduri/muchii (vezi `02-DATA-MODEL.md`); interogări de graf prin CTE recursive DuckDB.
9. **`pipeline/export`** — gold → `data/v1/*.json` + index Pagefind.
10. **`connectors/parlament/cdep`** — portează scriptele `run_*.py` din `cdep-api-poc` pe noul core.
11. **CI** — `.github/workflows/source.yml` generic: input = `source_id`, rulează connector → pipeline → export → commit.
12. **`sources.yaml`** — finalizează schema + intrările (vezi `config/sources.yaml`).

### Criterii „done"
- [ ] `connectors/parlament/cdep` produce JSON identic (diff gol) cu `cdep-api-poc` pe legislatura 2024.
- [ ] Entity resolution atribuie `romega_id` stabil între două rulări consecutive.
- [ ] Un fapt publicat poate fi urmărit înapoi la artefactul bronze + URL + dată.
- [ ] CI rulează end-to-end pe runner-ul self-hosted.

---

## FAZA 1 — Senat (unificarea Parlamentului)

**Scop:** a doua cameră → entitate `Parlamentar` unificată, ciclu de viață bicameral al legii.

> Context tehnic (din research): `senat.ro` e ASP.NET WebForms, chei GUID, **doar HTML, fără
> open data**. Nu împarte ID-uri cu `cdep.ro`. Crosswalk pe nume+legislatură. `cdep.ro` e
> de fapt sursa mai bună pentru ciclul bicameral al legii (`cam=1` = Senat).

### Pași atomici
1. `connectors/parlament/senat/senators` — `FisaSenatori.aspx` + `FisaSenator.aspx?ParlamentarID={GUID}`.
2. `.../votes` — `Voturiplen.aspx` (voturi plen electronice).
3. `.../bills` — `legiproiect.aspx` + `Legis/Lista.aspx` (cod+NR+AN).
4. `.../questions` — `VizualizareIntrebariInterpelari.aspx`.
5. `.../committees` — `EnumComisii.aspx?Permanenta=1`.
6. `.../stenograms` — `StenoPag2.aspx` (full-text).
7. **Crosswalk** Senate GUID ↔ `cdep` person ↔ `romega_id` (nume+DOB+legislatură, scor de încredere).
8. **Bicameral bill tracker** — unifică proiectul pe traseul Senat→Cameră folosind `cdep.ro upl_pck` cu `cam=1/2`.
9. Export + client: profil senator, ciclu de viață al legii pe ambele camere.

### Criterii „done"
- [ ] Toți senatorii legislaturii curente, legați la `romega_id`.
- [ ] Un proiect de lege arată traseul complet (Senat + Cameră) într-un singur profil.
- [ ] Parlamentarii care au fost și deputat și senator au un singur `romega_id`.

---

## FAZA 2 — Declarații de avere și interese (ANI)

**Scop:** sursa centrală pentru **toți** demnitarii. Acesta e momentul în care entity
resolution capătă putere reală — ANI leagă persoane din tot statul.

> Context (din research): repository central la `declaratii.integritate.eu` (SPA JS, ~1.6M
> declarații), arhivă veche `old-declaratii.integritate.eu` (2008–2022). **Fără API/bulk** —
> headless scraping. PDF-uri: 2022+ native (text), pre-2022 scanate (OCR). Bază legală:
> Legea 176/2010. Redactări obligatorii: CNP, adrese, semnături.

### Pași atomici
1. `connectors/ani/portal` — driver headless (Playwright) pe SPA-ul de căutare: enumerare după instituție/an → index de declarații + URL-uri PDF.
2. `.../archive` — arhiva 2008–2022 (`old-declaratii` / `depozitar`).
3. `romega_core/pdf` — extractor: ramură text (2022+) + ramură OCR (Tesseract RO, pre-2022).
4. `.../parse` — parser pe template-ul legal standardizat: secțiuni imobile, vehicule, active financiare, datorii, venituri, cadouri (avere) + acțiuni, funcții CA, contracte (interese).
5. **Link la Person** — fiecare declarație → `romega_id` (ANI dă funcția+instituția → context puternic pentru rezoluție).
6. **Delta de avere** — diferențe an-la-an per persoană (conceptul există deja în `cdep-api-poc declaratii-avere`).
7. **Guard de redactare** — verifică automat că nu se publică CNP/adrese.
8. Export + client: profil declarații per persoană, timeline de avere, alerte de variație.

### Criterii „done"
- [ ] Declarațiile demnitarilor din valurile 0–1 (parlamentari) sunt parsate și legate.
- [ ] Pipeline-ul OCR procesează corect un eșantion pre-2022.
- [ ] Delta de avere se calculează corect pe ≥2 ani.
- [ ] Niciun câmp redactat legal nu apare în output (test automat).

---

## FAZA 3 — Companii de stat + acționariat (follow-the-money)

**Scop:** lista completă a companiilor de stat, conducerea lor (CA/AGA/directorat) și graful
de proprietate — legate de declarațiile și funcțiile din valurile anterioare.

> Context (din research): master list = **AMEPIP, Raport anual, Anexa 1** (CUI + nume +
> autoritate tutelară). ~1.320 întreprinderi publice monitorizate (146 centrale + 1.174
> locale). Board prin OUG 109/2011 art. 51 (site-uri proprii, conformare inegală) + AMEPIP +
> BVB (listate). **Acționariat cu %:** ONRC dump (data.gov.ro) dă doar reprezentanți legali;
> asociați+% doar prin API comercial (termene.ro / risco.ro) — vezi tensiunea T1 în STATE.md.

### Pași atomici
1. `connectors/companii/amepip` — parsează Anexa 1 din raportul AMEPIP → master list SOE (CUI, nume, APT).
2. `connectors/fiscal/anaf` — îmbogățire per CUI prin ANAF REST (status, CAEN, TVA, inactiv). *(100 CUI/req, 1 req/s.)*
3. `connectors/opendata/datagov/onrc-dump` — `OD_FIRME.CSV` + `OD_REPREZENTANTI_LEGALI` → companii + reprezentanți legali.
4. `connectors/fiscal/mf-bilanturi` — `situatii_financiare_{an}` (TXT+CSV bulk) → indicatori financiari per CUI.
5. `connectors/companii/boards` — crawl Art. 51 per companie (CA/directorat + CV + remunerație) + listări AMEPIP + filings BVB pentru listate.
6. `connectors/companii/ownership` — **(decizie T1)** acționari+% via agregator comercial (termene.ro „Asociați și Administratori" / risco.ro ACT) pentru ținte prioritare; fallback gratis = reprezentanți legali.
7. **Graf** — muchii `MEMBER_OF_BOARD`, `OWNS_SHARE`, `SUBSIDIARY_OF`, `CONTROLS`.
8. **Conflict detection v0** — membru CA `romega_id` ↔ declarație de interese ↔ funcție publică (semnal de potențial conflict).
9. Export + client: profil companie (conducere, financiar, acționariat), graf de proprietate vizualizat.

### Criterii „done"
- [ ] Master list SOE completă (≥146 centrale) cu CUI + autoritate tutelară.
- [ ] Conducerea companiilor mari (Hidroelectrica, Romgaz, Nuclearelectrica, CFR, Poșta, Tarom...) legată la `romega_id`.
- [ ] Graf de proprietate navigabil pentru un eșantion de SOE.
- [ ] Cel puțin un semnal de conflict de interese detectat și verificabil manual.

---

## FAZA 4 — Achiziții publice (SICAP)

**Scop:** contractele care leagă firmele de banii publici; muchii firmă↔autoritate↔sumă.

> Context (din research): **fără OCDS** funcțional. Open data oficial = XLSX bulk anual pe
> `data.gov.ro` (publisher ADR), 28 fișiere/an. Alternativă bogată dar nesusținută: JSON la
> `istoric.e-licitatie.ro/api-pub/...`.

### Pași atomici
1. `connectors/achizitii/datagov-xlsx` — ingest XLSX anual (achiziții directe, contracte, anunțuri de atribuire).
2. `connectors/achizitii/elicitatie-json` *(opțional)* — `istoric.e-licitatie.ro/api-pub/C_PUBLIC_*` pentru detaliu suplimentar (fragil, undocumented).
3. **Match entități** — autoritate contractantă → `Organization`; furnizor (CUI) → `Company`.
4. **Graf** — muchii `AWARDED_CONTRACT` (autoritate→firmă, sumă, dată, obiect).
5. **Cross-link cu Faza 3** — firme cu legături la demnitari/membri CA care iau contracte publice.
6. Export + client: profil firmă cu contracte câștigate; profil instituție cu contracte acordate.

### Criterii „done"
- [ ] Contractele pe ≥1 an complet, legate la companii (CUI) și autorități.
- [ ] Sume agregate per firmă și per autoritate.
- [ ] Cel puțin un lanț firmă↔demnitar↔contract evidențiat.

---

## FAZA 5+ — Restul statului

**Scop:** acoperire completă. Conectoare generice + templated pentru volumul mare.

### Sub-valuri (în ordine de valoare)
1. **Tier 2 — agenții centrale (~200–300):** connector generic „instituție" (date org, conducere, link declarații, buget, achiziții, SOE proprii). Ținte prioritare: ANAF, ANI, ONRC, Curtea de Conturi, ASF, BNR, AEP, ANAP, CNSC, ANRE, ANCOM, CNAS, CNPP, ANOFM, INS, ANPC (vezi `03-SOURCES.md`).
2. **Bugete & salarii:** `data.gov.ro` (`buget*`, `drepturi-salariale`) + MF `transparenta-bugetara` → cheltuieli per instituție, salarii sector public.
3. **Legislație:** `legislatie.just.ro` (SOAP) → cross-link cu proiectele de lege din Faza 1.
4. **Ministere (16) — adâncime org:** organigrame (Tier 1 directorate) unde e nevoie de context.
5. **Tier 3 — deconcentrate (~900–1.350):** connector templated per tip de serviciu × 42 unități (DSP, DSVSA, AJOFM, ITM, APIA, OCPI, IPJ, ISU...). Generare din `sources.yaml`.
6. **Axa locală (Consilii Județene):** DGASPC, DJEP, spitale județene — modelate ca tier separat (autonomie locală, nu stat central).
7. **Audit:** Curtea de Conturi — rapoarte de audit → semnale pe instituții/companii.
8. **Enrichment:** BNR (curs XML), INS Tempo (statistică) — context economic.

### Criterii „done" (per sub-val)
- [ ] Connector generic configurabil 100% din `sources.yaml` (zero cod nou per instituție similară).
- [ ] Tier 3 generat din template, nu scris manual per instituție.

---

## Matrice faze × surse (rezumat)

| Fază | Surse principale | Metodă | Cost |
|---|---|---|---|
| 0 | `cdep.ro` (portare) | scrape | gratis |
| 1 | `senat.ro`, `cdep.ro` | scrape | gratis |
| 2 | `declaratii.integritate.eu` | headless + OCR | gratis (efort) |
| 3 | AMEPIP, ANAF API, data.gov.ro, MF, BVB, **(agregator)** | bulk+api+scrape | gratis + **opțional plătit (acționariat)** |
| 4 | data.gov.ro XLSX, e-licitatie | bulk+api | gratis |
| 5+ | data.gov.ro CKAN, legislatie SOAP, BNR, INS, site-uri instituții | api+bulk+scrape | gratis |

## Estimare de efort (relativă)

| Fază | Complexitate | Risc principal |
|---|---|---|
| 0 | Mare | Entity resolution corect de la început |
| 1 | Medie | GUID-uri Senat, crosswalk fără ID comun |
| 2 | Mare | Headless la scară + OCR pre-2022 + volum (~1.6M PDF) |
| 3 | Foarte mare | Acționariat (cost/ToS) + board decentralizat (Art. 51 inegal) |
| 4 | Medie | Lipsa OCDS, API undocumented fragil |
| 5+ | Mare (dar repetitiv) | Volum Tier 3; menținerea connector-ului generic |

---

*Următorul document:* [`01-ARCHITECTURE.md`](01-ARCHITECTURE.md) — structura și logica sistemului.
