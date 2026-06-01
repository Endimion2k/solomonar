# 03 — CATALOG DE SURSE

> Inventarul complet al surselor de date pentru ROMEGA, verificat (iunie 2026).
> Coloana **Acces:** `api` (REST/SOAP) · `bulk` (fișiere descărcabile) · `scrape` (HTML/PDF) ·
> `headless` (SPA JS) · `paid` (comercial). **Fază** = valul din `00-MASTERPLAN.md`.
>
> Echivalentul machine-readable (config pentru connectors) e în [`../config/sources.yaml`](../config/sources.yaml).

> ⚠️ **Context politic (iunie 2026):** Guvernul e în interimat/demisionar din 5 mai 2026.
> *Structura* ministerelor e stabilă; *miniștrii* sunt parțial interimari. Modelăm instituțiile,
> nu persoanele — de aceea `Organization` e versionat în timp (vezi `02-DATA-MODEL.md`).

---

## A. PARLAMENT

| # | Sursă | Domeniu | Date | Acces | Format | Fază |
|---|---|---|---|---|---|---|
| A1 | Camera Deputaților | `cdep.ro` | deputați, voturi, proiecte, amendamente, interpelări, comisii, moțiuni, sancțiuni, ordine zi, declarații, stenograme, doc-comisii | scrape | HTML/XML/PDF | 0 (portare) |
| A2 | Senat | `senat.ro` | senatori, voturi plen, proiecte, întrebări/interpelări, comisii, stenograme, declarații | scrape | HTML/PDF | **1** |

**Note Senat (din research):** ASP.NET WebForms, chei GUID, **fără open data**. URL-uri cheie:
`FisaSenatori.aspx`, `FisaSenator.aspx?ParlamentarID={GUID}`, `Voturiplen.aspx`,
`legiproiect.aspx`, `Legis/Lista.aspx`, `VizualizareIntrebariInterpelari.aspx`,
`EnumComisii.aspx?Permanenta=1`, `StenoPag2.aspx`. **Nu** împarte ID-uri cu cdep.ro →
crosswalk pe nume+legislatură. `cdep.ro` e sursa mai bună pentru ciclul **bicameral** al legii
(`upl_pck` cu `cam=1` = Senat). 43 circumscripții (41 județe + București + diaspora).

---

## B. CENTRUL GUVERNULUI

| # | Sursă | Domeniu | Date | Acces | Fază |
|---|---|---|---|---|---|
| B1 | Guvernul României | `gov.ro` | componență, ședințe, HG-uri, organigramă | scrape | 5 |
| B2 | Secretariatul General al Guvernului (SGG) | `sgg.gov.ro` | coordonare AMEPIP, politica de proprietate a statului | scrape | 5 |
| B3 | Cancelaria Prim-Ministrului | `gov.ro` | structuri din subordinea PM | scrape | 5 |

---

## C. MINISTERE (16 — structura curentă 2026)

Sursă autoritativă: `gov.ro/ro/guvernul/organizare/ministere`. Modelate ca `Organization`
versionate (granița 16↔19 se mută la fiecare cabinet).

| # | Minister | Domeniu | Fază |
|---|---|---|---|
| C1 | Ministerul Afacerilor Externe | `mae.ro` | 5 |
| C2 | Ministerul Afacerilor Interne | `mai.gov.ro` | 5 |
| C3 | Ministerul Apărării Naționale | `mapn.ro` | 5 |
| C4 | Ministerul Justiției | `just.ro` | 5 |
| C5 | Ministerul Finanțelor | `mfinante.gov.ro` | 3/5 |
| C6 | Ministerul Economiei, Digitalizării, Antreprenoriatului și Turismului | `economie.gov.ro` | 5 |
| C7 | Ministerul Energiei | `energie.gov.ro` | 3/5 |
| C8 | Ministerul Transporturilor și Infrastructurii | `mt.ro` | 3/5 |
| C9 | Ministerul Agriculturii și Dezvoltării Rurale | `madr.ro` | 5 |
| C10 | Ministerul Mediului, Apelor și Pădurilor | `mmediu.ro` | 5 |
| C11 | Ministerul Dezvoltării, Lucrărilor Publice și Administrației | `mdlpa.ro` | 5 |
| C12 | Ministerul Investițiilor și Proiectelor Europene | `mfe.gov.ro` | 5 |
| C13 | Ministerul Muncii, Familiei, Tineretului și Solidarității Sociale | `mmuncii.gov.ro` | 5 |
| C14 | Ministerul Sănătății | `ms.ro` | 5 |
| C15 | Ministerul Educației și Cercetării | `edu.ro` | 5 |
| C16 | Ministerul Culturii | `cultura.ro` | 5 |

