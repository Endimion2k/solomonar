"""Harvester CV-uri conducere — parcursul școlar/profesional al leadership-ului SOE/instituții.

CV-urile sunt pe paginile de conducere/management (nu cu declarațiile), doar pt. CA/directori.
Două forme: PDF (CV-{Nume}.pdf pe Romgaz/Hidroelectrica) + inline HTML (bio în pagină, CFR/ministere).

Acest script: pt. fiecare domeniu (din inventar + SOE mari) găsește pagina de conducere →
colectează CV-PDF-uri + textul bio inline. Scrie cv_surse.json + _cv_pdfs.json (url→entitate).
Pas 2: download + parse CV-PDF + parsare bio inline (studii/experiență).
"""

from __future__ import annotations

import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from romega_core.http import Client  # noqa: E402
from romega_core.parse import selector  # noqa: E402

V = os.path.join(ROOT, "data/v1")
PATHS = ["/conducere/", "/conducerea/", "/management/", "/despre-noi/conducere/",
         "/organizare/conducere/", "/echipa/", "/consiliul-de-administratie/",
         "/conducere", "/management", "/cv/", "/curriculum-vitae/"]
RE_CV = re.compile(r"cv[-_ ]|curriculum", re.I)
RE_BIO = re.compile(r"studii|experien[țt]|absolvit|facultat|universitat|licen[țt]|master|doctor",
                    re.I)
KNOWN_SOE = {  # SOE mari cu domeniu non-brand (ratate de brand-guess)
    "cfr.ro": "CFR SA", "hidro.ro": "Hidroelectrica", "posta-romana.ro": "Posta Romana",
    "ancom.ro": "ANCOM", "mt.ro": "Min. Transporturi", "transelectrica.ro": "Transelectrica",
    "nuclearelectrica.ro": "Nuclearelectrica", "romgaz.ro": "Romgaz", "tarom.ro": "Tarom",
    "transgaz.ro": "Transgaz", "cnair.ro": "CNAIR", "metrorex.ro": "Metrorex",
}
client = Client(throttle_seconds=0.1, timeout=12)


def _dom(url: str) -> str:
    return re.sub(r"^https?://(www\.)?", "", url).split("/")[0]


def _find_cv(dom: str, name: str):
    """Găsește pagina de conducere → CV-PDF-uri + text bio inline."""
    for sch in ("https://www.", "https://"):
        for p in PATHS:
            url = sch + dom + p
            try:
                content, _ = client.fetch(url, "cv", ".html", use_cache=True)
                t = content.decode("utf-8", "ignore") if isinstance(content, bytes) else content
                if len(t) < 600:
                    continue
                sel = selector(t)
                cv_pdfs = [urljoin(url, a.attrib.get("href", "")) for a in sel.css("a")
                           if a.attrib.get("href", "").lower().endswith(".pdf")
                           and RE_CV.search(a.attrib.get("href", ""))]
                # bio inline: text vizibil dacă pagina vorbește de studii/experiență
                body = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t))
                bio_signal = len(RE_BIO.findall(body))
                if cv_pdfs or bio_signal >= 3:
                    return {"nume": name, "conducere_url": url, "domeniu": dom,
                            "cv_pdfs": cv_pdfs, "bio_inline": bio_signal >= 3,
                            "bio_len": len(body) if bio_signal >= 3 else 0}
            except Exception:
                pass
    return None


def main(limit: int = 0) -> dict:
    # domenii din inventar + SOE mari cunoscute
    inv = json.load(open(os.path.join(V, "companii/inventar_declaratii.json"), encoding="utf-8"))
    dom_name = {}
    for s in inv["surse"]:
        d = _dom(s["url"])
        dom_name.setdefault(d, s["nume"])
    for d, n in KNOWN_SOE.items():
        dom_name.setdefault(d, n)
    items = list(dom_name.items())
    if limit:
        items = items[:limit]
    print(f"caut CV-uri pe {len(items)} domenii...", flush=True)

    found, n_pdf, done = [], 0, 0
    with ThreadPoolExecutor(max_workers=12) as ex:
        futs = {ex.submit(_find_cv, d, n): (d, n) for d, n in items}
        for f in as_completed(futs):
            done += 1
            r = f.result()
            if r:
                found.append(r)
                n_pdf += len(r["cv_pdfs"])
                tag = f"{len(r['cv_pdfs'])} CV-pdf" + (" +bio-inline" if r["bio_inline"] else "")
                print(f"   ✔ {r['nume'][:40]}: {tag}", flush=True)
            if done % 50 == 0:
                print(f"   ...{done}/{len(items)}", flush=True)

    # cv_surse.json + _cv_pdfs.json
    cv_pdfs = {u: r["nume"] for r in found for u in r["cv_pdfs"]}
    json.dump({"surse": found, "total_surse": len(found), "total_cv_pdf": n_pdf,
               "cu_bio_inline": sum(1 for r in found if r["bio_inline"])},
              open(os.path.join(V, "companii/cv_surse.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    json.dump(cv_pdfs, open(os.path.join(V, "declaratii/_cv_pdfs.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"\nGATA: {len(found)} surse cu CV ({n_pdf} CV-pdf + "
          f"{sum(1 for r in found if r['bio_inline'])} cu bio inline)", flush=True)
    return {"surse": len(found), "cv_pdf": n_pdf}


if __name__ == "__main__":
    import urllib3
    urllib3.disable_warnings()
    main(limit=int(sys.argv[1]) if len(sys.argv) > 1 else 0)
