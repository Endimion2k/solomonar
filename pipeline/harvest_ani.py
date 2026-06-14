"""Harvest METADATE de declarații de pe portalul ANI VECHI (old-declaratii.integritate.eu).

Portalul vechi = JSF/ICEfaces, **ZERO captcha** (confirmat), declarații 2008–2022.
Spre deosebire de portalul ANI NOU (integritate.eu, Cloudflare Turnstile — blocat),
acesta servește căutarea + un tabel de rezultate cu metadate complete per declarant.

MECANISM SPART
--------------
1. GET /search.html → JSF view (ViewState + ice.window + ice.view). Formularul `form` are:
     - select  form:searchField_input  ∈ {numePrenume, institutia}
     - input   form:searchKey_input    = textul căutat
     - buton   form:submitButtonSS      (ICEfaces ACE partial-submit, execute/render=@all)
2. Submit-ul ICEfaces ACE e prea fragil cu `requests` pur (tabelul se randează în mai mulți
   pași AJAX) → folosim PLAYWRIGHT (headless chromium) ca să conducă search-ul + paginarea.
3. Tabelul `form:resultsTable` are coloane stabile (celule cu id-uri `…:N:numeCell` etc.):
     nume, institutie, functie, localitate, judet, data_completare, tip_declaratie
   + link "Vezi document" = GET /DownloadServlet?fileName={F}&uniqueIdentifier=NTNTARTLNE_{ID}
4. LIMITĂ portal: o căutare care întoarce >10.000 rezultate REFUZĂ să listeze (cere rafinare).
   → strategia de acoperire iterează pe căutări înguste (per instituție / per nume) sub 10k.
5. PDF-urile se descarcă cu `requests` pur (doar JSESSIONID dintr-un GET) → %PDF real.

OUTPUT: data/v1/declaratii/_ani_index.json — indexul metadatelor (NU 12M PDF-uri).
PII: metadatele NU conțin CNP/adrese; descărcăm doar câteva PDF-uri ca dovadă (verificăm %PDF).

Rulare:
  python pipeline/harvest_ani.py                      # pilot pe instituțiile-cheie + sample PDF
  python pipeline/harvest_ani.py --institutie "Senatul Romaniei"
  python pipeline/harvest_ani.py --nume "popescu" --max-pages 5
  python pipeline/harvest_ani.py --sample-pdfs 10     # câte PDF-uri de dovadă
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from solomonar_core.names import fix_ro_diacritics  # noqa: E402

BASE = "https://old-declaratii.integritate.eu"
SEARCH_URL = BASE + "/search.html"
UA = "SOLOMONAR-research/1.0 (civic transparency; contact catalinpopa2k@gmail.com)"

OUT_DIR = os.path.join(ROOT, "data", "v1", "declaratii")
INDEX_PATH = os.path.join(OUT_DIR, "_ani_index.json")
SAMPLE_DIR = os.path.join(ROOT, "data", "raw", "ani_old_sample")

# Instituții-cheie pentru HARVEST-PILOT (nume curate, sub limita de 10k fiecare).
PILOT_INSTITUTII = [
    "Senatul Romaniei",
    "Administratia Prezidentiala",
    "Ministerul Finantelor Publice",
    "Ministerul Afacerilor Externe",
    "Ministerul Justitiei",
    "Ministerul Sanatatii",
    "Compania Nationala de Cai Ferate CFR SA",
    "S.N.T.F.C. CFR Calatori SA",
]

# Coloane stabile din tabelul de rezultate (sufix id celulă).
CELL_COLS = {
    "nume": "numeCell",
    "institutie": "institutieCell",
    "functie": "functieCell",
    "localitate": "localitateCell",
    "judet": "judetCell",
    "data_completare": "dataCompletareCell",
    "tip_declaratie": "tipDeclaratieCell",
}


def fix_mojarra_utf8(s: str) -> str:
    """Normalizează textul servit de portal.

    Două probleme distincte:
    1. Diacritice DUBLU-encodate (UTF-8 citit ca latin-1: "Ã¢", "Èi"...) → roundtrip latin-1.
       Aplicat doar dacă roundtrip-ul reușește FĂRĂ caractere de înlocuire (evită corupția
       pe stringuri doar parțial dublu-encodate).
    2. Diacritice legacy cu cedilă (ş/ţ) → virgulă-jos (ș/ț), via fix_ro_diacritics.
    """
    if not s:
        return s
    if any(ch in s for ch in ("Ã", "Å", "È", "Ä", "â\x80")):
        try:
            fixed = s.encode("latin-1").decode("utf-8")
            if "�" not in fixed:
                s = fixed
        except (UnicodeDecodeError, UnicodeEncodeError):
            pass
    return fix_ro_diacritics(s)


# ---------------------------------------------------------------- Playwright search

def _search_and_collect(field: str, key: str, max_pages: int, settle_ms: int = 8000) -> tuple[list[dict], str]:
    """Conduce o căutare cu Playwright, paginează, întoarce (records, status).

    status ∈ {"ok", "over_limit", "empty"}.
    """
    from playwright.sync_api import sync_playwright

    records: list[dict] = []
    status = "ok"
    seen_uids: set[str] = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=UA)
        pg = ctx.new_page()
        try:
            pg.goto(SEARCH_URL, wait_until="networkidle", timeout=60000)
            pg.select_option("select[id='form:searchField_input']", field)
            pg.fill("input[id='form:searchKey_input']", key)
            pg.click("input[id='form:submitButtonSS']")
            pg.wait_for_timeout(settle_ms)

            html = pg.content()
            if "mai mult de 10 000" in html or "mai mult de 10000" in html:
                browser.close()
                return [], "over_limit"

            page_no = 0
            while True:
                html = pg.content()
                rows = _parse_rows(html, key, field)
                new = 0
                for r in rows:
                    uid = r.get("unique_id") or (r["nume"] + "|" + r["data_completare"])
                    if uid in seen_uids:
                        continue
                    seen_uids.add(uid)
                    records.append(r)
                    new += 1
                page_no += 1
                if page_no >= max_pages:
                    break
                # next-page link; disabled when on last page
                nxt = pg.query_selector(
                    "a[id$='_paginatorbottom_nextPageLink']:not(.ui-state-disabled)")
                if not nxt or new == 0:
                    break
                nxt.click()
                pg.wait_for_timeout(3500)

            if not records:
                status = "empty"
        finally:
            browser.close()
    return records, status


def _parse_rows(html: str, query_key: str, query_field: str) -> list[dict]:
    """Extrage rândurile din tabelul de rezultate randat."""
    out: list[dict] = []
    body_i = html.find('id="form:resultsTable_body"')
    if body_i < 0:
        return out
    body = html[body_i:html.find("</table>", body_i)]
    for tr in re.findall(r"<tr\b.*?</tr>", body, re.S):
        rec: dict = {}
        for col, suffix in CELL_COLS.items():
            m = re.search(
                r'id="form:resultsTable:\d+:' + suffix + r'"[^>]*>(.*?)</span>', tr, re.S)
            val = re.sub(r"<[^>]+>", "", m.group(1)).strip() if m else ""
            rec[col] = fix_mojarra_utf8(val)
        dl = re.search(
            r'DownloadServlet\?fileName=([^&"\']*)(?:&amp;|&)uniqueIdentifier=([^"\'<> ]*)', tr)
        if dl:
            rec["file_name"] = dl.group(1)
            rec["unique_identifier"] = dl.group(2)
            rec["unique_id"] = dl.group(2).replace("NTNTARTLNE_", "")
            rec["download_url"] = (
                f"{BASE}/DownloadServlet?fileName={dl.group(1)}"
                f"&uniqueIdentifier={dl.group(2)}")
        if rec.get("nume"):
            rec["_query"] = f"{query_field}={query_key}"
            out.append(rec)
    return out


# ---------------------------------------------------------------- PDF proof download

def download_sample_pdfs(records: list[dict], n: int) -> list[dict]:
    """Descarcă primele n PDF-uri (dovadă), verifică %PDF. requests pur + JSESSIONID."""
    import requests

    os.makedirs(SAMPLE_DIR, exist_ok=True)
    s = requests.Session()
    s.headers["User-Agent"] = UA
    s.get(SEARCH_URL, timeout=30)  # obține JSESSIONID

    proofs = []
    picked = [r for r in records if r.get("download_url")][:n]
    for r in picked:
        try:
            resp = s.get(r["download_url"], timeout=45)
            ok = resp.status_code == 200 and resp.content[:4] == b"%PDF"
            if ok:
                path = os.path.join(SAMPLE_DIR, r["file_name"].replace("/", "_"))
                with open(path, "wb") as f:
                    f.write(resp.content)
            proofs.append({
                "nume": r["nume"], "institutie": r["institutie"],
                "file_name": r["file_name"], "status": resp.status_code,
                "is_pdf": ok, "bytes": len(resp.content),
            })
        except Exception as e:  # noqa: BLE001
            proofs.append({"file_name": r.get("file_name"), "error": str(e)[:120]})
        time.sleep(0.6)  # respectă serverul
    return proofs


# ---------------------------------------------------------------- harvest driver

def _load_index() -> dict:
    if os.path.exists(INDEX_PATH):
        try:
            return json.load(open(INDEX_PATH, encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
    return {"meta": {}, "done_queries": [], "records": []}


def harvest(queries: list[tuple[str, str]], max_pages: int, sample_pdfs: int) -> dict:
    """queries = listă de (field, key). Resume-safe pe done_queries."""
    os.makedirs(OUT_DIR, exist_ok=True)
    idx = _load_index()
    done = set(idx.get("done_queries", []))
    by_uid = {r.get("unique_id") or (r["nume"] + r.get("data_completare", "")): r
              for r in idx.get("records", [])}

    over_limit, empties = [], []
    for field, key in queries:
        qid = f"{field}={key}"
        if qid in done:
            print(f"[skip] {qid} (deja făcut)", flush=True)
            continue
        print(f"[search] {qid} ...", flush=True)
        try:
            recs, status = _search_and_collect(field, key, max_pages)
        except Exception as e:  # noqa: BLE001
            print(f"  EROARE: {e}", flush=True)
            continue
        if status == "over_limit":
            over_limit.append(qid)
            print(f"  >10.000 rezultate — rafinează (NEindexat)", flush=True)
            continue
        if status == "empty":
            empties.append(qid)
        for r in recs:
            uid = r.get("unique_id") or (r["nume"] + r.get("data_completare", ""))
            by_uid[uid] = r
        done.add(qid)
        print(f"  +{len(recs)} înregistrări (total unic: {len(by_uid)})", flush=True)
        # persistă incremental (resume-safe)
        _save(by_uid, done, over_limit, empties, sample_pdfs=None)
        time.sleep(1.0)  # respectă serverul între căutări

    records = list(by_uid.values())
    proofs = None
    if sample_pdfs > 0 and records:
        print(f"[pdf] descarc {sample_pdfs} PDF-uri de dovadă ...", flush=True)
        proofs = download_sample_pdfs(records, sample_pdfs)
        ok = sum(1 for p in proofs if p.get("is_pdf"))
        print(f"  {ok}/{len(proofs)} PDF-uri valide (%PDF)", flush=True)

    payload = _save(by_uid, done, over_limit, empties, sample_pdfs=proofs)
    return payload


def _save(by_uid: dict, done: set, over_limit: list, empties: list, sample_pdfs) -> dict:
    records = list(by_uid.values())
    existing = _load_index()
    payload = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "sursa": "old-declaratii.integritate.eu (portal ANI vechi, JSF/ICEfaces, FĂRĂ captcha)",
            "acoperire_ani": "2008-2022",
            "metoda": "Playwright headless: search per instituție/nume, paginare; PDF via requests",
            "limita_portal": "căutările cu >10.000 rezultate nu se listează (rafinare necesară)",
            "total_metadate": len(records),
            "queries_facute": sorted(done),
            "queries_over_limit": over_limit,
            "queries_empty": empties,
        },
        "done_queries": sorted(done),
        "records": records,
    }
    if sample_pdfs is not None:
        payload["meta"]["sample_pdfs"] = sample_pdfs
    elif existing.get("meta", {}).get("sample_pdfs"):
        payload["meta"]["sample_pdfs"] = existing["meta"]["sample_pdfs"]
    json.dump(payload, open(INDEX_PATH, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    return payload


def main():
    ap = argparse.ArgumentParser(description="Harvest metadate declarații ANI portal vechi")
    ap.add_argument("--institutie", action="append", default=[],
                    help="caută după instituție (repetabil)")
    ap.add_argument("--nume", action="append", default=[],
                    help="caută după nume/prenume (repetabil)")
    ap.add_argument("--max-pages", type=int, default=20,
                    help="pagini max per căutare (25 rezultate/pagină)")
    ap.add_argument("--sample-pdfs", type=int, default=5,
                    help="câte PDF-uri de dovadă să descarce (0 = niciunul)")
    ap.add_argument("--pilot", action="store_true",
                    help="rulează lista de instituții-cheie (implicit dacă nu dai nimic)")
    args = ap.parse_args()

    queries: list[tuple[str, str]] = []
    for inst in args.institutie:
        queries.append(("institutia", inst))
    for nume in args.nume:
        queries.append(("numePrenume", nume))
    if not queries or args.pilot:
        for inst in PILOT_INSTITUTII:
            queries.append(("institutia", inst))

    print(f"Căutări de rulat: {len(queries)} | max-pages={args.max_pages} | "
          f"sample-pdfs={args.sample_pdfs}", flush=True)
    payload = harvest(queries, args.max_pages, args.sample_pdfs)
    m = payload["meta"]
    print("\n=== REZULTAT ===", flush=True)
    print(f"Metadate indexate (unic): {m['total_metadate']}", flush=True)
    print(f"Căutări over-limit (>10k): {m['queries_over_limit']}", flush=True)
    print(f"Output: {INDEX_PATH}", flush=True)
    if m.get("sample_pdfs"):
        ok = sum(1 for p in m["sample_pdfs"] if p.get("is_pdf"))
        print(f"PDF-uri dovadă: {ok}/{len(m['sample_pdfs'])} valide în {SAMPLE_DIR}", flush=True)


if __name__ == "__main__":
    main()
