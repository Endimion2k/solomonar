# STATE.md — ROMEGA

> Memorie de proiect: decizii, blocaje, tensiuni, poziția curentă.
> Actualizează ÎNAINTE de orice `/compact` sau la final de sesiune.

Owner: Cătălin Popa · Ultima actualizare: 2026-06-06

---

## Poziția curentă

> **🟢 RUNDA 2026-06-11c (commit 148) — STRAT DUCKDB GOLD:** `build_duckdb.py` realizează ultima piesă din
> arhitectură (medallion gold relațional). Încarcă toate entitățile+relațiile în DuckDB la build (person 56k,
> company 1256, person_company 21k edges, party/comisii/state_holding), engine efemer (gitignored). Interogări
> relaționale + CTE recursiv (expandare rețea persoană↔companie). Exportă **6 view-uri analitice** noi în API:
> sumar_sector/judet, companii_per_tutela, participatii_stat, oficiali_contracte, retele_coadministrare
> (`data/v1/analytics/`). Arhitectura din docs e acum COMPLETĂ cap-coadă.
>
> **🟢 RUNDA 2026-06-11b (commit 145):** CV-uri ~3× (**1.237 total**: 775 SOE/instituții cu 766 studii/exp,
> +449 OCR de pe site-urile localsoe) · **DNA 8.998 comunicate** (3×, 5.136 nume, cross-ref local 391/78 high) ·
> **senatori↔comisii în gold** (130, crosswalk GUID).
>
> **🟢 MILESTONE (2026-06-11) — 141 commit-uri, API LIVE.** Bază masivă + graf canonic + search:
> - **Declarații: 144.458** (76.838 avere + 67.620 interese) — deconcentrate+CFR+SOE+soe2+**localsoe (8.225,
>   SOE locale: căutare online 729 companii → 185 cu site, 10.177 PDF: CONPET/CNCIR/APPS/AFDJ/aeroporturi/porturi)**+
>   ministere+parlament, tot OCR-izat. Coverage companii: 493→834 cu declarații (goluri 729→398, -45%).
>   Follow-the-money confirmate: **12** (UNIFARM 3,8mld, Transgaz-Sterian, DPL Alba...).
> - **Companii stat: 1.256** + reps + **1.153 bilanț** · **firme cu contracte SICAP: 11.945** (achizitii).
> - **CV-uri: 634** · **Partide: 17** (subvenții 2008-26 + 402 RVC) · **Bugete: 6.389 UAT + 28 luni BGC**.
> - **GRAF GOLD canonic: 52.853 persoane** (romega_id stabil SQLite, institution-aware) + **search 54.126 entități**
>   (web/search.html) + **follow-the-money: 4 conflicte confirmate** (firmă în propria declarație de interese).
> - **Audit: DNA 2.999 comunicate** (cross-ref local) · Curtea de Conturi 11 · legislație 41 (connectori live).
> - Comisii CDep (1.852 PLx, 20.574 doc) · 175 moțiuni · inventar 167 surse declarații.
> - **stats.json** = sumar live. Gap-uri: senat comisii/moțiuni (postback, fezabil acum), ANI central (CAPTCHA), SOE obscure.
>
> **✅ FOLLOW-THE-MONEY (2026-06-10) — contract→firmă→persoană:** SICAP harvest 2023-25 (11.945 firme
> câștigătoare, `achizitii/contracte_firme.json`) → ONRC reps extins la câștigători (12.777 companii, 21.476
> reps) → gold leagă contract↔firmă↔persoană (49.008 persoane). ONEST: link nume-bazat = majoritar OMONIMI
> (ENGIE/Groupama = namesake, NU parlamentarul). Verificare defensabilă = firma în PROPRIA declarație de interese
> → **2 CONFIRMATE din 13 leaduri** (Gherasim Laura/AUR → ACG Construction 263,5M lei; Vidra Vlad/SOS → COPROT).
> `graf/follow_the_money.json` separă clar CONFIRMATE vs leaduri_neverificate (NU acuzații). Gold v2 institution-aware
> (omonimi separați pe organizație). RĂMAS: verificare interese pe toți + dată naștere ONRC + promovare DuckDB.
>
> **✅ STRAT GOLD (2026-06-10) — rezoluție canonică:** `pipeline/build_gold.py` pe `romega_core.resolve`
> → 21.058 persoane canonice cu **romega_id stabil** în `data/gold/registry.sqlite`. Parlamentarii
> rezolvați cu data nașterii (332 high-conf) ancorează registrul. Cross-links **stratificate pe încredere**:
> 45 HIGH fiabile vs candidați med/low. Omonimii fără CNP flag-uiți LOW (nu ascunși). `persoane_gold.json`
> + `rezolutie_stats.json`. Limita onestă: separare perfectă a omonimilor cere CNP (redactat legal D6).
> RĂMAS gold v2: rezoluție institution-aware (separă același-nume la instituții diferite) + promovare DuckDB.
>
> **✅ IMPLEMENTAT (2026-06-10) — P0 Bugete + Partide:** subvenții partide (anual 2008-2026, 20 partide) ·
> rapoarte RVC (22, Monitorul Oficial) · bugete UAT (6.389, toate, 2024-25) · BGC (28 luni). Vezi
> `data/v1/partide/` + `data/v1/bugete/` + harvest_{subventii_partide,rvc_partide,bugete_uat,bgc}.py.
> RĂMAS (opțional): extindere RVC la toți anii/partidele (~500), subvenții lunare (necesită spreadsheet EFOR sursă),
> data.gov.ro index, FOREXEBUG granular per-entitate, bugete locale ani vechi.
>
> **TO-DO (2026-06-10) — surse VERIFICATE, workflow 30 agenți:**
>
> **(A) FINANȚARE PARTIDE parlamentare** — ⚠️ AEP (roaep.ro + finantarepartide.ro) = **reCAPTCHA Enterprise pe tot
>   domeniul, inclusiv PDF-uri → NU construi pipeline pe el** (citează-l doar ca origine). Căi reale:
>   - 🟢 **[P0] Monitorul Oficial via `legislatie.just.ro/public/DetaliiDocument/{id}`** — rapoartele financiare
>     anuale ale partidelor (RVC, art.16 L.334/2006): cotizații, venituri pe surse, donatori. HTML server-rendered,
>     FĂRĂ captcha/JS, scalabil. ~90 partide. Ex. doc 297054 = USR 2024. **Singura sursă oficială ușor automatizabilă.**
>   - 🟢 **[P0] banipartide.ro/subventii (EFOR)** — Looker Studio public (raport b0177427-ae62-4d70-8c27-0215005733b4):
>     tabel An/Lună/Partid/Subvenții din 2008 (1.264 înreg.) + cheltuieli pe categorii din 2021 + contracte. Export CSV. NEblocat.
>   - 🟡 [P2] EFOR PDF-uri anuale (expertforum.ro) — cross-check cifre anuale (firecrawl proxy=enhanced).
>   - Legea 334/2006 (metodologie): just.ro doc 73672. AVOID: RVC scanate per-scrutin (captcha+OCR).
>
> **(B) BUGETE instituții/locale** — surse confirmate cu download direct:
>   - 🟢 **[P0 START] DPFBL/MDLPA** `dpfbl.mdrap.ro/sit_ven_si_chelt_uat.html` — centralizator **TOATE UAT-urile**
>     (comune/orașe/municipii/județe), venituri+cheltuieli, XLSX/an 1999-2025 (centra2025.xlsx). ⚠️ cert TLS invalid
>     (curl -k/http) + parsing block-aware (Anexa 24). **Cea mai bună sursă locală agregată.**
>   - 🟢 **[P0] MF buletin execuții BGC** `mfinante.gov.ro/static/10/Mfp/buletin/executii/bgc{DDMMYYYY}.xlsx` —
>     Buget General Consolidat lunar 2023-2026, **URL predictibil** (ultima zi a lunii). Agregat național (nu per-entitate).
>   - 🟡 [P1] data.gov.ro CKAN (65 seturi execuție) — index complementar, fragmentat. transparenta.eu (Funky Citizens) — prototip.
>   - 🔴 granular per-entitate: ANAF FOREXEBUG (`extranet.anaf.mfinante.gov.ro/.../EXECUTIEBUGETARA`, ~13.700 entități, XML) — greu.
> - Detalii complete: `docs/05-EXTERNAL-APIS.md` (de extins) + output workflow research-bugete-partide.
>
> **MILESTONE (2026-06-07) — ~81 commit-uri:** De la noduri-config la o bază reală mare:
> - **Declarații avere+interese: ~62.000** (deconcentrate text+OCR · ministere · ANPM · ambele camere
>   parlament · DSP) — guard PII a blocat sutele cu CNP. OCR scanate la **81%** (12.8k extrase din scane).
> - **Comisii CDep**: 33 comisii → 2.971 ședințe → 1.852 PLx → **20.574 documente** (19.408 arhivate).
> - **Moțiuni**: 175 (43 cenzură + 132 simple, 2000-2024).
> - **Companii de stat**: 1.256 + **reprezentanți legali ONRC pe 1.250** (4.053 admini — CFR/Tarom/Romgaz).
> - Parlament: 335 deputați + 134 senatori (+ declarații ambele camere).
>
> **ÎN CURS:** OCR scanate deconcentrate (GPU, ~28h, reluabil — `_finalize` manual publică progresul).
>
> **BATCH DUPĂ OCR (decis B, 2026-06-07):**
> 1. **#2 servicii deconcentrate cu registru național** (refolosind harvest_deconcentrate +
>    harvest_declaratii_deconcentrate + OCR):
>    - **APIA** — 49 județe la `apia.org.ro/centru-judetean/{judet}`; publică DA/DI native (confirmat) ✅
>    - **CAS** — directory `cnas.ro/cjas/` (case județene) ✅
>    - **ANAF/Finanțe** — declarații central-ish (`anaf.ro/.../structura_organizatorica`); de verificat pattern ANMAP
>    - **CNPP/CJP** — mai greu (case-judetene 404; de găsit altă cale)
>    - restul tipuri (AJPIS, DJC, GNM, OPC, DRV, ORC...) — discovery per registru/tipar
> 2. **Ministere/agenții SCANATE** → OCR (deferite în pass-ul text; coada GPU)
> 3. **Senat** (comisii + moțiuni simple + declarații) — scraper Playwright STATEFUL dedicat (ASP.NET)
> 4. **Companii**: bilanțuri MF (cifre) · declarații conducere SOE (ANI central) · acționariat % (plătit, ULTIMUL)
> 5. Rezolvare reprezentanți→Person + muchii LEGAL_REP + link PLx↔inițiatori (graf)
> 6. Curățenie: șterge `avere_toate.json` (378) + `avere_dsp.json` (151) — superseded.

