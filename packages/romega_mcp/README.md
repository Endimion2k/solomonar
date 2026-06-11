# romega-mcp — server MCP ROMEGA

Expune datele ROMEGA (`data/v1/*.json`) ca **Model Context Protocol** — orice agent compatibil
(Claude Desktop / Cursor / Continue) le poate interoga conversațional.

## Instalare + rulare

```bash
pip install -e packages/romega_mcp
romega-mcp          # server stdio
# sau:  ROMEGA_DATA=/cale/la/data/v1 python -m romega_mcp.server
```

## Config Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "romega": {
      "command": "romega-mcp",
      "env": { "ROMEGA_DATA": "C:/Users/Maia/Downloads/python/altele/romega/data/v1" }
    }
  }
}
```

## 11 tool-uri

`stats`, `search_persoana`, `get_persoana`, `search_companie`, `follow_the_money`,
`top_contracte_firme`, `participatii_stat`, `subventii_partide`, `search_dna`,
`comisie_senat`, `analytics_view`.

Exemplu de întrebare după configurare: *„Ce firme conduse de oameni care declară avere au câștigat
contracte de stat?"* → Claude apelează `follow_the_money()` și răspunde cu cazurile confirmate.

⚠️ Legăturile persoană↔firmă sunt pe nume (fără CNP) — „candidat" poate fi omonim; doar „confirmat"
(auto-declarat) e defensabil. Comunicatele DNA = trimiteri în judecată, nu condamnări.
