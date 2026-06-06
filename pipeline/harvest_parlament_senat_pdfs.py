"""Construiește lista de PDF-uri de declarații pentru SENATORI (senat.ro).

Spre deosebire de cdep.ro (deputați), senat.ro NU expune declarațiile pe fișa fiecărui
senator (linkul „Declaraţii de avere/interese" e un postback ASP.NET inert fără JS real).
ÎNSĂ portalul agregat `DeclaratiiAvere.aspx` (footer → „Declaraţii de avere şi interese ale
senatorilor", /default.aspx?Sel=6618c55c-...) listează, într-un singur GET, TOATE declarațiile
tuturor senatorilor legislaturii curente — fără postback, fără captcha, fără browser.

Particularități de parsing ale paginii:
  - linkurile PDF folosesc GHILIMELE SIMPLE și SEPARATORI BACKSLASH (stil Windows):
        href='Declaratii\\Senatori\\2024\\A.ABRUDEAN.Mircea.10.06.2025.pdf'
    (de aceea un regex naiv href="...\\.pdf" le ratează);
  - fișierele sunt grupate pe FOLDER = anul de început al legislaturii:
        /Declaratii/Senatori/2024/  → mandatul curent 2024-2028  (ăsta ne interesează)
        /Declaratii/Senatori/2020/, /2016/, ... → mandate anterioare (senatori reveniți);
  - fiecare senator e un rând în GridViewDeclaratii, cu numele în `<b>NUME Prenume</b>`
    chiar înainte de tabelele lui de avere/interese → atribuim fiecare PDF senatorului
    al cărui marker `<b>` îl precede (asignare pe poziție).

Pentru paritate cu deputații (`harvest_parlament_pdfs.py` → checkpoint mandat curent), reținem
DOAR declarațiile mandatului curent (2024-2028). ATENȚIE: folderul NU e un criteriu fiabil de
mandat — senatorii reveniți (ex. OPREA, NOVAK, FENECHIU) au declarațiile noi de mandat (dec.2024
/ ian.2025) depuse tot în folderul lor vechi /2020/. Criteriul fiabil e DATA declarației din
numele fișierului. Reținem deci un PDF dacă: e în folderul /2024/ SAU data lui >= 2024-12-01
(începutul mandatului). Cele două reguli se completează → acoperire 134/134 senatori din roster.

Rezultat: checkpoint {pdf_url: "Senator <nume>"} dat apoi lui `harvest_reprocess`
(ROMEGA_SRC=parlament_senat) pentru avere ȘI interese.
"""

from __future__ import annotations

import bisect
import json
import os
import re
import sys
import unicodedata
from html import unescape as html_unescape
from urllib.parse import urljoin

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "packages", "romega_core"))

from romega_core.bronze import BronzeStore  # noqa: E402
from romega_core.http import Client  # noqa: E402

V = os.path.join(ROOT, "data/v1")
OUT = os.path.join(V, "declaratii/_parlament_senat_pdfs.json")

# Portalul agregat (footer fișă senator → „Declaraţii de avere şi interese ale senatorilor").
# /default.aspx?Sel=6618c55c-... redirecționează la DeclaratiiAvere.aspx; îl cerem direct.
PORTAL_URL = "https://www.senat.ro/DeclaratiiAvere.aspx"
# Mandatul curent (legislatura care începe în 2024). Folder = anul de început al legislaturii.
CURRENT_LEG_FOLDER = "2024"
# Începutul mandatului 2024-2028 (validare 21.12.2024). Declarațiile de „numire" (30 zile) sunt
# datate dec.2024 / ian.2025; ultima sesiune anuală a mandatului anterior a fost ~iun.2024 → un
# prag în dec.2024 separă curat mandatele, indiferent de folderul în care e depus fișierul.
CURRENT_MANDATE_START = (2024, 12, 1)  # (an, lună, zi)

# <b>NUME Prenume</b> urmat imediat de tabelul de layout al senatorului = antetul fiecărui rând.
_NAME_RE = re.compile(r"<b>\s*([^<>]+?)\s*</b>\s*<table cellspacing=\"0\" cellpadding=\"0\">")
# href cu ghilimele simple + backslash-uri, terminat în .pdf.
_PDF_RE = re.compile(r"href='([^']*\.pdf)'", re.IGNORECASE)
# data DD<sep>MM<sep>YYYY din numele fișierului (separator . _ sau -); luăm ULTIMA apariție.
_DATE_RE = re.compile(r"(\d{1,2})[._-](\d{1,2})[._-](\d{4})")


def _file_date(basename: str) -> tuple[int, int, int] | None:
    """Ultima dată DD.MM.YYYY / DD_MM_YYYY / DD-MM-YYYY din nume → (an, lună, zi) sau None."""
    ms = list(_DATE_RE.finditer(basename))
    if not ms:
        return None
    d, m, y = (int(x) for x in ms[-1].groups())
    return (y, m, d)


