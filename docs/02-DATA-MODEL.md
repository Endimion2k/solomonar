# 02 — MODEL DE DATE: entități, rezoluție, graf

> Modelul canonic care unifică zeci de surse eterogene. Identifică ce e o „persoană", o
> „organizație", o „companie", cum le legăm (entity resolution) și cum modelăm relațiile (graf).

---

## 1. Entitățile canonice (core)

Toate au `romega_id` (ID intern stabil) + `sources[]` (provenance) + `created_at`/`updated_at`.

### Person — o persoană fizică
```yaml
Person:
  romega_id: str            # "p:" + ULID stabil
  full_name: str            # forma canonică
  aliases: [str]            # toate variantele văzute (NUME Prenume, cu/fără diacritice...)
  birth_date: date | null   # cheie puternică de dezambiguizare (nu CNP!)
  county: str | null
  # NU stocăm: CNP, adresă completă, semnătură (redactate legal)
  external_ids:             # crosswalk
    cdep_idm: [int]
    senat_guid: [str]
    ani_person_ref: [str]
  positions: [Position]     # funcții deținute (muchii HOLDS_POSITION/MEMBER_OF_BOARD)
  declarations: [ref]       # declarații de avere/interese
  sources: [SourceRef]
```

### Organization — instituție publică (non-companie)
```yaml
Organization:
  romega_id: str            # "o:" + ULID
  name: str
  short_name: str | null    # ANAF, ANI, DSP...
  type: enum                # parliament_chamber | government | ministry | agency |
                            # authority | deconcentrated | local_council_body | court | other
  tier: enum                # central | subordinated | deconcentrated | local_autonomy
  parent: romega_id | null  # SUBORDINATE_OF
  tutelary_authority: romega_id | null  # pentru SOE: autoritatea tutelară
  domain: str | null        # website oficial
  cif: str | null           # cod fiscal instituție (dacă există)
  valid_from: date | null   # ministerele se versionează în timp!
  valid_to: date | null
  sources: [SourceRef]
```

### Company — persoană juridică (firmă)
```yaml
Company:
  romega_id: str            # "c:" + ULID (intern); cheia naturală e CUI
  cui: int                  # cod unic de înregistrare (cheia naturală, din ANAF/ONRC)
  name: str
  reg_com: str | null       # nr. registrul comerțului (J.../F.../C...)
  caen: str | null          # cod CAEN principal
  status: enum              # active | inactive | radiata | insolventa
  vat_payer: bool | null
  is_soe: bool              # întreprindere publică? (din AMEPIP)
  legal_reps: [ref]         # reprezentanți legali (ONRC dump — gratis)
  shareholders: [OwnershipStake]  # asociați + % (agregator comercial — vezi T1)
  financials: [FinancialYear]     # bilanțuri (MF, per an)
  sources: [SourceRef]
```

### Position — o funcție deținută de o persoană (mandat)
```yaml
Position:
  person: romega_id
  org: romega_id | null     # pentru funcții publice
  company: romega_id | null # pentru CA/directorat la companii
  role: str                 # "deputat", "ministru", "secretar de stat", "membru CA", "director general"
  role_type: enum           # elected | appointed | board | management | civil_servant
  start_date: date | null
  end_date: date | null     # null = în exercițiu
  remuneration: money | null # unde e public (Art. 51 SOE)
  source_legislature: str | null
  sources: [SourceRef]
```

### Declaration — declarație de avere sau interese
```yaml
Declaration:
  romega_id: str
  person: romega_id
  org: romega_id | null     # instituția pentru care s-a depus
  type: enum                # avere | interese
  year: int
  filed_at: date | null
  pdf_url: str
  is_native_pdf: bool       # 2022+ text vs pre-2022 scanat (OCR)
  # AVERE (secțiuni din template-ul legal):
  real_estate: [...]        # imobile (localitate, NU adresă completă)
  vehicles: [...]
  financial_assets: [...]   # conturi, acțiuni, fonduri
  debts: [...]
  income: [...]
  gifts: [...]
  # INTERESE:
  shareholdings: [...]      # acțiuni/părți sociale → leagă la Company
  board_memberships: [...]  # → muchii MEMBER_OF_BOARD
  contracts: [...]
  sources: [SourceRef]
```

### Contract — achiziție publică (SICAP)
```yaml
Contract:
  romega_id: str
  contracting_authority: romega_id   # Organization
  supplier: romega_id                # Company (prin CUI)
  amount: money
  currency: str
  award_date: date
  cpv: str | null           # cod CPV obiect
  procedure_type: str | null
  title: str
  sources: [SourceRef]
```

### Tipuri auxiliare
```yaml
OwnershipStake: { holder: romega_id (Person|Company), company: romega_id, percent: float|null, role: enum(asociat|actionar) }
FinancialYear:  { company: romega_id, year: int, turnover, profit, employees, ... }
SourceRef:      { source_id: str, source_url: str, fetched_at: datetime, bronze_sha256: str }
Document:       { romega_id, kind, url, sha256, ocr: bool }
```

---

## 2. Entity Resolution (algoritmul)

Problema: „Popescu Ion" (cdep), „Ion POPESCU" (senat GUID), „POPESCU Ion" (declarație ANI la
Ministerul X), „Ion Popescu" (membru CA Hidroelectrica) — **aceeași persoană?** Fără CNP
(redactat), dezambiguizăm pe **nume normalizat + dată naștere + context**.

### Pași
1. **Normalizare** (`solomonar_core.resolve.normalize`)
   - elimină diacritice, lowercase, colapsează spații;
   - detectează ordinea NUME/Prenume (heuristici + dicționar de prenume RO);
   - scoate titluri (dr., ing., prof., av.);
   - produce o `name_key` canonică + păstrează forma originală ca `alias`.
