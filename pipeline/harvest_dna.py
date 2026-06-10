"""Ad-hoc harness — rulează DnaConnector.fetch_comunicate (live) și exportă în data/v1/audit/dna.json.

run.py NU exportă încă connectorii audit; acest harness îi cheamă metoda de fetch direct,
îmbogățește fiecare comunicat (titlu/data/nr/corp de pe pagina .xhtml) și scrie plicul JSON.

SSL: dna.ro merge din RO cu verify standard, dar — conform instrucțiunilor — forțăm
verify=False + urllib3.disable_warnings() ca să fim robuști la MITM/antivirus pe Windows.
"""

from __future__ import annotations

import json
import re
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import urllib3

urllib3.disable_warnings()
warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "packages" / "romega_core"))

from romega_core.bronze import BronzeStore  # noqa: E402
from romega_core.dates import parse_ro_date  # noqa: E402
from romega_core.http import Client  # noqa: E402
from romega_core.parse import selector  # noqa: E402

from connectors.audit.dna import BASE, DnaConnector  # noqa: E402

RE_RO_DATE = re.compile(r"(\d{1,2})\s+([A-Za-zăâîșşţț\.]+)\s+(\d{4})")


def _patch_no_verify(client: Client) -> None:
    """Forțează verify=False pe toate request-urile clientului (cerință harness)."""
    _orig_get = client.get

    def _get(url: str, **kwargs):
        kwargs.setdefault("verify", False)
        return _orig_get(url, **kwargs)

    client.get = _get  # type: ignore[method-assign]


def enrich(content: bytes, url: str) -> dict:
    """Din pagina comunicat.xhtml → {titlu, data, data_iso, nr, corp}."""
    sel = selector(content)
    res = sel.css("div.results")
    out: dict = {"url": url, "titlu": None, "data": None, "data_iso": None, "nr": None, "corp": None}
    if not res:
        return out
    res = res[0]
    indents = [
        " ".join(p.strip() for p in s.css("::text").getall() if p.strip())
        for s in res.css("span.indent")
    ]
    indents = [t for t in indents if t]
    tabs = [
        " ".join(p.strip() for p in s.css("::text").getall() if p.strip())
        for s in res.css("span.tab")
    ]
    tabs = [t for t in tabs if t]

    if indents:
        out["data"] = indents[0]
        m = RE_RO_DATE.search(indents[0])
        if m:
            d = parse_ro_date(m.group(1), m.group(2), m.group(3))
            if d:
                out["data_iso"] = d.isoformat()
    for s in indents[1:]:
        if s.lower().startswith("nr"):
            out["nr"] = s
            break
    if tabs:
        # primul paragraf = lede-ul descriptiv (semnalul real: nume/instituții)
        out["titlu"] = tabs[0]
        out["corp"] = "\n\n".join(tabs)
    return out


def main() -> int:
    bronze = BronzeStore(ROOT / "data" / "raw")
    client = Client(bronze=bronze, legacy_ssl=False)
    _patch_no_verify(client)

    conn = DnaConnector(client=client)
    try:
        coms = conn.fetch_comunicate()
    except Exception as e:  # pragma: no cover
        print(f"FETCH_LIST_FAILED: {type(e).__name__}: {e}", file=sys.stderr)
        return 2

    print(f"comunicate descoperite în listă: {len(coms)}", file=sys.stderr)

    records: list[dict] = []
    for c in coms:
        url = c["url"]
        try:
            content, _ = client.fetch(url, "dna", ext=".html")
            rec = enrich(content, url)
            rec["id"] = c["id"]
            records.append(rec)
            print(f"  id={c['id']:>6}  data={rec['data']!r}  titlu={(rec['titlu'] or '')[:70]!r}",
                  file=sys.stderr)
        except Exception as e:  # pragma: no cover
            print(f"  id={c['id']} ENRICH_FAILED: {type(e).__name__}: {e}", file=sys.stderr)
            records.append({"id": c["id"], "url": url, "titlu": None, "data": None,
                            "data_iso": None, "nr": None, "corp": None})

    # sort desc după id (cele mai noi primele)
    records.sort(key=lambda r: r["id"], reverse=True)

    out_path = ROOT / "data" / "v1" / "audit" / "dna.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_url": BASE + "/comunicate.xhtml",
            "source_id": "dna",
            "scraper_version": "harness-0.1",
            "count": len(records),
        },
        "data": records,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"EXPORTAT: {out_path}  ({len(records)} comunicate)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
