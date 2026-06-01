# STATE.md — ROMEGA

> Memorie de proiect: decizii, blocaje, tensiuni, poziția curentă.
> Actualizează ÎNAINTE de orice `/compact` sau la final de sesiune.

Owner: Cătălin Popa · Ultima actualizare: 2026-06-01

---

## Poziția curentă

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

**Următor: Faza 1 — Senat** (connector `parlament/senat`, crosswalk GUID↔cdep↔romega_id, bicameral).

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
| T1 | **Acționariat cu % la scară** nu există gratuit (ONRC dump = doar reprezentanți legali, nu asociați) | (a) doar reprezentanți legali din data.gov.ro (gratis, parțial); (b) API comercial — termene.ro / risco.ro (ACT ~1 RON/query) pentru asociați+%; (c) hibrid: gratis pentru bază, plătit on-demand pentru ținte de interes. **De decis bugetul.** |
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
