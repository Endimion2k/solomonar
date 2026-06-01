# data/v1 — API static publicat (gold)

Output-ul build-ului: snapshot-uri JSON versionate, servite prin GitHub Pages CDN.
Acesta E API-ul public (filozofia cdep-api-poc, generalizată).

Structură țintă (se populează pe măsură ce avansează valurile):

```
data/v1/
├── persoane/            # Person (romega_id) — profil unificat cross-instituție
├── organizatii/         # Organization (instituții, versionate în timp)
├── companii/            # Company (CUI) — SOE, financiar, conducere, acționariat
├── parlament/           # deputați, senatori, voturi, proiecte (Faza 0-1)
├── declaratii/          # avere + interese (Faza 2)
├── achizitii/           # contracte (Faza 4)
├── graph/               # noduri/muchii export pentru vizualizare
├── feed.atom            # ultimele evenimente
├── feed.json
└── status.json          # prospețime date (machine-readable)
```

Fiecare entitate include `sources[]` (provenance: source_id + url + fetched_at + sha256).
