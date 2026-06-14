"""CV-uri parlamentari (deputați) de pe cdep.ro — pag=0 al profilului = Curriculum Vitae (Europass).

Umple gap-ul parlament-CV. deputati.json are cdep_idm + profile_url. Fetch ...&pag=0 → extrage
studii + experiență (parserul din process_cv). Output cv_parlament.json. Network cdep (paralel cu soe2).
"""

from __future__ import annotations

import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from solomonar_core.http import Client  # noqa: E402
from pipeline.process_cv import _sections  # noqa: E402

V = os.path.join(ROOT, "data/v1")
client = Client(throttle_seconds=0.15, timeout=15)


def _cv_url(profile_url: str) -> str:
    base = profile_url.split("#")[0]
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}pag=0&idl=1"


def _fetch_cv(dep):
    purl = dep.get("profile_url")
    if not purl:
        return None
    try:
        content, _ = client.fetch(_cv_url(purl), "cvp", ".html", use_cache=True)
        t = content.decode("utf-8", "ignore") if isinstance(content, bytes) else content
    except Exception:
        return None
    body = re.sub(r"[ \t]+", " ", re.sub(r"<[^>]+>", "\n", t))
    edu, exp = _sections(body)
    if not edu and not exp:
        return None
    return {"nume": dep.get("name", ""), "cdep_idm": dep.get("cdep_idm"),
            "legislatura": dep.get("legislatura"), "partid": dep.get("current_party"),
            "judet": dep.get("judet"), "studii": edu, "experienta": exp, "url": _cv_url(purl)}


def main() -> dict:
    d = json.load(open(os.path.join(V, "parlament/deputati.json"), encoding="utf-8"))
    deps = d.get("data") or d.get("deputati")
    deps = deps if isinstance(deps, list) else list(deps.values())
    print(f"CV pe {len(deps)} deputați...", flush=True)
    out, done = [], 0
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = [ex.submit(_fetch_cv, dep) for dep in deps]
        for f in as_completed(futs):
            done += 1
            r = f.result()
            if r:
                out.append(r)
            if done % 100 == 0:
                print(f"   {done}/{len(deps)}, {len(out)} cu CV", flush=True)
    out.sort(key=lambda x: x["nume"])
    cu_studii = sum(1 for r in out if r.get("studii"))
    json.dump({"total": len(out), "cu_studii": cu_studii, "cv": out},
              open(os.path.join(V, "companii/cv_parlament.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"PUBLICAT cv_parlament.json: {len(out)} deputați cu CV ({cu_studii} cu studii)", flush=True)
    return {"cv": len(out)}


if __name__ == "__main__":
    import urllib3
    urllib3.disable_warnings()
    main()
