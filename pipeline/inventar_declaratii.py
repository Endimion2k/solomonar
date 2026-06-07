"""Inventariază ce companii de stat / instituții publică declarații de avere+interese pe site propriu.

Scop: listă „cine are" → de atacat pe rând (ca CFR). NU descarcă declarațiile — doar găsește
URL-ul paginii + mecanismul (PDF direct / FileBird JS / sub-pagini / linkuri).

- Companii (fără website în date): extrage BRANDUL din nume (ROMGAZ, TAROM...) → ghicește {brand}.ro
- Instituții (organizatii cu `domain`): folosește domeniul existent
- Probează paginile de declarații în paralel; detectează semnalul.
"""

from __future__ import annotations

import json
import os
import re
import sys
import threading
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from romega_core.http import Client  # noqa: E402
from romega_core.parse import selector  # noqa: E402

V = os.path.join(ROOT, "data/v1")
FOUND_JSONL = os.path.join(V, "companii/_inventar_found.jsonl")
CHECKED_TXT = os.path.join(V, "companii/_inventar_checked.txt")
PATHS = ["/declaratii-de-avere/", "/declaratii-de-avere-si-interese/", "/declaratii/",
         "/integritate/"]
_LOCK = threading.Lock()
# cuvinte de eliminat din nume → rămâne brandul
_STOP = {"SOCIETATEA", "COMPANIA", "NATIONALA", "NATIONAL", "NAȚIONALĂ", "DE", "A", "AL", "SA",
         "SRL", "SN", "CN", "REGIA", "AUTONOMA", "AUTONOMĂ", "ROMANA", "ROMÂNĂ", "ROMANIA",
         "PENTRU", "SI", "ȘI", "TRANSPORT", "ADMINISTRARE", "PRODUCERE", "GAZE", "NATURALE",
         "ENERGIE", "ELECTRICA", "SERVICII", "S.A.", "S.R.L.", "GRUP", "HOLDING", "FILIALA"}

client = Client(throttle_seconds=0.05, timeout=6)


def _root_ok(base: str) -> bool:
    """Verifică rapid dacă domeniul răspunde (evită 3 path-uri pe domenii moarte)."""
    try:
        content, _ = client.fetch(base + "/", "inv", ".html", use_cache=True)
        return content is not None and len(content) > 200
    except Exception:
        return False


def _norm(s):
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()


def _brands(name: str) -> list[str]:
    """Candidați de brand din nume: token-uri în ghilimele + token distinctiv lung."""
    n = _norm(name).upper()
    quoted = re.findall(r'["”“]([A-Z0-9 \-]{2,30})["”“]', n)
    cands = []
    for q in quoted:
        cands.append(re.sub(r"[^A-Z0-9]", "", q))
    toks = [t for t in re.findall(r"[A-Z0-9]{3,}", n) if t not in _STOP]
    if toks:
        cands.append(toks[-1])                       # brandul e adesea ultimul token (…TAROM SA)
        cands.append(toks[0])                         # …sau primul (METROREX SA)
    if len(toks) >= 2:
        cands.append(toks[-2] + "-" + toks[-1])       # combo cu cratimă (POSTA-ROMANA)
        cands.append(toks[0] + "-" + toks[1])
    cands.extend(sorted(toks, key=len, reverse=True)[:2])  # cele mai lungi token-uri distinctive
    # dedup, păstrează ordinea
    seen, out = set(), []
    for c in cands:
        c = c.lower()
        if 3 <= len(c) <= 28 and c not in seen:
            seen.add(c); out.append(c)
    return out[:5]


def _detect(url: str):
    try:
        content, _ = client.fetch(url, "inv", ".html", use_cache=True)
        t = content.decode("utf-8", "ignore") if isinstance(content, bytes) else content
        if len(t) < 500:
            return None
        sel = selector(t)
        pdfs = [a.attrib.get("href", "") for a in sel.css("a")
                if a.attrib.get("href", "").lower().endswith(".pdf")
                and any(k in a.attrib.get("href", "").lower() for k in ("da-", "di-", "avere", "interes", "declarat"))]
        fb = "njt-fbdl" in t or "filebird" in t.lower()
        links = len(re.findall(r"declaratii-de-avere", t, re.I))
        if pdfs or fb or links > 2:
            mech = "filebird" if fb else ("pdf_direct" if pdfs else "sub-pagini")
            return {"url": url, "mecanism": mech, "pdf": len(pdfs), "linkuri_avere": links}
    except Exception:
        pass
    return None