> **🟢 INVENTAR DATE REALE (2026-06-04)** — de la noduri-config la date reale descărcate:
> - **335 deputați** + **134 senatori** (profile live)
> - **1.256 companii de stat** (146 AMEPIP centrale+ANAF · **1.114 LOCALE** via companiidestat.ro API)
> - **29.921 contracte SICAP** (118 mld RON) · **2.482 firme ONRC** (din 4M, streaming 650MB) · **11.700 org ANI**
> - **~529 declarații de avere reale** parsate (378 ministere+agenții crawl depth 3 + 151 DSP județene),
>   redactare-curate, **fără CAPTCHA** (Legea 176/2010, per-instituție) — guard PII a blocat declarații cu CNP
> - **instituții accesate live:** 15 ministere + 20 agenții + 17 DSP · cache bronze **2.052 URL-uri**
> - **eficiență:** fetch_many (paralel cross-host) + cache pe URL (1082× pe cache hit)
>
> **Limite reale (nu de cod):** Tier-3 complet (1.218) NU e automatizabil — URL-urile serviciilor
> deconcentrate nu-s într-un registru cu linkuri (MS listează DSP ca director JS); ghicirea = ~40%.
> ANI central (Turnstile) + AEP (reCAPTCHA) = solver/om-în-buclă. Acționariat % = plătit (D7).
> **42 commit-uri · 102 teste verzi · API LIVE.**

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
> **🟡 Item 3 (coverage):** ✅ Curtea de Conturi + ✅ DNA (validate live).
> **ANI:** ✅ harvest API DESCHIS — **11.700 organizații** + 1.109 funcții + 42 județe în
> `data/v1/ani/`. Căutarea de declarații = **Cloudflare Turnstile** (anti-bot) → headless basic
> NU trece; API search e Spring Boot la `/api/` (fields deschise, search gated). Parser+guard+delta gata.
> **AEP:** reCAPTCHA. **Camoufox DEBLOCAT** — execuția din `AppData\Local` era blocată de o
> politică (AppLocker/ASR); copiat la `altele/cmf` (non-AppData) → rulează (Firefox 135). DAR
> **ambele CAPTCHA rezistă la Camoufox** (testat headless + non-headless + humanize + 36s): ANI
> Turnstile nu eliberează token la submit; AEP rămâne "Checking your browser". → necesită
> **solver CAPTCHA comercial (2captcha/capsolver) SAU human-in-the-loop** (rezolvă o dată, refolosește sesiunea).
>
> **Backlog (necesită acțiunea ta / runner):** ANI-search + AEP = solver CAPTCHA sau om-în-buclă (Camoufox singur NU ajunge). ANI fields deja harvestate. Restul: deblocare Camoufox (excludere
> antivirus pt. camoufox.exe) SAU rulare pe runner SAU solver Turnstile · bugete/salarii (heterogen) ·
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

