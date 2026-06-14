"""Harvest rapoarte financiare anuale ale partidelor (RVC — venituri/cheltuieli) → SOLOMONAR.

Sursa: Portal Legislativ (legislatie.just.ro). Partidele publică anual în Monitorul Oficial,
în temeiul art. 16 din Legea 334/2006, situația cuantumului total al veniturilor și
cheltuielilor (cotizații, donații, împrumuturi, subvenții, alte surse). Aceste documente au
titlul „CUANTUM TOTAL" și emitent „Partide Politice".

Strategie de descoperire a ID-urilor (fără captcha, HTML server-rendered):
  1. POST pe formularul de căutare „/" cu TitleText=„CUANTUM TOTAL" + __RequestVerificationToken;
  2. paginare prin /Public/RezultateCautare?titlu=CUANTUM+TOTAL&...&page=N (filtrul e în query);
  3. pentru fiecare rezultat reținem doc_id + data publicării (MO nr. X din DD luna YYYY);
  4. fetch /public/DetaliiDocument/{id} → extragem numele partidului (id_parA42 /
     „Denumirea partidului politic:"), anul de raportare („primite în anul YYYY") și
     cifrele financiare din tabele (cotizații, donații, împrumuturi, subvenții, total venituri,
     cheltuieli).

Țintă: partidele parlamentare (PSD, PNL, AUR, USR, UDMR) pe anii 2023-2024. Rapoartele pentru
anul N se publică până la 30 aprilie N+1, deci an 2023 → MO aprilie/mai 2024, an 2024 → 2025.

Ex. confirmat: doc 297054 = raport USR pentru anul 2024 (MO 391/30.04.2025).

Output: data/v1/partide/rapoarte_rvc.json
"""

from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone

import requests
import urllib3

urllib3.disable_warnings()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "packages", "solomonar_core"))

V = os.path.join(ROOT, "data", "v1", "partide")
BASE = "https://legislatie.just.ro"
HOME = BASE + "/"
RESULTS = BASE + "/Public/RezultateCautare"
DOC = BASE + "/public/DetaliiDocument/{}"
HDRS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# Partide parlamentare țintă — mapăm denumirea oficială la un cod scurt.
PARLAMENTARE = {
    "psd": ["partidul social democrat", "social democrat"],
    "pnl": ["partidul national liberal", "national liberal"],
    "aur": ["alianta pentru unirea romanilor", "aur"],
    "usr": ["uniunea salvati romania", "salvati romania"],
    "udmr": ["uniunea democrata maghiara", "maghiara din romania", "rmdsz"],
    "pmp": ["miscarea populara"],
    "pro_romania": ["pro romania"],
    "forta_dreptei": ["forta dreptei"],
    "sos": ["s.o.s. romania", "sos romania"],
    "pot": ["partidul oamenilor tineri"],
}

LUNI = {
    "ianuarie": 1, "februarie": 2, "martie": 3, "aprilie": 4, "mai": 5, "iunie": 6,
    "iulie": 7, "august": 8, "septembrie": 9, "octombrie": 10, "noiembrie": 11, "decembrie": 12,
}


