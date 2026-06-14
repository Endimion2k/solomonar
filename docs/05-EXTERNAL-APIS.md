# 05 — API-uri și surse externe: ce există, ce e ușor, ce nu

> Cercetare (2026-06-10): am căutat surse gata-făcute (API/open-data) care ar înlocui scraping-ul.
> **Concluzia centrală: pentru datele grele (declarații) NU există scurtătură — scraping-ul SOLOMONAR
> e validat ca necesar.** Câteva surse periferice sunt mai ușoare, dar marginale.

## Verdict pe categorii

| Categorie | Sursă „ușoară"? | Verdict |
|-----------|-----------------|---------|
| **Declarații avere/interese** | ❌ NU | 0 dataseturi pe data.gov.ro · **ANI central nu mai e public din 2025** (840k depuse, primul an nepublic) · instituțiile postează pe site propriu (L.176/2010) → **scraping per-instituție = singura cale.** Abordarea SOLOMONAR confirmată. |
| **Achiziții publice** | ⚠️ parțial mort | **opentender.eu / OCDS RO = DECOMMISSIONED** (OCP publication 404; pub activă=date UE, nu RO). Rămâne **connector-ul SICAP** (avem 29.921) + e-licitatie.ro (endpoint-uri notice) + data.gov.ro (156 dataseturi per-instituție XLS). |
| **Acționariat %** | ⚠️ marginal | data.gov.ro „Acțiuni deținute de statul român" = doar **portofoliul Min. Economiei/Energiei** (~30 companii, .xls vechi ~2017). Fragmentat + vechi. SOE-urile sunt majoritar-stat prin definiție → valoare mică. Pt. % exact: AMEPIP. |
| **Companii (identitate)** | 🟡 da, dar avem | **ANAF webservice** (`webservicesp.anaf.ro`, gratis: CUI→nume/status/TVA/adresă) — avem deja majoritatea. **OpenCorporates** (3.092.423 firme RO + API) DAR **0 officers** pt. RO → nu adaugă administratori (îi avem din ONRC). |
| **Bilanțuri financiare** | ✅ deja integrat | MF/ANAF situații financiare (data.gov.ro) — **1.153 SOE + trend 2020-23**, gata. |
| **Bugete / cheltuieli** | 🟡 categorie nouă | data.gov.ro: 184 buget + 221 contracte + 73 subvenții + 21 cheltuieli — per-instituție XLS (fragmentat, NU API unitar). Real, dar nu „ușor". |
| **Reprezentanți legali** | ✅ deja | ONRC OD_REPREZENTANTI_LEGALI (data.gov.ro) — 1.250 SOE, gata. |

## Surse de luat în calcul (dacă se extinde scopul)
- **e-licitatie.ro/pub/notices/** — endpoint-uri quasi-API pt. anunțuri SICAP/SEAP (extindere contracte).
- **TED EU** (ted.europa.eu) — licitații UE; are API dar robot-gated.
- **OCCRP Aleph / OpenCorporates API** — pt. cross-border / due-diligence (cheie public-benefit gratis).
- **AMEPIP** — registru SOE + guvernanță (acționariat, board-uri Art.51).

## Ce NU s-a confirmat
- Niciun agregator terț (averi.ro / banuldepublic) cu **API de declarații parsate** — ar fi scurtat OCR-ul, dar nu există accesibil.

**Implicație practică:** SOLOMONAR nu ratează niciun shortcut major. Efortul de scraping (OCR per-instituție,
postback ASP.NET, FileBird, bulk streaming) e justificat — datele de transparență din RO sunt în mare
parte „în sălbăticie", nu în API-uri.

## Acționariat firme NELISTATE — cercetare gratuit (2026-06-14)

**Verdict: NU există sursă gratuită bulk + legală pentru asociați/acționari cu % la firme RO nelistate.**
Verificat exhaustiv (5 unghiuri + teste fetch directe):

| Sursă | Are %? | Gratis? | Concluzie |
|---|---|---|---|
| ONRC data.gov.ro (OD_*) | ❌ doar reps | DA | 6 fișiere, niciun OD_ASOCIATI |
| ONRC RECOM / BRIS / e-justice | ❌ | DA | declară OFICIAL că % NU e în accesul gratuit |
| Monitorul Oficial P.IV | ⚠️ fragmentar | DA | publică AGA/bilanțuri/dizolvări, NU sistematic structura % |
| ONRC InfoCert / Certificat constatator | ✅ | ❌ ~8-37 lei/firmă | singura cale oficială cu %, plătită per-firmă |
| RBR (beneficiari reali) | ⚠️ doar >25% | ❌ taxă+semnătură; **GRATIS pt. jurnaliști** | loophole legal: cerere formală ca proiect de interes public |
| infocui.ro | ⚠️ | tier free **600 CUI/lună** | legitim, lent — pt. firme-țintă (necesită cheie) |
| GLEIF Level 2 (Relationships) | ⚠️ parent-child | DA bulk | doar firme cu cod LEI (mari, ~acoperite de BVB) |
| Agregatori (termene/listafirme/risco/confidas) | ✅ | ❌ paywall/ToS | au % dar contra-cost; scraping = încalcă ToS |
| OpenCorporates RO | ❌ | tier | mort (2020, 0 officers RO) |

**Ce avem deja (gratis):** BVB pt. SOE listate (% exact, cele importante) + reprezentanți legali (administratori) pt. toate.
**Căi legitime limitate pt. țintit:** (1) RBR cu cerere de jurnalist (>25%); (2) infocui free 600/lună pt. firmele-cheie; (3) GLEIF pt. firme cu LEI. **Nu există soluție gratis-la-scară** — doar advocacy ca ONRC să publice asociații ca open-data.
