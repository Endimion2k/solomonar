# connectors — un modul per familie de surse

Fiecare connector implementează aceeași interfață și e configurat din `config/sources.yaml`.

```python
class Connector(Protocol):
    source_id: str
    def fetch(self) -> list[BronzeArtifact]: ...      # → data/raw/ (cache, hash)
    def parse(self, artifacts) -> list[BaseModel]: ... # → staging (silver)
```

Arhetipuri (vezi `docs/01-ARCHITECTURE.md`): `api` · `bulk` · `scrape` · `headless`.

| Folder | Surse | Fază |
|---|---|---|
| `parlament/` | cdep (portare), senat | 0, 1 |
| `ani/` | declaratii.integritate.eu (avere/interese) | 2 |
| `companii/` | amepip, onrc, bvb, boards, ownership | 3 |
| `fiscal/` | anaf (API CUI), mf-bilanturi, mf-lookup | 3 |
| `achizitii/` | sicap (XLSX bulk), e-licitatie (JSON) | 4 |
| `opendata/` | datagov (CKAN), legislatie (SOAP), bnr, ins | 3, 5 |
| `institutie/` | connector GENERIC (ministere, agenții, deconcentrate, local) | 5 |

> `institutie/generic` + template-urile (`deconcentrat_template`, `local_template`) acoperă
> sutele de instituții fără cod nou per instituție — config-driven din `sources.yaml`.
