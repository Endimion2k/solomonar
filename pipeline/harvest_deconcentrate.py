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

# județ -> cod auto (ISO 3166-2:RO) — folosit de subdomeniile ANPM (apm{cod}.anpm.ro) etc.
COUNTY_CODE = {
    "Alba": "ab", "Arad": "ar", "Argeș": "ag", "Bacău": "bc", "Bihor": "bh",
    "Bistrița-Năsăud": "bn", "Botoșani": "bt", "Brașov": "bv", "Brăila": "br", "Buzău": "bz",
    "Caraș-Severin": "cs", "Călărași": "cl", "Cluj": "cj", "Constanța": "ct", "Covasna": "cv",
    "Dâmbovița": "db", "Dolj": "dj", "Galați": "gl", "Giurgiu": "gr", "Gorj": "gj",
    "Harghita": "hr", "Hunedoara": "hd", "Ialomița": "il", "Iași": "is", "Ilfov": "if",
    "Maramureș": "mm", "Mehedinți": "mh", "Mureș": "ms", "Neamț": "nt", "Olt": "ot",
    "Prahova": "ph", "Satu Mare": "sm", "Sălaj": "sj", "Sibiu": "sb", "Suceava": "sv",
    "Teleorman": "tr", "Timiș": "tm", "Tulcea": "tl", "Vaslui": "vs", "Vâlcea": "vl",
    "Vrancea": "vn", "București": "b",
}
COUNTIES = list(COUNTY_CODE)

# tip serviciu -> (tipare domeniu {s}=slug judet / {c}=cod auto, cuvinte-cheie conținut pagină)
SERVICES = {
    "DSP": (["dsp{s}.ro", "dsp-{s}.ro"], ["directia de sanatate publica", "sanatate publica"]),
    "DSVSA": (["dsvsa{s}.ro", "dsvsa-{s}.ro", "dsvsa{c}.ro"],
              ["sanitar veterinar", "sanitara veterinara", "sanitar-veterinar"]),
    "ITM": (["itm{s}.ro", "itm{s}.inspectiamuncii.ro"],
            ["inspectoratul teritorial de munca", "inspectia muncii"]),
    "OCPI": (["ocpi{s}.ro", "ocpi-{s}.ro"], ["cadastru", "publicitate imobiliara"]),
    "AJOFM": (["ajofm{s}.ro", "{s}.anofm.ro"], ["ocuparea fortei de munca", "agentia judeteana"]),
    "ISJ": (["isj{s}.ro"], ["inspectoratul scolar", "inspectorat scolar"]),
    "DGASPC": (["dgaspc{s}.ro", "dgaspc-{s}.ro"],
               ["asistenta sociala si protectia copilului", "protectia copilului", "asistenta sociala"]),
    "APM": (["apm{c}.anpm.ro", "apm{s}.anpm.ro"], ["protectia mediului", "agentia pentru protectia mediului"]),
}


def slug(county: str) -> str:
    return strip_diacritics(county).lower().replace(" ", "").replace("-", "")


def main() -> dict:
    bronze = BronzeStore(os.path.join(ROOT, "data", "raw"))
    client = Client(bronze=bronze, throttle_seconds=0.4, timeout=12)

    cand = {}  # url -> (service, county)
    for svc, (patterns, _) in SERVICES.items():
        for county in COUNTIES:
            s, c = slug(county), COUNTY_CODE[county]
            for pat in patterns:
                host = pat.format(s=s, c=c)
                cand[f"https://www.{host}"] = (svc, county)
                cand[f"https://{host}"] = (svc, county)
    print(f"Candidati de probat: {len(cand)}", flush=True)

    fetched = client.fetch_many([(u, "decon", ".html") for u in cand], workers=16)
    found = {}  # (svc,county) -> {service,county,url,title,sections}
    errors = 0
    for url, content in fetched.items():
        if not content:
            continue
        try:
            svc, county = cand[url]
            text = content.decode("utf-8", "ignore") if isinstance(content, bytes) else content
            title = (selector(text).css("title::text").get() or "").strip()
            # match robust: cuvânt-cheie în CONȚINUTUL paginii (nu doar titlu — titluri ca
            # "Home" sau "I.T.M." dotat treceau pe lângă filtru); acronim în titlu compactat.
            hay = strip_diacritics(text).lower()
            tl_compact = strip_diacritics(title).lower().replace(".", "").replace(" ", "")
            kws = SERVICES[svc][1]
            if any(k in hay for k in kws) or svc.lower() in tl_compact:
                key = (svc, county)
                secs = find_institution_sections(text, url)  # preferă pagina cu mai multe secțiuni
                if key not in found or len(secs) > len(found[key]["sections"]):
                    found[key] = {"service": svc, "county": county, "url": url,
                                  "title": title[:55], "sections": secs}
        except Exception as e:  # o pagină proastă nu oprește harvest-ul
            errors += 1
            print(f"   ! eroare la {url}: {type(e).__name__}: {e}", flush=True)
    if errors:
        print(f"Pagini sărite din cauza erorilor: {errors}", flush=True)
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
    url_by_key = {(v["service"], v["county"]): v["url"] for v in found.values()}
    flipped = 0
    for o in doc["data"]:
        key = (o.get("short_name"), o.get("county"))
        if o.get("placeholder") and key in real_keys:
            o["placeholder"] = False
            o["domain"] = urlparse(url_by_key[key]).netloc
            flipped += 1
    json.dump(doc, open(idx_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    total_real = sum(1 for o in doc["data"]
                     if (o.get("short_name"), o.get("county")) in real_keys and not o.get("placeholder"))
    rest_ph = sum(1 for o in doc["data"] if o.get("placeholder"))
    print(f"Convertite ACUM: {flipped} | TOTAL deconcentrate reale in index: {total_real} | "
          f"placeholdere ramase: {rest_ph} | cache={bronze.count()}", flush=True)
    return {"found": len(found), "flipped": flipped, "total_real": total_real}


if __name__ == "__main__":
    main()
