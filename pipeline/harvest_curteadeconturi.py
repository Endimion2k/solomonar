"""Harness Curtea de Conturi — cheamă CurteaDeConturiConnector.fetch_audit_links() LIVE.

run.py nu exportă connectorii din connectors/audit, așa că acest mic harness importă direct
connectorul, îl rulează contra site-ului live (curteadeconturi.ro) cu cache bronze, și publică
rezultatul în data/v1/audit/curtea_de_conturi.json (plic meta + data, ca restul stratului v1).
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import urllib3  # noqa: E402

from connectors.audit.curteadeconturi import BASE, CurteaDeConturiConnector  # noqa: E402
from solomonar_core.bronze import BronzeStore  # noqa: E402
from solomonar_core.http import Client  # noqa: E402

urllib3.disable_warnings()

V = os.path.join(ROOT, "data/v1/audit")
OUT = os.path.join(V, "curtea_de_conturi.json")


def main() -> dict:
    os.makedirs(V, exist_ok=True)
    bronze = BronzeStore(os.path.join(ROOT, "data", "raw"))
    client = Client(bronze=bronze, throttle_seconds=0.5, timeout=30)
    conn = CurteaDeConturiConnector(client=client)

    error = None
    links: list[dict] = []
    try:
        links = conn.fetch_audit_links()
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"
        print(f"FETCH LIVE A ESUAT: {error}", flush=True)

    payload = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_id": conn.source_id,
            "source_url": BASE,
            "connector": "connectors/audit/curteadeconturi.py::CurteaDeConturiConnector.fetch_audit_links",
            "count": len(links),
            "fetch_error": error,
        },
        "data": links,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"PUBLICAT {os.path.relpath(OUT, ROOT)}: {len(links)} rapoarte de audit", flush=True)
    return {"count": len(links), "error": error}


if __name__ == "__main__":
    main()
