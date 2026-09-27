# DEPLOY — publicare API static + runner

## GitHub Pages (API static + client)
SOLOMONAR servește `data/v1/*.json` și `web/` ca site static (filozofia cdep-api-poc).

1. **Repo public sau GitHub Pro** — Pages pe repo privat necesită plan plătit. Pentru un
   proiect de transparență, recomandarea e **public** (datele sunt publice oricum).
2. Settings → Pages → Source: `Deploy from a branch` → `main` / root.
3. `.nojekyll` (prezent) dezactivează procesarea Jekyll (servește fișierele ca atare).
4. URL-uri rezultate:
   - API: `https://endimion2k.github.io/solomonar/data/v1/status.json`
   - Organizații: `.../data/v1/organizatii/_index.json`
   - Client: `https://endimion2k.github.io/solomonar/web/`
5. În `web/index.html`, `DATA` e setat la `../data/v1` (corect când Pages servește din root).

## Client Streamlit — local + Streamlit Community Cloud

Aplicația „SOLOMONAR Insights" (18 pagini) e auto-conținută (bootstrap de `sys.path` în fiecare
pagină → nu mai cere `PYTHONPATH`).

**Local:**
```bash
.venv/Scripts/python -m streamlit run web/app/Overview.py
```

**Streamlit Community Cloud (URL public, gratuit):**
1. share.streamlit.io → New app → conectează repo-ul `Endimion2k/solomonar`.
2. **Main file path:** `web/app/Overview.py`
3. **Requirements:** `web/requirements.txt` (Advanced settings → sau redenumește în root dacă cere).
4. (Opțional) ca să citească datele live de pe Pages în loc de cele din repo, setează secret/env
   `SOLOMONAR_DATA = https://endimion2k.github.io/solomonar/data/v1`.
5. Tema dark e în `.streamlit/config.toml` (aplicată automat).

## Runner self-hosted (scraping programat)
`cdep.ro` / `senat.ro` geo-blochează IP-urile de cloud → scraping-ul programat rulează pe un
runner self-hosted în România (PC Windows, ca la cdep-api-poc).

1. Repo → Settings → Actions → Runners → New self-hosted runner (Windows), instalează + rulează.
2. Etichetează-l `romania` (workflow-urile cer `runs-on: [self-hosted, romania]`).
3. Workflow-urile (`.github/workflows/source.yml` + `schedule.yml`) rulează connectoarele pe
   cadența din `config/sources.yaml` (zilnic/săptămânal/lunar) → commit `data/v1/`.

> Notă: multe surse (ANAF API, data.gov.ro, BNR, INS) merg din orice locație din RO — au fost
> validate live de pe mașina de dezvoltare. Runner-ul e necesar pentru volum + geo-block parlament.

## Build local
> ⚠️ `pipeline.run --build` / `build_all()` sunt **bootstrap** (config + seed de 7 companii), nu
> refresh: pe `data/v1` existent ar rescrie `companii/_index.json` (1.256 companii îmbogățite → 7).
> De aceea refuză să suprascrie fișiere existente; rulează-le doar pe un director gol.
```bash
.venv/Scripts/python -m pipeline.run --build --out _local/bootstrap   # bootstrap offline într-un dir gol
# înainte de ORICE commit în data/v1 (gardă PII — Legea 176/2010 + GDPR):
.venv/Scripts/python -m pipeline.scrub_pii --check     # exit 1 = PII găsit → rulează fără --check ca să mascheze
```

## Refresh date (local, mașină din România)
Ordinea pașilor e codificată în `pipeline/refresh.py` (41 de pași, 4 grupuri). Log-urile fiecărui pas:
`_local/refresh/<timestamp>/<pas>.log`.

| Grup | Ce face | Durată orientativă |
|---|---|---|
| `surse` | parlament, comisii, DNA, legislație, partide, bugete, BVB, catalog SICAP | 1-2 h |
| `mari` | achiziții directe (~22M rânduri, cu checkpoint), red-flags, ONRC, bilanțuri MF | câteva ore |
| `derivate` | gold → Splink → ANI → sancțiuni / guvernanță → grafuri → DuckDB → rețele → alerte → căutare | 30-60 min |
| `final` | `stats.json` + `status.json`, mascare PII, gărzi (0 PII, niciun fișier > 90 MiB, JSON valid) | minute |

```bash
.venv/Scripts/python -m pipeline.refresh --groups surse --continue-on-error
.venv/Scripts/python -m pipeline.refresh --groups mari
.venv/Scripts/python -m pipeline.refresh --groups derivate,final
.venv/Scripts/python -m pipeline.refresh --from gold      # reluare după un pas eșuat
```
Declarațiile de avere/interese (OCR, ~o zi de GPU) nu fac parte din refresh — se rulează separat
(`harvest_declaratii*`, apoi `harvest_reprocess`). Commit-ul de date se face doar dacă garda finală
(`scrub_pii --check`) iese 0.
