# solomonar_core — biblioteca comună

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
| `mcp_server` | **server MCP** (FastMCP) peste DuckDB gold — interogare conversațională | nou |

**Faza 0:** extrage `http`, `parse`, `io` din cdep-api-poc; implementează `models`, `resolve`, `provenance`.

---

## Server MCP — `solomonar_core.mcp_server`

Expune datele gold SOLOMONAR (DuckDB read-only) pentru orice client MCP
(Claude Desktop / Cursor / Continue). 10 tool-uri cu provenance pe fiecare răspuns:

| Tool | Ce întoarce |
|---|---|
| `search_persoana(nume, limit)` | persoane după nume + nivel de încredere a identității |
| `get_persoana(romega_id)` | fișa completă: declarații, companii cu rol, comisii, contracte |
| `search_companie_stat(nume/sector/cui/judet, doar_bvb, limit)` | companii de stat: bilanț, % stat, contracte SICAP |
| `top_firme_contracte(n, sector)` | top firme după valoarea contractelor de stat |
| `follow_the_money(doar_confirmate)` | conflicte auto-declarate (+ leaduri neverificate cu AVERTISMENT pe omonimi) |
| `persoane_cu_firme_contracte(min_lei)` | persoane ale căror firme au contracte ≥ prag |
| `party_subventii(cod)` | subvenții partide (AEP) + parlamentari + rapoarte RVC |
| `companii_cu_participatie_stat()` | companii BVB cu participație de stat |
| `comisie_membri(nume)` | componența unei comisii parlamentare |
| `stats_globale()` | dimensiunile dataset-ului + agregate-cheie |

### Decizii etice (codificate în docstring-uri și în `_provenance`)
- Legăturile persoană↔firmă sunt pe **NUME (fără CNP)** → un `candidat` poate fi
  **OMONIM**, NU o acuzație. Doar conflictele **auto-declarate** sunt defensabile.
- Referințele DNA (dacă apar) = **trimiteri în judecată, NU condamnări**.
- CNP-ul este **redactat** din întreg dataset-ul.

### Instalare (în .venv-ul proiectului)

```bash
.venv/Scripts/python.exe -m pip install -e packages/solomonar_core[mcp]
# instalează: mcp[cli], duckdb și înregistrează scriptul `solomonar-mcp-core`
```

### Rulare

```bash
solomonar-mcp-core                       # scriptul instalat
# sau, fără instalare:
.venv/Scripts/python.exe -m solomonar_core.mcp_server
```

Localizarea datelor se autodetectează (`data/gold/solomonar.duckdb`,
`data/v1/graf/*.json`). Override prin variabile de mediu:
`SOLOMONAR_DUCKDB=/cale/solomonar.duckdb` și `SOLOMONAR_DATA=/cale/data/v1`.

### Configurare în Claude Desktop

Editează `claude_desktop_config.json`
(Windows: `%APPDATA%\Claude\claude_desktop_config.json`,
macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`):

```jsonc
{
  "mcpServers": {
    "solomonar": {
      "command": "solomonar-mcp-core"
    }
  }
}
```

Dacă scriptul nu e pe `PATH`, indică explicit interpretorul din venv și modulul:

```jsonc
{
  "mcpServers": {
    "solomonar": {
      "command": "C:/Users/<user>/Downloads/python/altele/romega/.venv/Scripts/python.exe",
      "args": ["-m", "solomonar_core.mcp_server"],
      "env": {
        "SOLOMONAR_DUCKDB": "C:/Users/<user>/Downloads/python/altele/romega/data/gold/solomonar.duckdb",
        "SOLOMONAR_DATA": "C:/Users/<user>/Downloads/python/altele/romega/data/v1"
      }
    }
  }
}
```

Repornește Claude Desktop; uneltele `solomonar` apar în lista de tool-uri MCP.
