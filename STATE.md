# STATE.md — ROMEGA

> Memorie de proiect: decizii, blocaje, tensiuni, poziția curentă.
> Actualizează ÎNAINTE de orice `/compact` sau la final de sesiune.

Owner: Cătălin Popa · Ultima actualizare: 2026-06-01

---

## Poziția curentă

> **SUMAR (2026-06-03, sesiuni autonome):** Faze 0–6 + coverage · **98 teste verzi** · 22
> commit-uri pe `Endimion2k/romega` (PUBLIC) · **API STATIC LIVE** pe GitHub Pages.
> Validat LIVE din RO: cdep.ro, senat.ro, ANAF v9, data.gov.ro, BNR, INS, SICAP, Curtea de Conturi, DNA, ANI portal.
>
> **🟢 Item 1 (deploy): LIVE** — repo public, Pages "built". API la
> `https://endimion2k.github.io/romega/data/v1/status.json` (HTTP 200), client la `/romega/web/`.
>
> **🟢 Item 2 (rulări live):** cdep → **335 deputați** (335 unici, 0 erori) + senat → **134 senatori**
> (133 unici) publicați în `data/v1/parlament/` (cu birth_date din profile → omonimi separați la cdep;
> senat fără birth_date → entități proprii, fără fals-merge cross-cameră).
>
> **🟡 Item 3 (coverage):** ✅ Curtea de Conturi + ✅ DNA (validate live). ❌ AEP = reCAPTCHA (Camoufox).
> ⚠️ ANI: portal nou CONFIRMAT drivable cu Playwright (search input + buton); RĂMAS = extragere
> rezultate din componenta Angular + mecanism PDF (subproiect). Parser+guard+delta gata (Faza 2).
>
> **Backlog:** ANI harvest (driver rezultate) · AEP (Camoufox) · bugete/salarii (heterogen) ·
> board-uri Art.51 (runner) · **acționariat % plătit (DEFERIT, D7)**.

---

**Faza 0 — Fundație: COMPLETĂ (cod) — 44/44 teste verzi.** `cdep-api-poc` clonat sparse la
`../cdep-api-poc` ca referință. venv la `.venv`, `romega-core` instalat editable.

`romega_core` (bibliotecă):
- ✅ `names.py` — normalizare nume RO (cedilă vs virgulă-jos, ordine NUME/Prenume, titluri) + Jaro-Winkler
- ✅ `provenance.py` — `SourceRef` + `Meta`
- ✅ `models.py` — entități canonice + enums + `make_id`
- ✅ `resolve.py` — **PersonRegistry** (entity resolution: crosswalk → blocking → matching; homonimi pe dată naștere; `romega_id` stabil)
- ✅ `http.py` — `Client` cu throttle **per-host** + SSL legacy + integrare bronze
- ✅ `bronze.py` — `BronzeStore` (cache content-addressed + manifest + dedup)
- ✅ `parse.py` — selectori parsel + decodare encoding (ISO-8859-2/win-1250/utf-8)
- ✅ `io.py` — export JSON (plic meta+data)

`pipeline/` (build):
- ✅ `silver.py` (staging DuckDB) · `gold/graph.py` (graf DuckDB, CTE recursive: control_chain + semnal conflict) · `gold/registry.py` (PersonRegistry persistent SQLite) · `export.py`
- ✅ `config.py` (loader sources.yaml, aplatizează `items`) · `run.py` (CLI `--source`/`--list`)

`connectors/`:
- ✅ `base.py` (protocol) · `parlament/cdep.py` (**portare fidelă**, testată pe HTML real `deputat_189.html` → Person canonic + crosswalk)

CI: ✅ `.github/workflows/source.yml` (generic) + `schedule.yml` (cron daily/weekly/monthly), YAML valid.

**Criterii „done" Faza 0:**
- [x] entity resolution `romega_id` stabil între rulări (in-memory determinist + persistat SQLite)
- [x] provenance: orice fapt → bronze artifact + URL + dată (`BronzeArtifact.source_ref()`)
- [x] connector cdep parsează HTML real → model canonic
- [~] „diff gol" vs cdep-api-poc pe date live — **necesită rulare pe runner-ul RO** (cdep.ro geo-blochează cloud)
- [~] CI end-to-end — workflows + CLI gata; **necesită înregistrarea runner-ului self-hosted RO**

