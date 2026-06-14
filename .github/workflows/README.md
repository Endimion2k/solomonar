# .github/workflows — CI (runner self-hosted, RO)

cdep.ro/senat.ro geo-blochează IP-urile de cloud → CI rulează pe runner self-hosted în România
(setup moștenit din cdep-api-poc).

Țintă:
- **`source.yml`** — workflow GENERIC parametrizat (`source_id`): rulează connector → pipeline
  (silver→gold) → export → commit + push. Apelat per sursă, pe cadența din `sources.yaml`.
- **`schedule.yml`** — cron-uri care lansează `source.yml` pe grupuri:
  - zilnic 04:00 UTC: parlament, feed-uri (ca în cdep-api-poc);
  - săptămânal: declarații ANI, board-uri SOE;
  - lunar: dump-uri ONRC/MF, XLSX SICAP, bugete.

Pași tipici: checkout → setup Python → `pip install -e .` → `python -m solomonar run --source $SOURCE`
→ commit `data/v1/` + `registry.sqlite`.