def _ascii(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()


def _cod_partid(denumire: str) -> str | None:
    d = _ascii(denumire)
    for cod, variante in PARLAMENTARE.items():
        if any(v in d for v in variante):
            return cod
    return None


def _parse_pub_date(pub: str) -> tuple[int | None, int | None, str | None]:
    """„Monitorul Oficial nr. 391 din 30 aprilie 2025" → (mo_nr, an_publicare, data_iso)."""
    nr = re.search(r"nr\.?\s*(\d+)", pub)
    md = re.search(r"din\s+(\d{1,2})\s+([a-zăâîșţț]+)\s+(\d{4})", pub, re.I)
    mo_nr = int(nr.group(1)) if nr else None
    if md:
        zi = int(md.group(1)); luna = LUNI.get(_ascii(md.group(2))); an = int(md.group(3))
        iso = f"{an:04d}-{luna:02d}-{zi:02d}" if luna else None
        return mo_nr, an, iso
    return mo_nr, None, None


def _get_token(s: requests.Session) -> str:
    r = s.get(HOME, verify=False, timeout=30)
    m = re.search(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"', r.text)
    if not m:
        raise RuntimeError("nu am gasit __RequestVerificationToken pe pagina de start")
    return m.group(1)


def _search_post(s: requests.Session, token: str) -> requests.Response:
    data = {
        "__RequestVerificationToken": token, "TitleText": "CUANTUM TOTAL",
        "ContentText_First": "", "opContentText_Second": "AND", "ContentText_Second": "",
        "opContentText_Third": "AND", "ContentText_Third": "", "opContentText_Fourth": "AND",
        "ContentText_Fourth": "", "DocumentType": "", "DocumentNumber": "",
        "DataSemnariiTextFrom": "", "DataSemnariiTextTo": "", "PublishedInName": "",
        "PublishedInNumber": "", "DataPublicariiTextFrom": "", "DataPublicariiTextTo": "",
        "ActInForceOnDateTextFrom": "", "EmitentAct": "",
    }
    return s.post(HOME, data=data, verify=False, timeout=30)


def _parse_results(html: str) -> list[dict]:
    out = []
    for b in html.split("search_result_item")[1:]:
        did = re.search(r"DetaliiDocument/(\d+)\"", b)
        if not did:
            continue
        ttl = re.search(r"DetaliiDocument/\d+\"[^>]*>([^<]+)", b)
        pub = re.search(r'S_PUB_BDY">([^<]+)', b)
        out.append({
            "doc_id": did.group(1),
            "titlu_list": (ttl.group(1).strip() if ttl else ""),
            "publicat_raw": (pub.group(1).strip() if pub else ""),
        })
    return out


def _max_page(html: str) -> int:
    pages = re.findall(r"RezultateCautare\?[^\"]*page=(\d+)", html)
    return max((int(p) for p in pages), default=1)


def harvest_ids(s: requests.Session, max_pages: int | None = None) -> list[dict]:
    """Paginare completă peste rezultatele CUANTUM TOTAL → listă {doc_id, titlu, publicat}."""
    token = _get_token(s)
    r0 = _search_post(s, token)
    total = re.search(r"(\d[\d.]*)\s*document", r0.text)
    print(f"   total rezultate CUANTUM TOTAL: {total.group(1) if total else '?'}", flush=True)
    last = _max_page(r0.text)
    items = _parse_results(r0.text)
    seen = {it["doc_id"] for it in items}
    pages = range(2, last + 1)
    if max_pages:
        pages = range(2, min(last, max_pages) + 1)
    for p in pages:
        url = f"{RESULTS}?titlu=CUANTUM+TOTAL&op2=AND&op3=AND&op4=AND&page={p}"
        try:
            r = s.get(url, verify=False, timeout=30)
        except Exception as e:
            print(f"   ! pagina {p} esuata: {e}", flush=True)
            continue
        for it in _parse_results(r.text):
            if it["doc_id"] not in seen:
                seen.add(it["doc_id"]); items.append(it)
        if p % 10 == 0:
            print(f"   ...pagina {p}/{last}, {len(items)} doc colectate", flush=True)
    print(f"   colectate {len(items)} doc_id (din {last} pagini)", flush=True)
    return items


def _strip_tables(html: str) -> str:
    """Text plat din corpul documentului, cu separatori de celulă/rând păstrați."""
    h = re.sub(r"<style.*?</style>", " ", html, flags=re.S)
    h = re.sub(r"<script.*?</script>", " ", h, flags=re.S)
    h = re.sub(r"</td>", " | ", h)
    h = re.sub(r"</tr>", "\n", h)
    h = re.sub(r"<[^>]+>", " ", h)
    h = h.replace("\xa0", " ")
    return h


def _num(s: str) -> float | None:
    """„5.651,00" → 5651.0 (format RO: punct=mii, virgulă=zecimal)."""
    s = s.strip()
    if not re.fullmatch(r"[\d.]+(?:,\d+)?", s):
        return None
    return float(s.replace(".", "").replace(",", "."))


def parse_document(s: requests.Session, doc_id: str) -> dict | None:
    try:
        r = s.get(DOC.format(doc_id), headers=HDRS, verify=False, timeout=40)
    except Exception as e:
        return {"doc_id": doc_id, "error": str(e)}
    if r.status_code != 200 or len(r.text) < 2000:
        return {"doc_id": doc_id, "error": f"status={r.status_code} len={len(r.text)}"}
    h = r.text
    # numele partidului
    den = re.search(r"Denumirea partidului politic:\s*([^<\n]+)", h)
    if not den:
        emt = re.search(r'S_EMT_BDY">\s*<li>([^<]+)', h)
        partid_nume = emt.group(1).strip() if emt else ""
    else:
        partid_nume = den.group(1).strip()
    flat = _strip_tables(h)
    flat_clean = re.sub(r"[ \t]+", " ", flat)
    # anul de raportare (din corp): „primite în anul YYYY" / „obtinute in anul YYYY"
    an = None
    m = re.search(r"(?:primite|ob[țt]inut\w*|cheltuiel\w*|sumele primite)\D{0,30}anul\s+(\d{4})",
                  flat_clean, re.I)
    if not m:
        m = re.search(r"\banul\s+(\d{4})", flat_clean)
    if m:
        an = int(m.group(1))
    cod = _cod_partid(partid_nume)
    # tip raport (multe documente sunt parțiale: doar cotizații, doar donații etc.)
    tipuri = []
    low = flat_clean.lower()
    if "cotiza" in low:
        tipuri.append("cotizatii")
    if "dona" in low:
        tipuri.append("donatii")
    if "imprumut" in low or "împrumut" in low:
        tipuri.append("imprumuturi")
    if "subven" in low:
        tipuri.append("subventii")
    if "cheltuiel" in low:
        tipuri.append("cheltuieli")
    if "venituri ob" in low or "veniturilor ob" in low or "total venituri" in low:
        tipuri.append("venituri_totale")
    venituri, cheltuieli, reprezentant = None, None, None
    # Tabelul „Situația centralizată a ... veniturilor" se încheie cu rândul
    # „Cuantumul total | <suma> |" — sursa autoritară pentru totalul de venituri.
    if "situa" in low and "centraliz" in low and ("venitur" in low):
        # ia ULTIMA aparitie a „Cuantumul total|<suma>" (tabelul real, nu cuprinsul)
        ct = re.findall(r"[Cc]uantumul total\s*\|\s*([\d.]+,\d{2})", flat)
        if ct:
            venituri = _num(ct[-1])
    # fallback: orice „cuantumul total al veniturilor" urmat de o sumă
    if venituri is None:
        mt = re.search(r"(?:total venituri|cuantumul total al veniturilor)\D{0,40}?([\d.]+,\d{2})",
                       flat_clean, re.I)
        if mt:
            venituri = _num(mt.group(1))
    mc = re.search(r"(?:total cheltuieli|cuantumul total al cheltuielilor)\D{0,40}?([\d.]+,\d{2})",
                   flat_clean, re.I)
    if mc:
        cheltuieli = _num(mc.group(1))
    # reprezentantul legal (semnatarul raportului)
    mr = re.search(r"reprezentantului legal\s*\|?\s*([A-ZȘȚĂÂÎ][^|<\n]{3,60}?)\s*(?:\||<|$)", flat)
    if mr:
        reprezentant = re.sub(r"\s+", " ", mr.group(1)).strip()
    # text relevant pentru audit (primele ~3500 caractere din corpul tabelar, fara navigatie)
    body_start = flat_clean.find("Denumirea partidului politic")
    if body_start < 0:
        body_start = flat_clean.find("Situa")
    detalii_text = flat_clean[max(0, body_start):body_start + 3500].strip()
    mo_nr, an_pub, data_iso = _parse_pub_date(
        re.search(r"MONITORUL OFICIAL nr\. \d+ din [^<]+", h).group(0)
        if re.search(r"MONITORUL OFICIAL", h) else "")
    return {
        "doc_id": doc_id,
        "url": DOC.format(doc_id),
        "partid_nume": partid_nume,
        "partid_cod": cod,
        "an": an,
        "an_publicare": an_pub,
        "mo_nr": mo_nr,
        "data_publicare": data_iso,
        "tip_raport": tipuri,
        "venituri": venituri,
        "cheltuieli": cheltuieli,
        "reprezentant_legal": reprezentant,
        "detalii_text": detalii_text,
    }


def main(max_pages: int | None = None, only_parlamentare: bool = True,
         ani: tuple[int, ...] = (2023, 2024)) -> dict:
    os.makedirs(V, exist_ok=True)
    s = requests.Session(); s.headers.update(HDRS)

    items = harvest_ids(s, max_pages=max_pages)
    # Pre-filtrare pe data publicarii: an N raportat in aprilie/mai N+1.
    ani_pub_tinta = {a + 1 for a in ani}
    candidate = []
    for it in items:
        _, an_pub, _ = _parse_pub_date(it["publicat_raw"])
        # pastram daca anul publicarii e in fereastra tinta SAU daca nu am putut citi data
        if an_pub is None or an_pub in ani_pub_tinta:
            candidate.append(it)
    print(f"   candidati dupa filtrul de data publicare ({sorted(ani_pub_tinta)}): "
          f"{len(candidate)}/{len(items)}", flush=True)

    rapoarte = []
    for i, it in enumerate(candidate, 1):
        rec = parse_document(s, it["doc_id"])
        if not rec or rec.get("error"):
            continue
        # filtru pe an de raportare + partid parlamentar
        if rec.get("an") not in ani:
            continue
        if only_parlamentare and not rec.get("partid_cod"):
            continue
        rapoarte.append(rec)
        if rec.get("partid_cod"):
            print(f"   [{len(rapoarte)}] {rec['partid_cod'].upper()} an={rec['an']} "
                  f"doc={rec['doc_id']} tip={rec['tip_raport']}", flush=True)
        if i % 25 == 0:
            print(f"   ...procesate {i}/{len(candidate)} candidate, {len(rapoarte)} retinute",
                  flush=True)

    # dedup pe (partid_cod, an, doc_id)
    seen = set(); uniq = []
    for r in rapoarte:
        k = (r["partid_cod"], r["an"], r["doc_id"])
        if k not in seen:
            seen.add(k); uniq.append(r)
    uniq.sort(key=lambda r: (r["partid_cod"] or "zzz", r["an"] or 0))

    out_path = os.path.join(V, "rapoarte_rvc.json")
    payload = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_url": BASE + "/ (cautare titlu='CUANTUM TOTAL')",
            "scraper": "harvest_rvc_partide.py",
            "temei_legal": "art. 16 Legea 334/2006",
            "ani_tinta": list(ani),
            "count": len(uniq),
            "doc_id_total_scanate": len(items),
        },
        "data": uniq,
    }
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    by = {}
    for r in uniq:
        by[r["partid_cod"]] = by.get(r["partid_cod"], 0) + 1
    print(f"\nPUBLICAT rapoarte_rvc.json: {len(uniq)} rapoarte | pe partid: {by}", flush=True)
    return {"count": len(uniq), "pe_partid": by, "out": out_path}


if __name__ == "__main__":
    mp = int(sys.argv[1]) if len(sys.argv) > 1 else None
    main(max_pages=mp)
