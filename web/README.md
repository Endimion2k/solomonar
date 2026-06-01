# web — client (succesorul cdep-client)

Frontend static (HTML/JS + i18n RO/EN) care consumă `data/v1/*.json`. Extinde clientul
cdep-client de la profiluri parlamentare la profiluri unificate + graf.

Pagini țintă:
- **Persoană** — funcții (cross-instituție), declarații de avere (timeline), membri CA, firme legate.
- **Instituție** — conducere, buget, achiziții acordate, SOE controlate.
- **Companie** — date fiscale, financiare, conducere (CA/directorat), acționariat, contracte câștigate.
- **Graf** — vizualizare relații (persoană↔firmă↔contract↔instituție).
- **Căutare** — Pagefind full-text peste toate entitățile.

Fiecare afirmație afișează **sursă + dată** (provenance). Corecții via GitHub issues.