**Faza 1 — Senat: COMPLETĂ (cod) — 50/50 teste.**
- ✅ `romega_core/dates.py` — parsare date RO factorizată (partajat cdep + senat)
- ✅ `connectors/parlament/senat.py` — listă + profil (GUID), `to_person` cu crosswalk `senat`
- ✅ **Unificare bicamerală testată**: aceeași persoană deputat(cdep)+senator(senat) → un singur `romega_id` cu ambele ID-uri externe
- ✅ `senat` înregistrat în CLI; fixture-uri sintetice (selectorii live de validat pe runner)

**Hardening (post-test live):**
- ✅ `fix_ro_diacritics` (cedilă→virgulă-jos) aplicat la nume/județ în connectoare
- ✅ provenance: `to_person` (cdep+senat) atașează `SourceRef`

**Faza 2 — Declarații ANI: v0 (cod) — 62/62 teste.**
- ✅ `connectors/ani/declaratii.py` — `parse_avere_text` (portat din analiza_avere_pdf.py: secțiuni I–VII, sume RON/valută, m²), `compute_avere_delta`, `parse_interese` (best-effort), `extract_pdf_text` (lazy pdfplumber)
- ✅ `connectors/ani/redaction.py` — guard PII (CNP/telefon/CI), `assert_clean` (critic legal)
- ✅ `AniConnector` skeleton headless (necesită Playwright; OCR pre-2022) — validat pe runner
- ✅ `ani` în CLI; fixture sintetic template ANI
- [~] headless live + OCR — necesită Playwright + acces ANI real (runner)

**Constatare live confirmată:** rezolvarea pe listă (fără dată naștere) supra-contopește
omonimi → connectoarele TREBUIE să rezolve cu `birth_date` din profile/declarații (ANI = ancoră).

**Faza 3 — Companii de stat (free-tier): v0 (cod) — 69/69 teste.**
- ✅ `connectors/fiscal/anaf.py` — connector `api` ANAF (status/CAEN/TVA/inactiv după CUI), **validat LIVE** (Romgaz/Hidroelectrica/Nuclearelectrica)
- ✅ `connectors/companii/amepip.py` — parser master list SOE (Anexa 1: CUI+denumire+autoritate)
- ✅ `connectors/companii/onrc_dump.py` — parser dump ONRC (firme + reprezentanți legali; GRATIS)
- ✅ `connectors/companii/registry.py` — `CompanyRegistry` (merge pe CUI) + `control_edges` (stat→SOE)
- ✅ `anaf_api` în CLI
- **Decizie D7 (T1 rezolvat):** gratis acum (reprezentanți legali din ONRC dump); acționariat cu % (termene/risco, plătit) **DEFERIT la final**.
- **Finding live:** endpoint ANAF v8 documentat = 404; corect = `…/api/PlatitorTvaRest/v9/tva` (reparat).
- [~] board-uri Art.51 (per companie) + BVB (listate) + MF bilanțuri bulk — pe runner / sub-val ulterior

**Faza 4 — Achiziții publice (SICAP): v0 (cod) — 73/73 teste.**
- ✅ `connectors/achizitii/sicap.py` — parser contracte (XLSX/CSV → Contract), `read_xlsx` (lazy openpyxl), agregate (total per firmă/autoritate), `awarded_contract_edges`, `SicapConnector.discover` (CKAN) **validat LIVE** (achizitii-publice-2025 = 28 resurse XLSX reale)
- ✅ `GraphStore.contracts_with_conflicted_suppliers()` — **follow-the-money**: firmă cu contract + membru CA cu funcție publică (red flag), testat
- ✅ `sicap_bulk` în CLI

🎯 **Lista de priorități 1-2-3-4 COMPLETĂ** (Senat → ANI → Companii → SICAP).

**Faza 5 — „restul" (în curs):**
- ✅ **Connector generic `institutie`** — config → Organization: **43 instituții centrale** (16 ministere + 23 agenții + guvern + 2 camere) + SUBORDINATE_OF (minister→guvern) + `find_declaration_links`
- ✅ **Tier 3 deconcentrate (templated)** — 29 tipuri serviciu × 42 unități = **1.218 instituții**; total **1.261 noduri Organization** din config, zero cod/instituție
- ✅ **Enrichment BNR** — curs valutar (XML, validat LIVE); ⬜ INS Tempo
- ✅ **Axa locală** (Consilii Județene, `local_cj`, tier separat) — 168 instituții. **Total acoperire: 1.429 instituții** (43 centrale + 1.218 deconcentrate + 168 locale)
- ⬜ Bugete & salarii (data.gov.ro + MF transparenta-bugetara)
- ⬜ Legislație (legislatie.just.ro SOAP) ↔ proiecte de lege
- ⬜ **Acționariat % (plătit) — DEFERIT la final** (D7)

