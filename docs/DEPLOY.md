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
```bash
.venv/Scripts/python -m pipeline.run --build              # data/v1 din config (offline)
# build cu îmbogățire live (ANAF) pentru companii:
.venv/Scripts/python -c "import sys;sys.path.insert(0,'.');from pipeline.build import build_all;build_all(enrich_live=True)"
```
