"""Descarcă (arhivează în bronze) documentele PLx ale comisiilor — din plx.json.

Pas 2 după harvest_comisii (indexul). Descarcă toate URL-urile de documente (em/pl/csm/cl/gv/
avize/rapoarte) în cache-ul bronze, ca să fie arhivate + disponibile. Reluabil (cache-ul sare
peste cele deja descărcate). Publică un mic raport în comisii/documente_status.json.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from romega_core.bronze import BronzeStore  # noqa: E402
from romega_core.http import Client  # noqa: E402

V = os.path.join(ROOT, "data/v1/comisii")


def main() -> dict:
    bronze = BronzeStore(os.path.join(ROOT, "data", "raw"))
    client = Client(bronze=bronze, throttle_seconds=0.25, timeout=20)
    plx = json.load(open(os.path.join(V, "plx.json"), encoding="utf-8"))["plx"]
    urls = sorted({d["url"] for p in plx for d in p["documente"]})
    todo = [u for u in urls if not bronze.has_url(u)]
    print(f"documente totale={len(urls)} | deja in cache={len(urls) - len(todo)} | de descarcat={len(todo)}",
          flush=True)

    ok = fail = 0
    for i in range(0, len(todo), 200):
        chunk = todo[i:i + 200]
        fetched = client.fetch_many([(u, "co_doc", ".pdf") for u in chunk], workers=8)
        ok += sum(1 for v in fetched.values() if v)
        fail += sum(1 for v in fetched.values() if not v)
        print(f"   descărcate {min(i + 200, len(todo))}/{len(todo)} | ok={ok} fail={fail} "
              f"cache={bronze.count()}", flush=True)

    in_cache = sum(1 for u in urls if bronze.has_url(u))
    json.dump({"generated_at": datetime.now(timezone.utc).isoformat(),
               "total_documente": len(urls), "arhivate_in_cache": in_cache,
               "esuate": len(urls) - in_cache},
              open(os.path.join(V, "documente_status.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"GATA: {in_cache}/{len(urls)} documente arhivate in bronze | cache={bronze.count()}", flush=True)
    return {"arhivate": in_cache, "total": len(urls)}


if __name__ == "__main__":
    main()
