"""Harvester CV-uri DEEP — parcursul școlar/profesional al conducerii SOE/instituții.

Două tipare (documentate):
- SOE: CV-PDF pe /concursuri/ /cariera/ /guvernanta-corporativa/ /anunturi/ /management/ /conducere/
  (CFR=44 la crawl adânc, nu 0!). Crawl BFS depth 2, urmărește sub-pagini concurs/selecție/numire.
- Ministere/agenții/guvern: bio INLINE HTML pe pagini per-persoană (gov.ro/cabinetul-de-ministri,
  ANAF demnitari, conducere) — capturăm textul bio + urmărim linkuri per-persoană.

Scrie cv_surse.json + _cv_pdfs.json (url→entitate) + _cv_inline.json (url→entitate, pt. bio HTML).
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from romega_core.http import Client  # noqa: E402
from romega_core.parse import selector  # noqa: E402

V = os.path.join(ROOT, "data/v1")
SEED_PATHS = ["/conducere/", "/conducerea/", "/management/", "/guvernanta-corporativa/",
              "/cariera/", "/cariere/", "/concursuri/", "/anunturi/", "/posturi-vacante/",
              "/resurse-umane/", "/selectie-administratori/", "/despre-noi/conducere/",
              "/organizare/conducerea-ministerului/", "/integritate/", "/echipa/",
              "/consiliul-de-administratie/", "/conducere", "/cariera"]
RE_CV = re.compile(r"cv[-_ /.]|curriculum|europass", re.I)
RE_FOLLOW = re.compile(r"concurs|cariera|cariere|selectie|select-|post|anunt|numire|conducer|"
                       r"administrator|director|demnitar|secretar-de-stat|membri|guvernanta", re.I)
RE_BIO = re.compile(r"studii|experien[țt]|absolvit|facultat|universitat|licen[țt]|master|"
                    r"doctor|n[ăa]scut|carier[ăa]", re.I)
KNOWN_SOE = {
    "cfr.ro": "CFR SA", "hidro.ro": "Hidroelectrica", "posta-romana.ro": "Posta Romana",
    "ancom.ro": "ANCOM", "transelectrica.ro": "Transelectrica", "nuclearelectrica.ro": "Nuclearelectrica",
    "romgaz.ro": "Romgaz", "tarom.ro": "Tarom", "transgaz.ro": "Transgaz", "cnair.ro": "CNAIR",
    "metrorex.ro": "Metrorex", "salrom.ro": "Salrom",
}
client = Client(throttle_seconds=0.08, timeout=12)
_seen_pdf = set()
_lock_pdf = None


def _dom(url):
    return re.sub(r"^https?://(www\.)?", "", url).split("/")[0]


def _crawl(dom, name):
    """BFS depth 2 pe paginile de conducere/concursuri → CV-PDF + pagini bio inline."""
    base = None
    for sch in ("https://www.", "https://"):
        try:
            content, _ = client.fetch(sch + dom + "/", "cvh", ".html", use_cache=True)
            if content and len(content) > 300:
                base = sch + dom
                break
        except Exception:
            pass
    if not base:
        return name, set(), set()
    netloc = urlparse(base).netloc
    visited, queue = set(), deque((base + p, 0) for p in SEED_PATHS)
    cv_pdfs, bio_pages = set(), set()
    while queue and len(visited) < 70:
        url, depth = queue.popleft()
        if url in visited:
            continue
        visited.add(url)
        try:
            content, _ = client.fetch(url, "cvh", ".html", use_cache=True)
            t = content.decode("utf-8", "ignore") if isinstance(content, bytes) else content
        except Exception:
            continue
        if len(t) < 500:
            continue
        sel = selector(t)
        had_cv = False
        for a in sel.css("a"):
            h = a.attrib.get("href", "")
            if h.lower().endswith(".pdf") and RE_CV.search(h):
                cv_pdfs.add(urljoin(url, h)); had_cv = True
        # bio inline: pagina vorbește de studii/experiență dar n-are CV-pdf
        body = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t))
        if not had_cv and len(RE_BIO.findall(body)) >= 3:
            bio_pages.add(url)
        # urmează sub-pagini relevante (depth<2)
        if depth < 2:
            for a in sel.css("a"):
                h = a.attrib.get("href", "")
                full = urljoin(url, h).split("#")[0]
                if (RE_FOLLOW.search(h) and urlparse(full).netloc == netloc
                        and full not in visited and len(queue) < 120):
                    queue.append((full, depth + 1))
    return name, cv_pdfs, bio_pages


CKPT = os.path.join(V, "companii/_cv_checked.txt")
PDF_JL = os.path.join(V, "companii/_cv_pdfs.jsonl")
INL_JL = os.path.join(V, "companii/_cv_inline.jsonl")
import threading  # noqa: E402
_L = threading.Lock()


def main(limit: int = 0) -> dict:
    dom_name = {}
    # 1. toate instituțiile reale (organizatii) cu domeniu
    org = json.load(open(os.path.join(V, "organizatii/_index.json"), encoding="utf-8"))["data"]
    for o in org:
        d = o.get("domain")
        if d and not o.get("placeholder"):
            dom_name.setdefault(re.sub(r"^https?://(www\.)?", "", d).rstrip("/").split("/")[0],
                                o.get("name", ""))
    # 2. inventar declarații (companii + instituții)
    inv = json.load(open(os.path.join(V, "companii/inventar_declaratii.json"), encoding="utf-8"))
    for s in inv["surse"]:
        dom_name.setdefault(_dom(s["url"]), s["nume"])
    # 3. SOE mari cunoscute
    for d, n in KNOWN_SOE.items():
        dom_name.setdefault(d, n)
    # 4. site-urile SOE locale găsite la căutarea online (2026-06-11, _localsoe_found*.json)
    import glob as _g
    for ff in _g.glob(os.path.join(ROOT, "pipeline", "_localsoe_found*.json")):
        try:
            for c in json.load(open(ff, encoding="utf-8")):
                site = c.get("site") or c.get("declaratii_url")
                if site and site.startswith("http"):
                    dom_name.setdefault(_dom(site), c.get("name", ""))
        except Exception:
            pass

    checked = set(open(CKPT, encoding="utf-8").read().splitlines()) if os.path.exists(CKPT) else set()
    items = [(d, n) for d, n in dom_name.items() if d not in checked]
    if limit:
        items = items[:limit]
    print(f"crawl CV deep: {len(items)}/{len(dom_name)} domenii (deja={len(checked)})", flush=True)

    fh_p = open(PDF_JL, "a", encoding="utf-8")
    fh_i = open(INL_JL, "a", encoding="utf-8")
    fh_c = open(CKPT, "a", encoding="utf-8")
    done, tot_pdf = 0, 0

    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = {ex.submit(_crawl, d, n): (d, n) for d, n in items}
        for f in as_completed(futs):
            done += 1
            d, n = futs[f]
            try:
                name, pdfs, bios = f.result()
            except Exception:
                pdfs, bios, name = set(), set(), n
            with _L:
                fh_c.write(d + "\n"); fh_c.flush()
                for u in pdfs:
                    fh_p.write(json.dumps({"url": u, "nume": name}, ensure_ascii=False) + "\n")
                for u in bios:
                    fh_i.write(json.dumps({"url": u, "nume": name}, ensure_ascii=False) + "\n")
                fh_p.flush(); fh_i.flush()
                tot_pdf += len(pdfs)
                if pdfs or bios:
                    print(f"   ✔ {name[:38]}: {len(pdfs)} CV-pdf, {len(bios)} bio (cumul pdf={tot_pdf})", flush=True)
            if done % 50 == 0:
                print(f"   ...{done}/{len(items)}", flush=True)
    fh_p.close(); fh_i.close(); fh_c.close()

    # compilează JSONL → JSON
    cv_pdfs = {r["url"]: r["nume"] for r in (json.loads(l) for l in open(PDF_JL, encoding="utf-8") if l.strip())}
    cv_inline = {r["url"]: r["nume"] for r in (json.loads(l) for l in open(INL_JL, encoding="utf-8") if l.strip())}
    json.dump(cv_pdfs, open(os.path.join(V, "declaratii/_cv_pdfs.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    json.dump(cv_inline, open(os.path.join(V, "declaratii/_cv_inline.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\nGATA: {len(cv_pdfs)} CV-PDF + {len(cv_inline)} pagini bio-inline", flush=True)
    return {"cv_pdf": len(cv_pdfs), "bio_inline": len(cv_inline)}


if __name__ == "__main__":
    import urllib3
    urllib3.disable_warnings()
    main(limit=int(sys.argv[1]) if len(sys.argv) > 1 else 0)
