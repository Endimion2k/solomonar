"""Construiește feed-urile temporale publicate pentru ROMEGA (data/v1/).

Trei livrabile, servite prin GitHub Pages CDN:
  1. data/v1/feed.json        — JSON Feed 1.1 (https://jsonfeed.org/version/1.1),
                                cele mai recente ~60 comunicate DNA
  2. data/v1/feed.xml         — Atom 1.0 valid, aceleași comunicate
  3. data/v1/alerte.feed.json — JSON Feed 1.1 cu cele 12 conflicte confirmate
                                (severitate "mare" / tip "conflict_confirmat")

Sursa flux temporal: data/v1/audit/dna.json (comunicate DNA). Ordinea cronologică
e dată de `id` (id mai mare = mai recent — corespunde ordinii de publicare dna.ro).
`data` ("11 iunie 2026") se derivă în ISO 8601 când se poate.

Idee pentru index.html (NU se modifică aici — doar notă):
  <link rel="alternate" type="application/atom+xml" title="ROMEGA — comunicate DNA"
        href="./data/v1/feed.xml">
  <link rel="alternate" type="application/json" title="ROMEGA — comunicate DNA"
        href="./data/v1/feed.json">
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from xml.dom import minidom
from xml.sax.saxutils import escape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V = os.path.join(ROOT, "data/v1")

# Baza canonică a site-ului publicat (GitHub Pages).
SITE = "https://endimion2k.github.io/romega"
FEED_JSON_URL = f"{SITE}/data/v1/feed.json"
FEED_ATOM_URL = f"{SITE}/data/v1/feed.xml"
ALERTE_FEED_URL = f"{SITE}/data/v1/alerte.feed.json"
ALERTE_HTML_URL = f"{SITE}/web/#alerte"

N_DNA = 60  # câte comunicate DNA recente intră în feed

# Luni românești -> număr (acoperă și forme cu/ fără diacritice).
_LUNI = {
    "ianuarie": 1, "februarie": 2, "martie": 3, "aprilie": 4, "mai": 5,
    "iunie": 6, "iulie": 7, "august": 8, "septembrie": 9, "octombrie": 10,
    "noiembrie": 11, "decembrie": 12,
}
_DATE_RE = re.compile(r"(\d{1,2})\s+([a-zăâîșț]+)\s+(\d{4})", re.IGNORECASE)


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_data(s: str | None):
    """'11 iunie 2026' -> datetime(UTC, 12:00). Întoarce None dacă nu se poate parsa."""
    if not s:
        return None
    m = _DATE_RE.search(s.strip())
    if not m:
        return None
    day, mon, year = int(m.group(1)), m.group(2).lower(), int(m.group(3))
    month = _LUNI.get(mon)
    if not month:
        return None
    try:
        # Comunicatele nu au oră — fixăm 12:00 UTC ca să fie stabil/deterministic.
        return datetime(year, month, day, 12, 0, 0, tzinfo=timezone.utc)
    except ValueError:
        return None


def _clean_titlu(titlu: str) -> str:
    """Curăță titlul comunicatului (DNA pune prefix 'Nr. X COMUNICAT ...')."""
    t = (titlu or "").strip()
    t = re.sub(r"\s+", " ", t)
    # taie prefixul redundant "Nr. 386/I-36 COMUNICAT"
    t = re.sub(r"^Nr\.?\s*[\w/\-]+\s+COMUNICAT\s*", "", t, flags=re.IGNORECASE)
    return t.strip() or "Comunicat DNA"


def _short_title(titlu: str, nr: str | None, limit: int = 120) -> str:
    t = _clean_titlu(titlu)
    if len(t) > limit:
        t = t[: limit - 1].rstrip() + "…"
    if nr:
        return f"Nr. {nr} — {t}"
    return t


def _content_text(c: dict) -> str:
    """Text scurt: rezumat titlu + numele extrase din comunicat."""
    base = _clean_titlu(c.get("titlu", ""))
    if len(base) > 280:
        base = base[:279].rstrip() + "…"
    nume = [n for n in (c.get("nume_extrase") or []) if n and n.strip()]
    if nume:
        return f"{base}\n\nNume extrase: " + ", ".join(nume)
    return base


# --------------------------------------------------------------------------- #
# DNA — JSON Feed + Atom
# --------------------------------------------------------------------------- #
def _recent_dna(n: int = N_DNA) -> list[dict]:
    rows = _load(os.path.join(V, "audit", "dna.json")).get("data", [])
    rows = [r for r in rows if r.get("id") is not None]
    rows.sort(key=lambda r: r["id"], reverse=True)
    return rows[:n]


def build_dna_jsonfeed(items: list[dict]) -> dict:
    out_items = []
    for c in items:
        cid = c["id"]
        dt = _parse_data(c.get("data"))
        item = {
            "id": str(cid),
            "url": c.get("url") or f"https://www.dna.ro/comunicat.xhtml?id={cid}",
            "title": _short_title(c.get("titlu", ""), c.get("nr")),
            "content_text": _content_text(c),
        }
        if dt:
            item["date_published"] = dt.isoformat()
        tags = [n for n in (c.get("nume_extrase") or []) if n and n.strip()]
        if tags:
            item["tags"] = tags[:8]
        out_items.append(item)

    return {
        "version": "https://jsonfeed.org/version/1.1",
        "title": "ROMEGA — comunicate DNA",
        "home_page_url": SITE,
        "feed_url": FEED_JSON_URL,
        "description": (
            "Cele mai recente comunicate ale Direcției Naționale Anticorupție, "
            "agregate de ROMEGA. Text neoficial, destinat mass-media."
        ),
        "language": "ro",
        "authors": [{"name": "ROMEGA", "url": SITE}],
        "items": out_items,
    }


def build_dna_atom(items: list[dict]) -> str:
    dts = [d for d in (_parse_data(c.get("data")) for c in items) if d]
    feed_updated = (max(dts) if dts else datetime.now(timezone.utc)).isoformat()

    parts = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<feed xmlns="http://www.w3.org/2005/Atom" xml:lang="ro">',
        "  <title>ROMEGA — comunicate DNA</title>",
        "  <subtitle>Cele mai recente comunicate ale Direcției Naționale "
        "Anticorupție, agregate de ROMEGA.</subtitle>",
        f'  <link href="{escape(SITE)}"/>',
        f'  <link rel="self" type="application/atom+xml" href="{escape(FEED_ATOM_URL)}"/>',
        f"  <id>{escape(FEED_ATOM_URL)}</id>",
        f"  <updated>{feed_updated}</updated>",
        "  <author><name>ROMEGA</name></author>",
    ]

    for c in items:
        cid = c["id"]
        url = c.get("url") or f"https://www.dna.ro/comunicat.xhtml?id={cid}"
        dt = _parse_data(c.get("data"))
        updated = (dt or datetime.now(timezone.utc)).isoformat()
        # id Atom: URN stabil bazat pe id-ul comunicatului
        entry_id = f"urn:romega:dna:{cid}"
        parts += [
            "  <entry>",
            f"    <title>{escape(_short_title(c.get('titlu', ''), c.get('nr')))}</title>",
            f'    <link href="{escape(url)}"/>',
            f"    <id>{escape(entry_id)}</id>",
            f"    <updated>{updated}</updated>",
            f"    <summary>{escape(_content_text(c))}</summary>",
            "  </entry>",
        ]
    parts.append("</feed>")
    return "\n".join(parts)


# --------------------------------------------------------------------------- #
# ALERTE — JSON Feed (cele 12 conflicte confirmate)
# --------------------------------------------------------------------------- #
def build_alerte_jsonfeed() -> dict:
    a = _load(os.path.join(V, "alerte.json"))
    generat = a.get("generat")
    dt_gen = None
    if generat:
        try:
            dt_gen = datetime.fromisoformat(generat).replace(tzinfo=timezone.utc)
        except ValueError:
            dt_gen = None
    pub = (dt_gen or datetime.now(timezone.utc)).isoformat()

    confirmate = [
        x for x in a.get("alerte", [])
        if x.get("tip") == "conflict_confirmat" and x.get("severitate") == "mare"
    ]

    out_items = []
    for i, x in enumerate(confirmate):
        det = x.get("detalii") or {}
        firme = det.get("firme") or []
        firme_txt = "; ".join(
            f"{f.get('nume')} (CUI {f.get('cui')}, {int(f.get('total_ron') or 0):,} RON)".replace(",", ".")
            for f in firme
        )
        total = det.get("total_contracte_ron")
        lines = [x.get("titlu", "")]
        if firme_txt:
            lines.append(f"Firme: {firme_txt}")
        if total:
            lines.append(f"Total contracte: {int(total):,} RON".replace(",", "."))
        if x.get("provenance"):
            lines.append(f"Sursă: {x['provenance']}")
        # id stabil: romega_id dacă există, altfel index
        rid = det.get("romega_id") or f"idx{i}"
        out_items.append({
            "id": f"romega:alerta:conflict_confirmat:{rid}",
            "url": ALERTE_HTML_URL,
            "title": x.get("titlu", "Conflict confirmat"),
            "content_text": "\n".join(lines),
            "date_published": pub,
            "tags": ["conflict_confirmat", "severitate:mare"],
            "_meta": {
                "entitate": x.get("entitate"),
                "este_parlamentar": det.get("este_parlamentar"),
                "total_contracte_ron": total,
                "scor": x.get("scor"),
            },
        })

    return {
        "version": "https://jsonfeed.org/version/1.1",
        "title": "ROMEGA — conflicte de interese confirmate",
        "home_page_url": SITE,
        "feed_url": ALERTE_FEED_URL,
        "description": (
            "Conflicte de interese documentate (severitate mare): persoane "
            "care au în propria declarație de interese firme cu contracte de stat. "
            + (a.get("disclaimer") or "")
        ).strip(),
        "language": "ro",
        "authors": [{"name": "ROMEGA", "url": SITE}],
        "items": out_items,
    }


# --------------------------------------------------------------------------- #
def main() -> dict:
    dna = _recent_dna(N_DNA)

    feed_json = build_dna_jsonfeed(dna)
    atom_xml = build_dna_atom(dna)
    alerte_json = build_alerte_jsonfeed()

    # Validare în memorie înainte de scriere.
    json.loads(json.dumps(feed_json, ensure_ascii=False))          # JSON valid
    json.loads(json.dumps(alerte_json, ensure_ascii=False))        # JSON valid
    minidom.parseString(atom_xml.encode("utf-8"))                  # XML well-formed

    p_json = os.path.join(V, "feed.json")
    p_xml = os.path.join(V, "feed.xml")
    p_alerte = os.path.join(V, "alerte.feed.json")

    with open(p_json, "w", encoding="utf-8") as f:
        json.dump(feed_json, f, ensure_ascii=False, indent=2)
    with open(p_xml, "w", encoding="utf-8") as f:
        f.write(atom_xml)
        f.write("\n")
    with open(p_alerte, "w", encoding="utf-8") as f:
        json.dump(alerte_json, f, ensure_ascii=False, indent=2)

    res = {
        "feed.json": {"items": len(feed_json["items"]), "kb": os.path.getsize(p_json) // 1024},
        "feed.xml": {"entries": len(dna), "kb": os.path.getsize(p_xml) // 1024},
        "alerte.feed.json": {"items": len(alerte_json["items"]), "kb": os.path.getsize(p_alerte) // 1024},
    }
    print(f"PUBLICAT feed.json: {res['feed.json']['items']} comunicate DNA | {res['feed.json']['kb']} KB")
    print(f"PUBLICAT feed.xml (Atom 1.0): {res['feed.xml']['entries']} entries | {res['feed.xml']['kb']} KB")
    print(f"PUBLICAT alerte.feed.json: {res['alerte.feed.json']['items']} conflicte confirmate | "
          f"{res['alerte.feed.json']['kb']} KB")
    return res


if __name__ == "__main__":
    main()
