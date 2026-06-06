"""Connector parlament/comisii — activitatea comisiilor Camerei Deputaților (cdep.ro).

Lanț: lista comisiilor → ședințe per comisie/an → ordinea de zi (PDF) → PLx-uri (linkuri în PDF)
→ pagina proiectului → documente (expunere motive, formă inițiator, avize CSM/CL/comisii, rapoarte).

URL-uri:
- comisii:      /ords/co/sedinte2015.comisii
- ședințe:      /ords/co/sedinte2015.lista?tip={tip}&an={an}   → linkuri docs?F.../Ordinea de zi {data}.pdf
- ordine de zi: /ords/co/docs?F{id}/...pdf  (anotări PDF = linkuri către pagini PLx)
- pagină PLx:   /ords/pls/proiecte/upl_pck2015.proiect?cam=2&idp={idp}
- documente PLx: /proiecte/{an}/.../{em|pl|csm|cl|gv}NNN.pdf + /comisii/{comisie}/pdf/{an}/avNNN.pdf
"""

from __future__ import annotations

import re
from urllib.parse import urljoin

from romega_core.parse import selector

CO_BASE = "https://www.cdep.ro/ords/co/"
COMISII_URL = CO_BASE + "sedinte2015.comisii"

_MONTHS_RO = {
    "ianuarie": 1, "februarie": 2, "martie": 3, "aprilie": 4, "mai": 5, "iunie": 6,
    "iulie": 7, "august": 8, "septembrie": 9, "octombrie": 10, "noiembrie": 11, "decembrie": 12,
}
_RE_DATE = re.compile(r"(\d{1,2})\s+([a-zăâî]+)\s+(\d{4})", re.I)
# clasificare document după prefixul fișierului
_DOC_TYPES = {
    "em": "expunere_motive", "pl": "forma_initiator", "csm": "aviz_csm",
    "cl": "aviz_consiliu_legislativ", "gv": "punct_vedere_guvern", "av": "aviz_comisie",
    "rp": "raport", "rs": "raport_suplimentar", "rd": "raport", "se": "sesizare",
    "ce": "cerere", "pvc": "proces_verbal",
}


def _txt(s: str) -> str:
    return " ".join((s or "").split())


def parse_committee_tips(html: str | bytes) -> list[int]:
    """Tip-urile (ID) comisiilor din pagina-listă (linkuri lista?tip=N&an=)."""
    t = html.decode("utf-8", "ignore") if isinstance(html, bytes) else html
    return sorted({int(m) for m in re.findall(r"tip=(\d+)&an=20", t)})


def parse_committee_name(html: str | bytes) -> str:
    """Numele comisiei de pe pagina-listă de ședințe (h1/h2/title)."""
    t = html.decode("utf-8", "ignore") if isinstance(html, bytes) else html
    sel = selector(t)
    for css in ("h1::text", "h2::text", "title::text"):
        v = _txt(sel.css(css).get() or "")
        if v and "cdep" not in v.lower() and len(v) > 8:
            return v[:120]
    return ""


def parse_session_agendas(html: str | bytes) -> list[dict]:
    """Linkurile ordinii de zi (PDF) dintr-o pagină de ședințe → [{date, agenda_pdf_url}]."""
    t = html.decode("utf-8", "ignore") if isinstance(html, bytes) else html
    out, seen = [], set()
    for a in selector(t).css("a"):
        h = a.attrib.get("href", "")
        if "docs?" in h or "/co/docs" in h:
            url = urljoin(CO_BASE, h)
            if url in seen:
                continue
            seen.add(url)
            out.append({"agenda_pdf_url": url, "date": _date_from_agenda(url)})
    return out


def _date_from_agenda(url: str) -> str | None:
    """Extrage data din numele 'Ordinea de zi {zi} {luna} {an}.pdf' → ISO."""
    from urllib.parse import unquote
    m = _RE_DATE.search(unquote(url))
    if not m:
        return None
    day, mon, year = int(m.group(1)), m.group(2).lower(), int(m.group(3))
    mm = _MONTHS_RO.get(mon)
    return f"{year:04d}-{mm:02d}-{day:02d}" if mm else None


def agenda_plx_links(pdf_bytes: bytes) -> list[str]:
    """Linkurile (anotări) către pagini PLx dintr-un PDF de ordine de zi (via PyMuPDF)."""
    import fitz
    links: set[str] = set()
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page in doc:
            for l in page.get_links():
                u = l.get("uri") or ""
                if "upl_pck2015.proiect" in u or "idp=" in u:
                    links.add(u.replace("http://", "https://"))
    return sorted(links)


def parse_plx_page(html: str | bytes, page_url: str = "") -> dict:
    """Pagina proiectului PLx → {numar, an, titlu, camera, documente:[{tip,url}]}."""
    t = html.decode("utf-8", "ignore") if isinstance(html, bytes) else html
    sel = selector(t)
    title = _txt(sel.css("title::text").get() or "")
    m = re.search(r"(\d+)\s*/\s*(\d{4})", title)
    numar, an = (int(m.group(1)), int(m.group(2))) if m else (None, None)
    docs, seen = [], set()
    for a in sel.css("a"):
        h = a.attrib.get("href", "")
        if h.lower().endswith(".pdf"):
            url = urljoin("https://www.cdep.ro/", h)
            if url in seen:
                continue
            seen.add(url)
            docs.append({"tip": _doc_type(url), "url": url})
    return {"titlu": title[:160], "numar": numar, "an": an, "documente": docs}


def _doc_type(url: str) -> str:
    fn = url.rsplit("/", 1)[-1].lower()
    m = re.match(r"([a-z]+)\d", fn)
    return _DOC_TYPES.get(m.group(1), "alt") if m else "alt"