**Articulații instabile (de versionat cu grijă):** Digitalizare (uneori minister separat),
Sport (retrogradat la agenție), Familie/Tineret (uneori la Muncii), Energie vs Economie.

---

## D. AGENȚII & AUTORITĂȚI CENTRALE (Tier 2 — prioritate de indexare)

### D.1 Fiscal / vamă / achiziții
| # | Instituție | Domeniu | Subordonare | Date utile | Fază |
|---|---|---|---|---|---|
| D1 | **ANAF** | `anaf.ro` | Min. Finanțelor | **API CUI** (status, CAEN, TVA, inactiv), bilanțuri bulk | 3 |
| D2 | Autoritatea Vamală Română | `customs.ro` | Min. Finanțelor | operațiuni vamale | 5 |
| D3 | **ANAP** (Achiziții Publice) | `anap.gov.ro` | Min. Finanțelor | cadru achiziții, link SICAP | 4 |

### D.2 Integritate / anticorupție
| # | Instituție | Domeniu | Subordonare | Date utile | Fază |
|---|---|---|---|---|---|
| D4 | **ANI** (Integritate) | `integritate.eu` | autonom (Parlament) | **declarații avere+interese, central** | **2** |
| D5 | DNA | `pna.ro` | PÎCCJ | comunicate, rechizitorii (semnale) | 5 |
| D6 | DGA | `mai-dga.ro` | MAI | anticorupție internă | 5 |
| D7 | ANABI | `anabi.just.ro` | Min. Justiției | bunuri indisponibilizate | 5 |

### D.3 Registre / cadastru
| # | Instituție | Domeniu | Subordonare | Date utile | Fază |
|---|---|---|---|---|---|
| D8 | **ONRC** | `onrc.ro` (`portal.onrc.ro`) | Min. Justiției | firme, reprezentanți; UBO (restricționat) | 3 |
| D9 | ANCPI | `ancpi.ro` | MDLPA | cadastru, OCPI județene | 5 |

### D.4 Audit / finanțe publice
| # | Instituție | Domeniu | Subordonare | Date utile | Fază |
|---|---|---|---|---|---|
| D10 | **Curtea de Conturi** | `curteadeconturi.ro` | autonom (Parlament) | rapoarte audit (semnale instituții/SOE) | 5 |
| D11 | ANRP | via `mfinante.gov.ro/anrp` | Min. Finanțelor | restituiri proprietăți | 5 |

### D.5 Reglementatori sectoriali (autonomi)
| # | Instituție | Domeniu | Date utile | Fază |
|---|---|---|---|---|
| D12 | **BNR** | `bnr.ro` | curs valutar XML (enrichment) | 5 |
| D13 | **ASF** | `asfromania.ro` | piețe financiare, asigurări, pensii II/III | 5 |
| D14 | ANRE | `anre.ro` | reglementare energie | 5 |
| D15 | ANCOM | `ancom.ro` | comunicații | 5 |
| D16 | Consiliul Concurenței | `consiliulconcurentei.ro` | decizii concurență, ajutor de stat | 5 |
| D17 | ANSPDCP | `dataprotection.ro` | autoritatea GDPR | 5 |

### D.6 Electoral
| # | Instituție | Domeniu | Date utile | Fază |
|---|---|---|---|---|
| D18 | **AEP** | `roaep.ro` | finanțare partide, alegeri | 5 |
| D19 | BEC | `bec.ro` | rezultate per scrutin (temporar) | 5 |

### D.7 Contestații achiziții
| # | Instituție | Domeniu | Date utile | Fază |
|---|---|---|---|---|
| D20 | **CNSC** | `cnsc.ro` | contestații licitații (semnale) | 4/5 |

### D.8 Social / sănătate
| # | Instituție | Domeniu | Subordonare | Date utile | Fază |
|---|---|---|---|---|---|
| D21 | CNAS | `cnas.ro` | Min. Sănătății | asigurări sănătate | 5 |
| D22 | CNPP | `cnpp.ro` | Min. Muncii | pensii publice | 5 |
| D23 | ANOFM | `anofm.ro` | Min. Muncii | ocupare forță de muncă | 5 |
| D24 | ANPIS | `mmanpis.ro` | Min. Muncii | plăți și inspecție socială | 5 |

