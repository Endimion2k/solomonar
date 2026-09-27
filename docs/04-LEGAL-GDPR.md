# 04 — LEGAL & GDPR

> SOLOMONAR agregă **date publice** despre **oficiali în calitatea lor oficială** și despre
> **entități juridice**. Acest document fixează baza legală, redactările obligatorii și
> regulile de conformare per sursă. Nu e consultanță juridică — e politica de proiect.

---

## 1. Baza legală (de ce e legal)

| Temei | Ce permite |
|---|---|
| **Legea 544/2001** — liberul acces la informații de interes public | accesul la informații despre activitatea instituțiilor publice |
| **Legea 176/2010** — integritatea în funcții publice | declarațiile de avere/interese sunt **publice prin lege**; ANI le publică online |
| **OUG 109/2011** (mod. **Legea 187/2023**) — guvernanța corporativă | transparența SOE: CA/directorat, CV, remunerație, rapoarte (Art. 51) |
| **OGL-ROU / CC BY 4.0** (data.gov.ro) | reutilizarea datelor deschise, cu atribuire |
| **Excepția GDPR pentru demnitari** | datele despre oficiali în exercițiul funcției nu intră sub restricțiile standard |

---

## 2. Redactări OBLIGATORII (rămân redactate)

Legea 176/2010 **art. 6** impune anonimizarea la sursă a anumitor câmpuri din declarații.
SOLOMONAR **nu** le publică și **nu** le reconstruiește:

- ❌ **CNP** (cod numeric personal)
- ❌ **adresa completă** a imobilelor (păstrăm doar localitatea/județul)
- ❌ adresele instituțiilor care administrează active
- ❌ **semnătura**
- ❌ date despre minori

> **Gardă PII implementată** (`connectors/ani/redaction.py` + `pipeline/scrub_pii.py`):
> - ce se maschează: CNP valid (cifră de control + lună/zi/județ), telefon mobil (orice format uzual),
>   telefon fix doar lângă o etichetă personală („domiciliu”, „personal”) sau lipit de un mobil
>   (antet de CV) — numerele fixe ale instituțiilor sunt publice și rămân —, serie/număr CI
>   (inclusiv „CI XX - NNNNNN”; nu diplome/bancnote), IBAN RO valid, e-mail în câmpul `web`;
> - la sursă: harvesterele de declarații, CV-uri (`process_cv`/`_sections`, `cv_ocr`,
>   `harvest_cv_parlament`, `harvest_cv_senatori`), rapoarte RVC și ONRC maschează înainte de
>   trunchiere; harvesterele SICAP tratează ca persoană fizică DOAR un CNP valid (agregare pe nume
>   `pf:<NUME>`, `cui` null, `pf: true`); alți identificatori lungi rămân în `cui_nevalid`;
> - la publicare: `python -m pipeline.scrub_pii --check` scanează tot `data/v1` și iese cu cod 1
>   la PII sau la un fișier care nu poate fi verificat → **pas obligatoriu înainte de orice commit
>   de date**; fără `--check` maschează in-place, păstrând formatarea;
> - test de regresie: `pipeline/tests/test_scrub_pii.py::test_published_data_has_no_pii`.
>
> Limite cunoscute: adresele complete din text liber (ex. donatori în rapoartele RVC) nu sunt încă
> detectate automat; URL-urile către documentele-sursă nu se modifică (sunt doar raportate);
> istoricul git anterior curățării conține încă valorile (rescriere de istoric = decizie separată).

---

## 3. Principii GDPR aplicate

1. **Minimizare** — colectăm doar ce servește scopul de transparență publică. Fără date
   sensibile dincolo de mandatul public.
2. **Scop** — interes public legitim (transparență, anticorupție, jurnalism de date).
3. **Exactitate + provenance** — fiecare fapt are sursă + dată; corecții via GitHub issues.
4. **Persoane private** — rudele/asociații care apar în declarații/acționariat sunt date
   personale → publicăm doar ce e deja public la sursă, cu aceleași redactări.
5. **Dreptul la rectificare** — procedură publică de corecție (ca în `cdep-api-poc`).

---

## 4. Reguli per sursă (ToS / acces)

| Sursă | Regulă |
|---|---|
| ANI (declarații) | publice prin lege; **păstrăm redactările**; fără re-identificare |
| ONRC dump (data.gov.ro) | CC BY 4.0 — OK reutilizare cu atribuire |
| Agregatori comerciali (termene/risco) | ToS interzic de obicei **redistribuirea/republicarea în masă** a datelor brute → folosim pentru îmbogățire internă/țintit, nu republicăm dump-ul lor |
| UBO (beneficiari reali) | **restricționat** (Legea 86/2025: interes legitim + taxă + semnătură) → **în afara scopului automat** |
| ANAF API | date publice; respectăm rate-limit (1 req/s, 100 CUI/req) |
| cdep.ro / senat.ro | scraping politicos (rate-limit, user-agent, ore de noapte); doar date publice |
| Monitorul Oficial PDF | paywall → **nu** scrapăm; folosim `legislatie.just.ro` (gratis) |

---

## 5. Scraping etic (reguli de execuție)
- `robots.txt` respectat unde e aplicabil; rate-limit per host; user-agent identificabil.
- Fără bypass de autentificare, CAPTCHA sau ToS.
- Cache bronze → minimizează cererile repetate către surse.
- Rulări grele (ANI headless) programate în afara orelor de vârf.

---

## 6. Disclaimer de publicare
Ca în `cdep-api-poc`: datele sunt agregate din surse publice oficiale, în scop de transparență
și informare publică. Pot exista erori de sursă sau de parsare; corecțiile se fac prin issues.
Datele despre acționariat/avere reflectă declarații/înregistrări publice, nu constituie
acuzații.

---

*Înapoi la:* [`03-SOURCES.md`](03-SOURCES.md)