**Mediu de validare:** ești în RO → scraping/API live funcționează de pe mașina ta (cdep.ro, ANAF, data.gov.ro confirmate). Runner self-hosted = pentru rulări programate/volum.

## Decizii luate (cu rațiune)

| # | Decizie | Rațiune |
|---|---|---|
| D1 | **Arhitectură hibridă** (JSON static public + DuckDB/SQLite la build) | Păstrează costul zero și provenance-ul imuabil din `cdep-api-poc`, dar adaugă putere relațională/graf pentru entity resolution și acționariat. DB doar la build (în CI), nu server de operat. |
| D2 | **Ordinea valurilor:** Senat → ANI (declarații) → Companii de stat + acționariat → SICAP → restul | Senat = quick win (refolosește scraperele de tip parlament). ANI = valoare civică maximă (sursă centrală pentru toți demnitarii). Companii+acționariat = follow-the-money. SICAP = contractele. |
| D3 | **DuckDB la build, SQLite pentru registre canonice** | DuckDB: embedded, citește CSV/Parquet direct, CTE recursive pentru graf, rulează în CI. SQLite: stabil, commit-abil, ține `romega_id`-urile și aliasurile între rulări. |
| D4 | **Monorepo `romega`** la `C:\Users\Maia\Downloads\python\altele\romega` | Proiect umbrelă care înglobează cdep + restul; `sources.yaml` ca single source of truth. |
| D5 | **`sources.yaml` = single source of truth** pentru connectors | Lista de surse (deliverable) și config-ul de execuție sunt același fișier — nu diverg. |
| D6 | **Redactările legale rămân redactate** (CNP, adrese, semnături) | Legea 176/2010 art. 6 + GDPR. Publicăm doar ce e deja public și anonimizat la sursă. |

## Tensiuni nerezolvate (de decis)

| # | Tensiune | Opțiuni |
|---|---|---|
| T1 | **Acționariat cu % la scară** nu există gratuit (ONRC dump = doar reprezentanți legali, nu asociați) | (a) doar reprezentanți legali din data.gov.ro (gratis, parțial); (b) API comercial — termene.ro / risco.ro (ACT ~1 RON/query) pentru asociați+%; (c) hibrid: gratis pentru bază, plătit on-demand pentru ținte de interes. **REZOLVAT (D7): gratis acum, plătit deferit la final.** |
| T2 | **UBO (beneficiari reali)** restricționat din 2025 (Legea 86/2025: interes legitim + taxă + semnătură; jurnaliștii pot fi refuzați) | Probabil în afara scopului automat. De urmărit cazuistica „interes legitim". |
| T3 | **Adâncimea instituțională** (Tier 3 deconcentrate ~1.000 + axa locală ~300) | Plan: Tier 2 (agenții centrale) prioritar; Tier 3 templated mai târziu; axa Consiliilor Județene modelată separat. |
| T4 | **Runner self-hosted** — cdep.ro/senat.ro geo-blochează cloud IPs | Reutilizăm setup-ul din `cdep-api-poc` (PC Windows în RO). De confirmat capacitatea pentru volum crescut (ANI = ~1.6M PDF-uri). |
| T5 | **OCR pre-2022** pentru declarații scanate ANI | Pipeline OCR (Tesseract RO / cloud). Cost/timp de estimat pe volum. |
| T6 | **`cdep-client` 404** la fetch | De confirmat dacă e privat/redenumit. Clientul nou (`web/`) îl va succeda oricum. |

## Următorii pași

1. **Faza 0 continuare:** `romega_core/http.py` — port `_http.py` din cdep + rate-limit
   per-host + `BronzeStore` (cache content-addressed) + teste offline (throttle/cache).
2. **Faza 0:** `pipeline/` pe DuckDB (bronze→silver→gold) + `io.py` (export JSON/Pagefind/feeds).
3. **Faza 0:** portează `connectors/parlament/cdep` pe noul core → test de regresie (diff gol vs cdep-api-poc).
4. Decide T1 (buget acționariat) — blochează partea grea din Faza 3 (poate aștepta până la Faza 3).

## Note de context

- `cdep-api-poc` acoperă deja: deputați, voturi, proiecte, amendamente, interpelări, comisii,
  moțiuni, sancțiuni, ordine de zi, **declarații (avere)**, stenograme, doc-comisii. Aceste
  scrapere sunt punctul de plecare pentru connector-ul `parlament`.
- Sursele verificate (iunie 2026) sunt în `docs/03-SOURCES.md` cu metoda de acces per sursă.