### D.9 Statistică / consumator
| # | Instituție | Domeniu | Date utile | Fază |
|---|---|---|---|---|
| D25 | **INS** | `insse.ro` (Tempo, port 8077) | statistică (enrichment) | 5 |
| D26 | ANPC | `anpc.ro` | protecția consumatorilor | 5 |

> ⚠️ **ANRMAP este desființată** (2015, funcțiile la ANAP) — a nu se indexa ca activă.
> Domenii corecte de reținut: ANI = `integritate.eu`, ASF = `asfromania.ro`, AEP = `roaep.ro`.

---

## E. DECLARAȚII DE AVERE ȘI INTERESE (ecosistemul ANI)

| # | Componentă | URL | Rol | Acces |
|---|---|---|---|---|
| E1 | e-DAI (depunere) | `dai.integritate.eu` | depunere electronică (din 2022, semnătură calificată) | — (backend) |
| E2 | **Portal public nou** | `declaratii.integritate.eu` | căutare publică (SPA JS) | **headless** |
| E3 | Portal vechi / depozitar | `old-declaratii.integritate.eu`, `depozitar.integritate.eu` | arhivă 2008–2022 | scrape |

**Realitate de acces (din research):** **fără API/bulk**. ~1.6M declarații. Căutare după
nume + avansată (categorie instituție, instituție, funcție, localitate, județ, tip, an).
PDF-uri: **2022+ native (text)**, **pre-2022 scanate → OCR necesar**. Template legal
standardizat (imobile, vehicule, active financiare, datorii, venituri, cadouri / acțiuni,
funcții CA, contracte). **Bază legală:** Legea 176/2010. **Redactate la sursă:** CNP, adrese,
semnături — rămân redactate. *Fază 2.*

> Fiecare instituție publică **și** pe site propriu declarațiile angajaților (aceeași
> declarație, sursă redundantă) — util ca fallback/verificare.

---

## F. DATE FISCALE & FINANCIARE DE FIRMĂ

| # | Sursă | Date | Acces | Format | Limite | Fază |
|---|---|---|---|---|---|---|
| F1 | **ANAF — API platitori TVA** | per CUI: denumire, adresă, nrRegCom, CAEN, status TVA, TVA la încasare, inactiv, split TVA, e-Factura | api | JSON | 100 CUI/req, 1 req/s, fără auth | 3 |
| F2 | **ANAF — bilanțuri (bulk)** | situații financiare per CUI, pe an | bulk | TXT+CSV | via data.gov.ro `situatii_financiare_{an}` (2012–2024) | 3 |
| F3 | **MF — info fiscale și bilanțuri** | căutare per CUI: obligații, bilanțuri ~6 ani, datorii la buget | scrape | HTML | fără API (single-CUI live) | 3 |
| F4 | MF — venituri salariale | liste salarii pe funcții publice | bulk/scrape | HTML/XLSX | — | 5 |
| F5 | MF — Forexebug / transparență bugetară | execuție bugetară per instituție | bulk/scrape | XLSX/PDF | `transparenta-bugetara`, lunar | 5 |

**Endpoint ANAF (verificat):** `https://webservicesp.anaf.ro/PlatitorTvaRest/api/v8/ws/tva`
(POST, body `[{"cui":7436636,"data":"2024-07-02"}]`). Doc:
`https://static.anaf.ro/static/10/Anaf/Informatii_R/Servicii_web/doc_WS_V8.txt`.

---

## G. COMPANII DE STAT (SOE)

| # | Sursă | Date | Acces | Note | Fază |
|---|---|---|---|---|---|
| G1 | **AMEPIP — Raport anual, Anexa 1** | **master list**: CUI + nume + autoritate tutelară | bulk | PDF (68 p.) | sursa autoritativă; ~146 centrale + 1.174 locale = **1.320 monitorizate** | 3 |
| G2 | AMEPIP — dashboard / tablou de bord | indicatori per companie, liste administratori | scrape | HTML | fără API | 3 |
| G3 | **companiidestat.ro** (independent) | 1.247 indexate / 1.502 urmărite, salarii execubtivi (143 centrale), subvenții, 2019–2024 | scrape/api? | web | cel mai bun agregator gata-făcut; API menționat, nedocumentat | 3 |
| G4 | OUG 109/2011 Art. 51 — site-uri proprii SOE | CA/directorat + CV + remunerație, decizii, rapoarte | scrape | HTML/PDF | conformare **inegală**; per companie | 3 |
| G5 | **BVB** | `bvb.ro` | board, hotărâri AGA, financiare pentru SOE listate | scrape | filings | Hidroelectrica, Romgaz, Nuclearelectrica, Transgaz, Transelectrica, Conpet, Oil Terminal | 3 |

