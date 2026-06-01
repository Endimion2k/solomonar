# pipeline — build bronze → silver → gold

Orchestrarea care transformă artefactele brute în JSON static publicabil.

```
bronze.py   # registru artefacte brute (sha256, timestamp, path) — data/raw/
silver.py   # brut → modele Pydantic → tabele staging DuckDB (cu provenance/rând)
gold/
  resolve.py  # entity resolution → registre SQLite (romega_id stabil, commit-abil)
  graph.py    # nodes + edges în DuckDB; traversări prin CTE recursive
  derive.py   # vederi derivate: delta avere, agregate contracte, semnale conflict
export.py   # gold → data/v1/*.json + Pagefind + feeds Atom/JSON
```

Vezi `docs/01-ARCHITECTURE.md` §3.3 și `docs/02-DATA-MODEL.md` §2 (algoritmul de resolution).

**Stabilitate ID:** `data/build/registry.sqlite` se comite (excepție în `.gitignore`) ca
`romega_id`-urile să fie stabile între rulări. DuckDB de build NU se comite (se regenerează).
