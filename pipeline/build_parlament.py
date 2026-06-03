"""Build LIVE parlament — scrape cdep.ro (listă + profile) → Person + HOLDS_POSITION → data/v1.

Rulează de pe o mașină din RO (cdep.ro geo-blochează cloud). Throttle 1/s (politicos).
Acum, CU birth_date din profile, omonimii se separă corect (vs lista-only care contopea 8).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from connectors.institutie.generic import org_id
from connectors.parlament.cdep import PROFILE_URL, CdepConnector, parse_profile, to_person
from romega_core.io import export_collection
from romega_core.models import Edge, EdgeType
from romega_core.provenance import SourceRef
from romega_core.resolve import PersonRegistry

DEFAULT_OUT = Path(__file__).resolve().parents[1] / "data" / "v1"


def build_parlament_live(
    output_dir: str | Path = DEFAULT_OUT,
    leg: int = 2024,
    cam: int = 2,
    limit: int | None = None,
    version: str = "0.1.0",
) -> dict:
    out = Path(output_dir)
    (out / "parlament").mkdir(parents=True, exist_ok=True)

    conn = CdepConnector(leg=leg, cam=cam)
    deps = conn.list_deputies()
    if limit:
        deps = deps[:limit]

    reg = PersonRegistry()
    persons, deputati, edges = [], [], []
    errors = 0
    for i, d in enumerate(deps, 1):
        url = PROFILE_URL.format(idm=d["idm"], cam=cam, leg=leg)
        try:
            content, _ = conn.client.fetch(url, "cdep", ext=".html")
            dep = parse_profile(content, d["idm"], leg=leg, url=url)
        except Exception:
            errors += 1
            continue
        ref = SourceRef(source_id="cdep", source_url=url, fetched_at=datetime.now(timezone.utc))
        p = to_person(dep, reg, source=ref)
        persons.append(p)
        deputati.append(dep)
        edges.append(
            Edge(
                src=p.romega_id,
                dst=org_id("cdep"),
                type=EdgeType.HOLDS_POSITION,
                props={"role": "deputat", "legislatura": leg},
                sources=[ref],
            )
        )

    export_collection(out / "parlament" / "deputati.json", deputati, source_url="cdep.ro", version=version)
    export_collection(out / "parlament" / "persoane.json", persons, source_url="cdep.ro", version=version)
    (out / "parlament" / "edges.json").write_text(
        json.dumps([e.model_dump(mode="json") for e in edges], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "deputati": len(deputati),
        "persoane_unice": len(reg),
        "edges": len(edges),
        "errors": errors,
    }
    (out / "parlament" / "_status.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


if __name__ == "__main__":
    print(build_parlament_live())