**Faza 7 — Activitatea comisiilor parlamentare (BACKLOG — cerut de owner 2026-06-06):**

Integrare COMPLETĂ a activității comisiilor: **ședințe → ordini de zi → PLx-uri → documente**,
domeniu **2024 → prezent**. Întâi Camera Deputaților, apoi Senatul (dacă are structură similară).

Structura cdep.ro (URL-uri confirmate de owner):
1. **Lista comisiilor:** `https://www.cdep.ro/ords/co/sedinte2015.comisii`
2. **Ședințe per comisie/an:** `https://www.cdep.ro/ords/co/sedinte2015.lista?tip={ID_COMISIE}&an={AN}`
   (ex. comisia IT: `tip=19&an=2026`)
3. **Ordinea de zi (PDF) per ședință:** ex.
   `https://www.cdep.ro/ords/co/docs?F1606199231/Ordinea%20de%20zi%202%20iunie%202026.pdf`
   — în acest PDF sunt listate **PLx-urile** dezbătute, fiecare cu link
4. **Pagina proiectului (PLx):** `https://www.cdep.ro/ords/pls/proiecte/upl_pck2015.proiect?cam=2&idp={IDP}`
   (ex. PLx 372/2026 → `idp=23259`)
5. **Documentele PLx** (pe pagina proiectului — pot fi MAI MULTE avize/rapoarte per PLx):
   - expunere de motive: `…/proiecte/2026/300/70/2/em423.pdf`
   - forma inițiatorului: `…/pl423.pdf`
   - aviz CSM: `…/csm423.pdf`
   - + alte avize / rapoarte (număr variabil)