def _check_entity(domains: list[str]):
    for dom in domains:
        for sch in ("https://www.", "https://"):
            base = sch + dom
            if not _root_ok(base):       # domeniul nu răspunde → sari la următorul
                continue
            for p in PATHS:
                r = _detect(base + p)
                if r:
                    return r
            break                        # domeniul există dar n-are pagină → nu mai încerca alt scheme
    return None


def main(limit: int = 0) -> dict:
    # instituții cu domain
    orgs = json.load(open(os.path.join(V, "organizatii/_index.json"), encoding="utf-8"))["data"]
    insts = [(o["name"], o.get("domain", ""), "institutie") for o in orgs
             if o.get("domain") and not o.get("placeholder")]
    # companii: brand → domeniu
    comps = json.load(open(os.path.join(V, "companii/_index.json"), encoding="utf-8"))["data"]
    soe = [(c["name"], c.get("cui"), "companie") for c in comps]

    targets = []
    for name, dom, typ in insts:
        d = re.sub(r"^https?://(www\.)?", "", dom).rstrip("/")
        targets.append((name, None, typ, [d]))
    for name, cui, typ in soe:
        targets.append((name, cui, typ, [b + ".ro" for b in _brands(name)]))
    if limit:
        targets = targets[:limit]

    # resume: sari peste cele deja verificate
    checked = set()
    if os.path.exists(CHECKED_TXT):
        checked = set(open(CHECKED_TXT, encoding="utf-8").read().splitlines())
    todo = [t for t in targets if f"{t[2]}:{t[0]}" not in checked]
    found_prev = sum(1 for _ in open(FOUND_JSONL, encoding="utf-8")) if os.path.exists(FOUND_JSONL) else 0
    print(f"de verificat: {len(todo)}/{len(targets)} (deja={len(checked)}, găsite anterior={found_prev})", flush=True)

    fh_found = open(FOUND_JSONL, "a", encoding="utf-8")
    fh_chk = open(CHECKED_TXT, "a", encoding="utf-8")
    done, found_n = 0, 0

    def _work(name, cui, typ, doms):
        r = _check_entity(doms)
        return name, cui, typ, r

    with ThreadPoolExecutor(max_workers=24) as ex:
        futs = [ex.submit(_work, n, c, t, d) for n, c, t, d in todo]
        for f in as_completed(futs):
            name, cui, typ, r = f.result()
            done += 1
            with _LOCK:
                fh_chk.write(f"{typ}:{name}\n"); fh_chk.flush()
                if r:
                    found_n += 1
                    rec = {"nume": name, "cui": cui, "tip": typ, **r}
                    fh_found.write(json.dumps(rec, ensure_ascii=False) + "\n"); fh_found.flush()
                    print(f"   ✔ [{found_prev + found_n}] {name[:40]} → {r['mecanism']} ({r['url'][:48]})", flush=True)
            if done % 100 == 0:
                print(f"   ...{done}/{len(todo)} verificate, +{found_n} găsite", flush=True)
    fh_found.close(); fh_chk.close()

    # compilează JSONL → JSON final
    surse = [json.loads(l) for l in open(FOUND_JSONL, encoding="utf-8") if l.strip()]
    surse.sort(key=lambda x: (x["tip"], x["nume"]))
    bym = {}
    for s in surse:
        bym[s["mecanism"]] = bym.get(s["mecanism"], 0) + 1
    json.dump({"total_verificate": len(checked) + done, "gasite": len(surse), "mecanisme": bym, "surse": surse},
              open(os.path.join(V, "companii/inventar_declaratii.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"\nGATA: {len(surse)} au pagină de declarații | mecanisme: {bym}", flush=True)
    return {"gasite": len(surse)}


if __name__ == "__main__":
    main(limit=int(sys.argv[1]) if len(sys.argv) > 1 else 0)
