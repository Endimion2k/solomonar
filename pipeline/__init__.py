"""SOLOMONAR pipeline — orchestrarea build-ului bronze → silver → gold → export.

- silver        : modele → tabele staging DuckDB
- gold.graph    : noduri + muchii în DuckDB (traversări recursive)
- gold.registry : PersonRegistry persistent în SQLite (romega_id stabil între rulări)
- export        : gold → data/v1/*.json
"""
