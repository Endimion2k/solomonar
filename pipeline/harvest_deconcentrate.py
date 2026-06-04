"""Harvest REAL pe servicii deconcentrate (Tier 3) — convertește placeholdere în date reale.

Probează tipare de domenii per tip de serviciu × județ (paralel + cache), confirmă prin
cuvânt-cheie în titlu, extrage secțiunile (conducere/declarații), și marchează nodurile
găsite ca placeholder=False în organizatii/_index.json. URL-urile NU-s într-un registru →
acoperire parțială (cât prind tiparele), restul rămân placeholdere onest etichetate.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from connectors.institutie.generic import find_institution_sections  # noqa: E402
from romega_core.bronze import BronzeStore  # noqa: E402
from romega_core.http import Client  # noqa: E402
from romega_core.names import strip_diacritics  # noqa: E402
from romega_core.parse import selector  # noqa: E402

COUNTIES = [
    "Alba", "Arad", "Argeș", "Bacău", "Bihor", "Bistrița-Năsăud", "Botoșani", "Brașov", "Brăila",
    "Buzău", "Caraș-Severin", "Călărași", "Cluj", "Constanța", "Covasna", "Dâmbovița", "Dolj",
    "Galați", "Giurgiu", "Gorj", "Harghita", "Hunedoara", "Ialomița", "Iași", "Ilfov", "Maramureș",
    "Mehedinți", "Mureș", "Neamț", "Olt", "Prahova", "Satu Mare", "Sălaj", "Sibiu", "Suceava",
    "Teleorman", "Timiș", "Tulcea", "Vaslui", "Vâlcea", "Vrancea", "București",
]

# tip serviciu -> (tipare domeniu cu {s}=slug judet, cuvinte-cheie titlu)
SERVICES = {
    "DSP": (["dsp{s}.ro", "dsp-{s}.ro"], ["sanatate publica"]),
    "DSVSA": (["dsvsa{s}.ro", "dsvsa-{s}.ro"], ["sanitar veterinar", "sanitara veterinara"]),
    "ITM": (["itm{s}.ro", "itm{s}.inspectiamuncii.ro"], ["inspectia muncii", "inspectoratul teritorial"]),
    "OCPI": (["ocpi{s}.ro", "ocpi-{s}.ro"], ["cadastru"]),
    "AJOFM": (["ajofm{s}.ro", "{s}.anofm.ro"], ["ocuparea fortei", "forta de munca", "ocupare"]),
    "ISJ": (["isj{s}.ro"], ["inspectoratul scolar", "inspectorat scolar"]),
    "DGASPC": (["dgaspc{s}.ro", "dgaspc-{s}.ro"], ["asistenta sociala", "protectia copilului"]),
    "APM": (["apm{s}.anpm.ro"], ["protectia mediului", "mediu"]),
}


def slug(county: str) -> str:
    return strip_diacritics(county).lower().replace(" ", "").replace("-", "")


def main() -> dict:
    bronze = BronzeStore(os.path.join(ROOT, "data", "raw"))
    client = Client(bronze=bronze, throttle_seconds=0.4, timeout=12)

    cand = {}  # url -> (service, county)
    for svc, (patterns, _) in SERVICES.items():
        for county in COUNTIES:
            s = slug(county)
            for pat in patterns:
                cand[f"https://www.{pat.format(s=s)}"] = (svc, county)
                cand[f"https://{pat.format(s=s)}"] = (svc, county)
    print(f"Candidati de probat: {len(cand)}", flush=True)

    fetched = client.fetch_many([(u, "decon", ".html") for u in cand], workers=16)
    found = {}  # (svc,county) -> {service,county,url,title,sections}
    for url, content in fetched.items():
        if not content:
            continue
        svc, county = cand[url]
        title = (selector(content).css("title::text").get() or "").strip()
        tl = strip_diacritics(title).lower()
        kws = SERVICES[svc][1]
        if any(k in tl for k in kws) or svc.lower() in tl:
            key = (svc, county)
            if key not in found:
                found[key] = {"service": svc, "county": county, "url": url,
                              "title": title[:55], "sections": find_institution_sections(content, url)}
    print(f"Servicii deconcentrate REALE gasite: {len(found)}", flush=True)

    by_svc = {}
    for (svc, _), v in found.items():
        by_svc[svc] = by_svc.get(svc, 0) + 1
    for svc, n in sorted(by_svc.items(), key=lambda x: -x[1]):
        print(f"   {svc:7} {n}/42", flush=True)

    out = os.path.join(ROOT, "data/v1/institutii")
    json.dump({"generated_at": datetime.now(timezone.utc).isoformat(),
               "gasite": len(found), "pe_tip": by_svc, "institutii": list(found.values())},
              open(os.path.join(out, "deconcentrate_real.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    # marchez nodurile gasite ca placeholder=False (+ domain) in organizatii/_index.json
    idx_path = os.path.join(ROOT, "data/v1/organizatii/_index.json")
    doc = json.load(open(idx_path, encoding="utf-8"))
    real_keys = {(v["service"], v["county"]) for v in found.values()}
    flipped = 0
    for o in doc["data"]:
        if o.get("placeholder") and (o.get("short_name"), o.get("county")) in real_keys:
            o["placeholder"] = False
            o["domain"] = urlparse(next(v["url"] for v in found.values()
                                        if v["service"] == o["short_name"] and v["county"] == o["county"])).netloc
            flipped += 1
    json.dump(doc, open(idx_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"Noduri convertite placeholder->real in index: {flipped} | cache={bronze.count()}", flush=True)
    return {"found": len(found), "flipped": flipped}


if __name__ == "__main__":
    main()