De făcut:
- ✅ Connector `parlament/comisii` (cdep) — `connectors/parlament/comisii.py` + `pipeline/harvest_comisii.py`
- ✅ Crawl CDep 2024-2026: **33 comisii → 2.971 ședințe → 1.852 PLx → 20.574 documente** indexate
  (`data/v1/comisii/comisii.json` + `sedinte.json` + `plx.json`) — LIVE
- ✅ Descărcat + arhivat în bronze: **19.408/20.574 documente** (94%; 1.166 = 404/linkuri moarte)
- ✅ **Senatul — COMPONENȚA comisiilor REZOLVATĂ (2026-06-11):** `harvest_comisii_senat.py` → 23 comisii,
  322 locuri, 131 senatori. Taburile comisiei sunt URL-uri GET (NU postback cum se temea): `comisii.aspx`
  (23 comisii+GUID) + `ComponentaComisii.aspx?ComisieID=GUID` (membri+ParlamentarID). `senat_comisii.json` +
  index senator→comisii. RĂMAS Senat: ordinea de zi/ședințe (ProgramLucruZi date-postback) + documente
  (afisarelistafisiere = gol pt. comisii) + roluri conducere (acum toți „Membru"). Nota veche (gated) ↓:
- ⬜ ~~Senatul — COMPLET ASP.NET-gated, necesită browser automation dedicat~~ (investigat 2026-06-07):
  - 23 comisii la `senat.ro/comisii.aspx`; agenda = `ProgramLucruZi.aspx?ComisieID={GUID}` cu câmp
    de dată `txtData` → postback per zi; **NU există listă de ședințe** (crawl exhaustiv = ~14k
    postback-uri oarbe pe dată × 23 comisii = impractic).
  - Proiecte = `LegiProiect.aspx`: grid paginat prin postback (Page$2..Page$Last) + search-driven,
    **zero linkuri fișă** la încărcare. Parametri URL de dată NU schimbă conținutul (postback pur).
  - Încercat 5 unghiuri (param dată, render Playwright, listă proiecte, LegiProiect, fișe) — toate gated.
  - Concluzie: necesită un scraper Playwright STATEFUL dedicat (navigare __VIEWSTATE/__EVENTVALIDATION
    pas-cu-pas) — fragil + greu, NU se rulează robust în paralel cu OCR. De făcut într-o sesiune
    dedicată (Chromium liber, după ce termină OCR) SAU în task-ul senat.ro deja spawnat (declarații).
  - cdep e bicameral-dominant + multe PLx partajate au deja avizele Senatului în documentele indexate.
- ⬜ Model canonic în graf: `Committee`/`CommitteeSession`/`LegislativeProject`/`LegislativeDocument`
  + muchii comisie→ședință→PLx→documente (acum sunt JSON-index; de promovat în DuckDB/graf)
- ⬜ Leagă PLx ↔ inițiatori (deputați/senatori din ROMEGA) → graf „cine a inițiat / avizat ce"
- ⬜ Opțional: parsare conținut documente (expunere de motive etc.) + reducere „alt" (7.178 neclasif.)

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
| T1 | **Acționariat cu % la scară** nu există gratuit (ONRC dump = doar reprezentanți legali, nu asociați) | (a) doar reprezentanți legali din data.gov.ro (gratis, parțial); (b) API comercial — termene.ro / risco.ro (ACT ~1 RON/query) pentru asociați+%; (c) hibrid: gratis pentru bază, plătit on-demand pentru ținte de interes. **REZOLVAT PARȚIAL (2026-06-11): confirmat că ONRC open-data = DOAR reps (0 dataset asociați). DAR pt. SOE-urile LISTATE la BVB acționariatul % e PUBLIC+gratis → `harvest_actionariat_bvb.py`: 16 companii, 12 cu participație stat (Hidroelectrica 80%, Romgaz 70%, Nuclearelectrica 82,5%...). Firme NElistate: acționarii rămân plătiți (termene.ro), deferit.** |
| T2 | **UBO (beneficiari reali)** restricționat din 2025 (Legea 86/2025: interes legitim + taxă + semnătură; jurnaliștii pot fi refuzați) | Probabil în afara scopului automat. De urmărit cazuistica „interes legitim". |
| T3 | **Adâncimea instituțională** (Tier 3 deconcentrate ~1.000 + axa locală ~300) | Plan: Tier 2 (agenții centrale) prioritar; Tier 3 templated mai târziu; axa Consiliilor Județene modelată separat. |
| T4 | **Runner self-hosted** — cdep.ro/senat.ro geo-blochează cloud IPs | Reutilizăm setup-ul din `cdep-api-poc` (PC Windows în RO). De confirmat capacitatea pentru volum crescut (ANI = ~1.6M PDF-uri). |
| T5 | **OCR pre-2022** pentru declarații scanate ANI | Pipeline OCR (Tesseract RO / cloud). Cost/timp de estimat pe volum. |
| T6 | **`cdep-client` 404** la fetch | De confirmat dacă e privat/redenumit. Clientul nou (`web/`) îl va succeda oricum. |

## Următorii pași

0. **Faza 7 — Activitatea comisiilor (PRIORITAR, cerut 2026-06-06)** — vezi secțiunea dedicată:
   connector `parlament/comisii`, crawl 2024→prezent (comisii → ședințe → ordini de zi PDF → PLx
   → documente), deputați apoi senat. Rulează după ce se eliberează GPU/CPU (OCR + ministere în curs).
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