2. **Blocking** — grupează candidați după chei ieftine ca să eviți O(n²):
   - bloc = `(name_key_soundex, birth_year)` sau `(first_initial+last_name, county)`.
3. **Matching** — scor ponderat pe candidații din același bloc:
   - nume (Jaro-Winkler pe `name_key`): pondere mare;
   - `birth_date` egal: foarte mare (aproape decisiv);
   - context (aceeași instituție/funcție/perioadă): mediu;
   - ID extern comun (cdep_idm, CUI ca membru CA): decisiv.
4. **Decizie**
   - scor ≥ prag_high → merge automat sub un `romega_id`;
   - prag_low ≤ scor < prag_high → **coadă de revizuire manuală** (homonimi);
   - scor < prag_low → entitate nouă.
5. **Persistare** (SQLite, commit-abil)
   - `person_registry(romega_id, canonical_name, birth_date, ...)`;
   - `person_alias(romega_id, alias, source_id)`;
   - `person_crosswalk(romega_id, system, external_id)` — ex. `(p:..., 'cdep', 12345)`.

> **De ce ANI (Faza 2) e ancora:** declarațiile dau funcție + instituție + an pentru fiecare
> persoană → context bogat care ridică drastic acuratețea matching-ului cross-sursă.

### Stabilitatea ID-urilor
`romega_id` se atribuie o singură dată și persistă în SQLite între rulări. Aliasurile se
adaugă, nu se rescriu. Așa, un link extern (ex. URL de profil persoană) rămâne valid la
nesfârșit — esențial pentru un API public.

---

## 3. Graful

### Noduri
`Person`, `Organization`, `Company`, `Document` — fiecare cu `romega_id`.

### Muchii (cu atribute)
| Muchie | De la → la | Atribute | Sursă |
|---|---|---|---|
| `HOLDS_POSITION` | Person → Organization | role, start, end | parlament, ministere, ANI |
| `MEMBER_OF_BOARD` | Person → Company | role (CA/directorat), start, end, remunerație | Art. 51, AMEPIP, BVB |
| `OWNS_SHARE` | Person/Company → Company | percent, role | agregator / declarații interese |
| `SUBSIDIARY_OF` | Company → Company | percent control | ONRC / agregator |
| `CONTROLS` | Organization → Company | rol (autoritate tutelară) | AMEPIP |
| `AWARDED_CONTRACT` | Organization → Company | amount, date, cpv | SICAP |
| `DECLARED` | Person → Document | type, year | ANI |
| `SUBORDINATE_OF` | Organization → Organization | tier | sources.yaml / organigrame |

### Stocare și interogare
Tabele `node(romega_id, type, props_json)` + `edge(src, dst, type, props_json)` în DuckDB.
Traversări prin **CTE recursive** (ex. „toate subsidiarele unei firme", „lanțul de control
de la stat la o firmă", „firme legate de un demnitar pe ≤2 hop-uri").

### Interogări-cheie pe care le activează graful
```sql
-- Firme care au câștigat contracte ȘI au în CA o persoană cu funcție publică
-- (semnal de conflict de interese)
WITH public_persons AS (
  SELECT DISTINCT src AS person FROM edge WHERE type='HOLDS_POSITION'
)
SELECT c.dst AS company, ct.amount
FROM edge c                                   -- MEMBER_OF_BOARD
JOIN public_persons pp ON pp.person = c.src
JOIN edge ct ON ct.dst = c.dst AND ct.type='AWARDED_CONTRACT'
WHERE c.type='MEMBER_OF_BOARD';
```

```sql
-- Lanțul de control stat → SOE → subsidiare (recursiv)
WITH RECURSIVE chain AS (
  SELECT src, dst, 1 AS depth FROM edge WHERE type='CONTROLS'
  UNION ALL
  SELECT e.src, e.dst, chain.depth+1
  FROM edge e JOIN chain ON e.src = chain.dst
  WHERE e.type='SUBSIDIARY_OF' AND chain.depth < 5
)
SELECT * FROM chain;
```

---

## 4. Versionarea în timp (temporal)
Instituțiile **se schimbă** (ministere fuzionează/se separă la fiecare cabinet — vezi
research: Digitalizare, Sport, Energie, Tineret sunt „articulațiile" instabile). De aceea:
- `Organization` are `valid_from`/`valid_to`;
- `Position` are `start_date`/`end_date`;
- nu suprascriem istoria — adăugăm versiuni.

Așa, o întrebare ca „cine era ministru al Energiei în martie 2024" are răspuns corect chiar
dacă ministerul s-a reorganizat între timp.

---

## 5. Maparea sursă → entitate (rezumat)
| Sursă | Alimentează |
|---|---|
| cdep.ro / senat.ro | Person (parlamentari), Organization (comisii), Position, Declaration (link) |
| ANI (integritate.eu) | Declaration (avere+interese), Person (ancoră de rezoluție) |
| AMEPIP | Company (is_soe), Organization (autoritate tutelară), `CONTROLS` |
| ANAF API | Company (status, CAEN, TVA) |
| ONRC dump (data.gov.ro) | Company, legal_reps |
| MF bilanțuri | Company.financials |
| Agregator (termene/risco) | OwnershipStake (asociați + %), `OWNS_SHARE`, `SUBSIDIARY_OF` |
| SICAP | Contract, `AWARDED_CONTRACT` |
| legislatie.just.ro | Documents (legi) ↔ bills |

---

*Următorul document:* [`03-SOURCES.md`](03-SOURCES.md) — catalogul complet de surse.