def _is_current_mandate(path: str) -> bool:
    """Mandat curent dacă e în folderul legislaturii curente SAU data declarației >= prag."""
    if f"/Senatori/{CURRENT_LEG_FOLDER}/" in path:
        return True
    dt = _file_date(path.rsplit("/", 1)[-1])
    return dt is not None and dt >= CURRENT_MANDATE_START


def _ro_key(name: str) -> frozenset:
    """Cheie de potrivire tolerantă la diacritice RO (ș/ş, ț/ţ, ă, â, î) și la ordinea numelui."""
    s = name.translate(str.maketrans({
        "ș": "s", "ş": "s", "Ș": "s", "Ş": "s", "ț": "t", "ţ": "t", "Ț": "t", "Ţ": "t",
        "ă": "a", "Ă": "a", "â": "a", "Â": "a", "î": "i", "Î": "i",
    }))
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower().replace("-", " ")
    s = re.sub(r"[^a-z ]", " ", s)
    return frozenset(t for t in s.split() if len(t) > 1)


def _titlecase(name: str) -> str:
    """„ABRUDEAN Mircea" → „Abrudean Mircea"; „CIUCĂ Nicolae-Ionel" → „Ciucă Nicolae-Ionel".

    Paritate cu eticheta deputaților (Nume-întâi, Title Case). Capitalizează și fiecare segment
    de nume cu cratimă; normalizează spațierea (unele markere `<b>` au spații/linii în plus).
    """
    def _cap(tok: str) -> str:
        return "-".join(p[:1].upper() + p[1:].lower() if p else p for p in tok.split("-"))

    return " ".join(_cap(w) for w in re.sub(r"\s+", " ", name).strip().split(" "))


def parse_portal(html: str) -> dict[str, str]:
    """HTML DeclaratiiAvere.aspx → {pdf_url_absolut: "Senator <Nume>"} pentru mandatul curent."""
    names = [(m.start(), m.group(1).strip()) for m in _NAME_RE.finditer(html)]
    name_pos = [p for p, _ in names]

    def _who(pos: int) -> str | None:
        i = bisect.bisect_right(name_pos, pos) - 1
        return names[i][1] if i >= 0 else None

    pdf_to_who: dict[str, str] = {}
    for m in _PDF_RE.finditer(html):
        # unele nume au diacritice ca entități HTML (ex. Cs&#225;sz&#225;r → Császár) → decodează
        pos, href = m.start(), html_unescape(m.group(1))
        path = href.replace("\\", "/")
        if not _is_current_mandate(path):  # doar mandatul curent (folder /2024/ sau dată >= prag)
            continue
        url = urljoin(PORTAL_URL, path)
        who = _who(pos)
        if who:
            pdf_to_who.setdefault(url, f"Senator {_titlecase(who)}")
    return pdf_to_who


def main() -> dict:
    bronze = BronzeStore(os.path.join(ROOT, "data", "raw"))
    client = Client(bronze=bronze, throttle_seconds=0.3, timeout=30)
    content, _ = client.fetch(PORTAL_URL, "senat_decl", ".html", use_cache=False)
    html = content.decode("utf-8", "ignore") if isinstance(content, bytes) else content
    print(f"Portal DeclaratiiAvere.aspx: {len(html)} chars", flush=True)

    pdf_to_who = parse_portal(html)
    senators = sorted(set(pdf_to_who.values()))
    print(f"PDF mandat curent (2024-2028): {len(pdf_to_who)} | senatori distincți: {len(senators)}",
          flush=True)

    # raport de acoperire față de rosterul oficial (senatori.json) — informativ, nu filtrează
    roster_path = os.path.join(V, "parlament/senatori.json")
    if os.path.exists(roster_path):
        roster = json.load(open(roster_path, encoding="utf-8"))["data"]
        rkeys = [_ro_key(r["name"]) for r in roster]
        have = [_ro_key(s.replace("Senator ", "")) for s in senators]

        def _covered(rk: frozenset) -> bool:
            return any(rk and (rk == hk or rk <= hk or hk <= rk) for hk in have)

        missing = [r["name"] for r, rk in zip(roster, rkeys) if not _covered(rk)]
        extra = [s for s, hk in zip(senators, have)
                 if not any(hk and (hk == rk or hk <= rk or rk <= hk) for rk in rkeys)]
        print(f"Roster senatori.json: {len(roster)} | cu declarații mandat curent: "
              f"{len(roster) - len(missing)} | FĂRĂ: {len(missing)}", flush=True)
        for m in missing:
            print(f"   (roster fără declarații) {m}", flush=True)
        for e in extra:  # senatori care au activat în mandat dar nu mai sunt în rosterul curent
            print(f"   (declarații dar nu în roster curent) {e}", flush=True)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(pdf_to_who, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print(f"Checkpoint salvat: {OUT}", flush=True)
    return {"pdfs": len(pdf_to_who), "senatori": len(senators)}


if __name__ == "__main__":
    main()
