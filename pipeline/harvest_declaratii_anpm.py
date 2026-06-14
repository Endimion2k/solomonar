"""Harvest declarații de avere ANPM/ANMAP (acoperă APM-urile județene consolidate).

Subdomeniile apm{cod}.anpm.ro au fost DECOMISIONATE; ANPM (acum ANMAP) publică toate declarațiile
centralizat pe anmap.gov.ro/declaratii-de-avere-si-interese-anpm-{an}/ — central + tot personalul
APM județean într-un singur loc. Scrapăm acele pagini (fără CAPTCHA), descărcăm PDF-urile „DA"
(avere), parsăm, REDACTĂM PII (Legea 176/2010), publicăm declaratii/avere_anpm.json.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from urllib.parse import urljoin

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from connectors.ani.declaratii import extract_pdf_text, parse_avere_text  # noqa: E402
from connectors.ani.redaction import find_pii  # noqa: E402
from solomonar_core.bronze import BronzeStore  # noqa: E402
from solomonar_core.http import Client  # noqa: E402
from solomonar_core.parse import selector  # noqa: E402

V = os.path.join(ROOT, "data/v1")
PAGES = [
    "https://anmap.gov.ro/declaratii-de-avere-si-interese-anpm-2024/",
    "https://anmap.gov.ro/declaratii-de-avere-si-interese-anpm-2025/",
]
RE_AVERE = re.compile(r"[-+ _]da[-+ _]", re.I)  # „DA" = declarație de AVERE (vs DI = interese)


def main() -> dict:
    bronze = BronzeStore(os.path.join(ROOT, "data", "raw"))
    client = Client(bronze=bronze, throttle_seconds=0.3, timeout=25)

    pdf_urls = set()
    for page in PAGES:
        try:
            content, _ = client.fetch(page, "anpm_pg", ".html", use_cache=True)
            text = content.decode("utf-8", "ignore") if isinstance(content, bytes) else content
            for h in selector(text).css("a::attr(href)").getall():
                u = urljoin(page, h)
                if u.lower().endswith(".pdf") and RE_AVERE.search(u):
                    pdf_urls.add(u)
        except Exception as e:
            print(f"   ! pagina {page}: {type(e).__name__}", flush=True)
    print(f"PDF-uri avere (DA) gasite pe ANMAP: {len(pdf_urls)}", flush=True)

    pdfs = client.fetch_many([(u, "anpm_pdf", ".pdf") for u in pdf_urls], workers=12)
    decls, pii_blocked, parsed = [], 0, 0
    for u, content in pdfs.items():
        if not content:
            continue
        try:
            txt = extract_pdf_text(content)
        except Exception:
            continue
        parsed += 1
        if find_pii(txt):
            pii_blocked += 1
            continue
        av = parse_avere_text(txt)
        signal = av.terenuri_count + av.cladiri_count + av.conturi_total_ron + av.venituri_anuale_ron
        if not av.text_extracted or signal == 0:
            continue
        decls.append({"institutie": "ANPM/APM", "pdf_url": u,
                      "terenuri": av.terenuri_count, "cladiri": av.cladiri_count,
                      "conturi_ron": round(av.conturi_total_ron), "venituri_ron": round(av.venituri_anuale_ron),
                      "datorii_ron": round(av.datorii_total_ron), "auto": av.auto_count})

    out = os.path.join(V, "declaratii/avere_anpm.json")
    json.dump({"generated_at": datetime.now(timezone.utc).isoformat(),
               "sursa": "anmap.gov.ro (ANPM central + APM judetene consolidate), Legea 176/2010, fara CAPTCHA",
               "total": len(decls), "pdf_descarcate": len([v for v in pdfs.values() if v]),
               "pii_blocate": pii_blocked, "declaratii": decls},
              open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"PUBLICAT avere_anpm.json: {len(decls)} declaratii | {parsed} parsate | "
          f"{pii_blocked} PII blocate | cache={bronze.count()}", flush=True)
    return {"declaratii": len(decls), "parsed": parsed, "pii_blocked": pii_blocked}


if __name__ == "__main__":
    main()
