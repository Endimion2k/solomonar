# romega_core — biblioteca comună

Codul partajat de toate connectoarele și de pipeline. Extras și generalizat din `cdep-api-poc`.

| Modul | Responsabilitate | Sursă |
|---|---|---|
| `http` | client requests+truststore (SSL legacy), retry/backoff, rate-limit/host, cache bronze | port din cdep-api-poc |
| `parse` | parsel (CSS/XPath), encoding ISO-8859-2, parser XLSX/CSV/XML/SOAP | port + extins |
| `pdf` | extractor PDF: ramură text (2022+) + ramură OCR (pre-2022) | nou (Faza 2) |
| `headless` | driver Playwright pentru SPA-uri (ANI) | nou (Faza 2) |
| `models` | modele Pydantic v2 canonice — vezi `docs/02-DATA-MODEL.md` | nou |
| `resolve` | normalizare nume, blocking, matching, `romega_id` | nou (creierul) |
| `io` | exporter JSON versionat, Pagefind, feed Atom/JSON | port din cdep-api-poc |
| `provenance` | `SourceRef` + registru bronze | nou |

**Faza 0:** extrage `http`, `parse`, `io` din cdep-api-poc; implementează `models`, `resolve`, `provenance`.