**Master list (2024 AMEPIP):** `https://amepip.gov.ro/wp-content/uploads/2025/10/RAPORT-ANUAL-PRIVIND-ACTIVITATEA-INTREPRINDERILOR-PUBLICE-IN-ANUL-2024.pdf`.
Cadru legal: **Legea 187/2023** (modifică OUG 109/2011), AMEPIP creat prin **HG 617/2023**.

**SOE mari (centrale, pe minister):**
- *Energie:* Hidroelectrica, Romgaz, Nuclearelectrica, Transgaz, Transelectrica, Electrocentrale, CE Oltenia.
- *Transporturi:* CFR SA, CFR Călători, CFR Marfă, ROMATSA, Aeroporturi București, Metrorex, Registrul Auto Român.
- *Economie/altele:* Poșta Română, Tarom, Salrom, Loteria Română, Imprimeria Națională, Oil Terminal.

> **Universul SOE:** AMEPIP monitorizează 1.320 (OUG 109/2011); alte numărători citează
> ~1.421–1.735 (incl. inactive/insolvente). Folosim 1.320 ca cifră defensabilă, ~1.500 ca univers larg.

---

## H. ACȚIONARIAT / PROPRIETATE / UBO

| # | Sursă | Date | Acces | Cost | Asociați + %? | Fază |
|---|---|---|---|---|---|---|
| H1 | **data.gov.ro — dump ONRC** | firme, reprezentanți legali, CAEN, status, sucursale | bulk | gratis (CC BY 4.0) | ❌ doar **reprezentanți legali** | 3 |
| H2 | ONRC RECOM | date de bază firmă | scrape | gratis (info, fără valoare legală) | ❌ | 3 |
| H3 | ONRC documente oficiale | certificat constatator, InfoCert | api/scrape | **plătit** (8–250 RON/doc) | parțial | on-demand |
| H4 | **Registrul Beneficiarilor Reali (UBO)** | beneficiari reali | restricționat | taxă + interes legitim + semnătură | ⚠️ **restricționat** (Legea 86/2025) | — |
| H5 | **termene.ro** (API) | „Asociați și Administratori": nume, funcție, **%**, dată naștere, financiare, datorii ANAF, dosare | api/**paid** | abonament (la cerere) | ✅ **da** | 3 |
| H6 | **risco.ro** (API ACT) | acționari + cote, grupuri de firme | api/**paid** | ~1 RON/query, min. 100 RON/lună | ✅ **da** | 3 |
| H7 | openapi.ro (API) | info firmă, CAEN, TVA, financiare | api | gratis 100/lună, apoi tiers | ❌ fără acționari | enrichment |
| H8 | listafirme.eu (API) | firme, rapoarte (ANAF+ONRC+BPI) | api/**paid** | credite/query | parțial | 3 |

> **Tensiunea T1 (vezi STATE.md):** acționariat cu % la scară **nu există gratis**. Decizie de
> buget necesară: gratis (doar reprezentanți legali H1) vs plătit on-demand (H5/H6 pentru
> ținte prioritare). **UBO (H4) e practic în afara scopului automat** — restricționat legal,
> jurnaliștii pot fi refuzați.

---

## I. ACHIZIȚII PUBLICE (SICAP / SEAP)

| # | Sursă | Date | Acces | Format | Note | Fază |
|---|---|---|---|---|---|---|
| I1 | **data.gov.ro — achiziții** | achiziții directe, contracte, anunțuri atribuire, modificări | bulk | XLSX | `achizitii-publice-{an}`, 28 fișiere/an, publisher ADR | 4 |
| I2 | e-licitatie istoric (legacy) | notices, contracte, achiziții directe | api | JSON | `istoric.e-licitatie.ro/api-pub/C_PUBLIC_*` — **nedocumentat, fragil** | 4 (opțional) |

> **Fără OCDS funcțional** (componenta de export nu a fost niciodată operaționalizată).
> Calea stabilă = XLSX bulk; calea bogată = JSON legacy nesusținut.

---

## J. LEGISLAȚIE

| # | Sursă | Date | Acces | Format | Note | Fază |
|---|---|---|---|---|---|---|
| J1 | **legislatie.just.ro** (Portal Legislativ) | 150.000+ acte normative | api | XML (SOAP) | `GetToken` → `Search`; token gratis | 5 |
| J2 | Monitorul Oficial | gazeta oficială PDF | — | PDF | `monitoruloficial.ro` **paywall** — folosim J1 | — |

---

## K. ENRICHMENT (context economic/statistic)

| # | Sursă | Date | Acces | Format | Note | Fază |
|---|---|---|---|---|---|---|
| K1 | **BNR** | curs valutar | api | XML | `bnr.ro/nbrfxrates.xml`, arhivă din 2005; TLS 1.2 | 5 |
| K2 | **INS Tempo** | statistică oficială | api | JSON | `statistici.insse.ro:8077/tempo-ins/` (HTTP) | 5 |
| K3 | **data.gov.ro** (CKAN) | ~1.800 dataset-uri (bugete, salarii, firme, achiziții) | api+bulk | JSON+XLSX/CSV | `data.gov.ro/api/3/action/` | 3/5 |

**Dataset-uri data.gov.ro relevante:** `situatii_financiare_{an}`, `achizitii-publice-{an}`,
`firme-{data}` (ONRC dump), `drepturi-salariale` (salarii sector public), `buget*` (bugete),
`informatii_fiscale` (ANAF lunar). Orgs cheie: `mfp`, `agentia-nationala-de-administrare-fiscala`, ADR.

---

## L. TIER 3 — SERVICII DECONCENTRATE (~900–1.350 unități)

Coordonate de **Prefect** (`{xx}.prefectura.mai.gov.ro`), prezente în 41 județe + București = **42 unități**.
Connector **templated**: tip serviciu × județ, generat din `sources.yaml` (NU scris manual). *Fază 5.*

| Domeniu | Servicii județene |
|---|---|
| Sănătate/social | **DSP**, **CAS**, **CJP**, **AJPIS** |
| Muncă | **AJOFM**, **ITM** |
| Educație/cultură/sport | **ISJ**, **DJC**, **DJST** |
| Agricultură | **DAJ**, **DSVSA**, **APIA**, **OJFIR**, **ANIF** |
| Mediu | **APM**, **GNM**, **Garda Forestieră**, **SGA** (Apele Române) |
| Finanțe | **DGRFP/AJFP**, **DRV** (regional) |
| Registre/cadastru | **OCPI**, **ORC** (ONRC teritorial) |
| Ordine/siguranță | **IPJ**, **IJJ**, **ISU** |
| Consumator | **CJPC/OPC** |
| Statistică | **DJS** (regional) |

> ~26–32 tipuri × 42; unele sunt **regionale** (DGRFP, DRV, CRPC) → real ~900–1.100.

---

## M. AXA LOCALĂ (Consilii Județene — tier SEPARAT)

⚠️ **NU sunt servicii deconcentrate ale statului central** — sunt în subordinea Consiliului
Județean (autonomie locală, ales). Modelate ca `tier: local_autonomy`. Confuzia cu Tier 3 e
cea mai frecventă eroare de modelare.

| Instituție | Date |
|---|---|
| **DGASPC** (asistență socială/protecția copilului) | per județ, sub CJ |
| **DJEP** (evidența persoanelor) | per județ, sub CJ |
| Spitale județene, drumuri/poduri județene | sub CJ |

---

## Rezumat: ce e gratis vs plătit vs efort

**Gratis & programatic:** ANAF API (F1), data.gov.ro CKAN+dump-uri (H1, F2, I1, K3),
BNR XML (K1), INS Tempo (K2), legislatie SOAP (J1).

**Gratis dar efort de inginerie:** declarații ANI (headless + OCR, E2/E3), board-uri SOE
(crawl Art. 51 inegal, G4), Senat/Camera (scrape, A1/A2).

**Plătit (sau singura cale realistă):** acționariat cu % (H5/H6), documente ONRC oficiale (H3).

**Restricționat legal:** UBO (H4), Monitorul Oficial PDF (J2).

---

*Înapoi la:* [`00-MASTERPLAN.md`](00-MASTERPLAN.md) · [`01-ARCHITECTURE.md`](01-ARCHITECTURE.md) · [`02-DATA-MODEL.md`](02-DATA-MODEL.md) · [`04-LEGAL-GDPR.md`](04-LEGAL-GDPR.md)
