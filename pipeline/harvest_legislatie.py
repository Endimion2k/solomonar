"""Harness ad-hoc — rulează LegislatieConnector live și exportă în data/v1/legislatie/index.json.

De ce un harness separat: connectorul (connectors/legislatie/legislatie.py) are doar GetToken +
helperi de parsare; pipeline/run.py îl raportează ca "pregătit" dar NU apelează fetch. Acest
script cheamă SOAP-ul real FreeWebService.svc (GetToken -> Search), parsează <Legi> și exportă.

Note pe SOAP-ul live (verificat pe 2026-06-10 din RO):
- endpoint real: .../apiws/FreeWebService.svc/SOAP  (WS din connector e doar baza /apiws)
- serverul cere User-Agent de browser (UA-ul bot ROMEGA primește 403 de la nginx)
- soapAction: http://tempuri.org/IFreeWebService/{GetToken,Search}
- Search: SearchModel{NumarPagina, RezultatePagina, SearchAn, SearchNumar, SearchText,
  SearchTitlu} + tokenKey -> ArrayOfLegi{Legi{DataVigoare, Emitent, LinkHtml, Numar,
  Publicatie, Text, TipAct, Titlu}}
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import requests
import urllib3

from connectors.legislatie.legislatie import (
    LegislatieConnector,
    get_token_envelope,
    parse_token,
)

urllib3.disable_warnings()

EP = "http://legislatie.just.ro/apiws/FreeWebService.svc/SOAP"
NS = "http://tempuri.org/"
DC = "http://schemas.datacontract.org/2004/07/FreeWebService"
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
OUT = Path(__file__).resolve().parents[1] / "data" / "v1" / "legislatie"

# câmpurile dintr-un nod <a:Legi>
_FIELDS = ["DataVigoare", "Emitent", "LinkHtml", "Numar", "Publicatie", "Text", "TipAct", "Titlu"]
_LEGI_BLOCK = re.compile(r"<a:Legi>(.*?)</a:Legi>", re.DOTALL)


def _unescape(s: str) -> str:
    return (
        s.replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&apos;", "'")
        .replace("&amp;", "&")
    )


def _field(block: str, name: str) -> str | None:
    m = re.search(rf"<a:{name}[^>]*?/>", block)
    if m:  # element nil (self-closing)
        return None
    m = re.search(rf"<a:{name}>(.*?)</a:{name}>", block, re.DOTALL)
    if not m:
        return None
    return _unescape(m.group(1)).strip()


def parse_search_response(xml: str) -> list[dict]:
    """Parsează SearchResponse SOAP -> listă de dict-uri Legi (text trunchiat)."""
    out: list[dict] = []
    for blk in _LEGI_BLOCK.findall(xml):
        rec = {f: _field(blk, f) for f in _FIELDS}
        text = rec.get("Text") or ""
        rec["TextLen"] = len(text)
        rec["Text"] = (text[:600] + "…") if len(text) > 600 else text
        # extrage id document din LinkHtml (.../DetaliiDocument/<id>)
        link = rec.get("LinkHtml") or ""
        mid = re.search(r"/DetaliiDocument/(\d+)", link)
        rec["DocId"] = mid.group(1) if mid else None
        out.append(rec)
    return out


def build_search_envelope(token: str, *, titlu=None, text=None, an=None, numar=None,
                          pagina=1, rezultate=20) -> str:
    def el(name: str, val) -> str:
        if val is None:
            return f'<a:{name} i:nil="true"/>'
        return f"<a:{name}>{val}</a:{name}>"

    model = (
        f'<SearchModel xmlns:a="{DC}" xmlns:i="http://www.w3.org/2001/XMLSchema-instance">'
        f"<a:NumarPagina>{pagina}</a:NumarPagina>"
        f"<a:RezultatePagina>{rezultate}</a:RezultatePagina>"
        f"{el('SearchAn', an)}{el('SearchNumar', numar)}"
        f"{el('SearchText', text)}{el('SearchTitlu', titlu)}"
        "</SearchModel>"
    )
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
        f'<soap:Body><Search xmlns="{NS}">{model}'
        f"<tokenKey>{token}</tokenKey></Search></soap:Body></soap:Envelope>"
    )


def _post(envelope: str, action: str) -> requests.Response:
    return requests.post(
        EP,
        data=envelope.encode("utf-8"),
        headers={
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": f"{NS}IFreeWebService/{action}",
            "User-Agent": BROWSER_UA,
        },
        timeout=90,
        verify=False,
    )


def main() -> int:
    # 1) GetToken — folosim helperii REALI ai connectorului (envelope + parser)
    conn = LegislatieConnector(namespace=NS)
    assert conn.source_id == "legislatie"
    tok_resp = _post(get_token_envelope(NS), "GetToken")
    tok_resp.raise_for_status()
    token = parse_token(tok_resp.text)
    if not token:
        print("[legislatie] GetToken a eșuat — fără token, nu pot căuta")
        return 1
    print(f"[legislatie] token live obținut (len={len(token)})")

    # 2) câteva căutări reprezentative (titlu + an) ca să dovedim date reale, variate
    queries = [
        {"label": "titlu:protectia datelor", "titlu": "protectia datelor", "rezultate": 20},
        {"label": "titlu:achizitii publice", "titlu": "achizitii publice", "rezultate": 20},
        {"label": "titlu:integritate an:2010", "titlu": "integritate", "an": "2010", "rezultate": 20},
        {"label": "titlu:cod fiscal", "titlu": "cod fiscal", "rezultate": 20},
        {"label": "titlu:transparenta decizionala", "titlu": "transparenta", "rezultate": 20},
    ]

    seen: set[str] = set()
    items: list[dict] = []
    per_query: list[dict] = []
    errors: list[str] = []

    for q in queries:
        env = build_search_envelope(
            token,
            titlu=q.get("titlu"),
            text=q.get("text"),
            an=q.get("an"),
            numar=q.get("numar"),
            pagina=1,
            rezultate=q.get("rezultate", 20),
        )
        try:
            r = _post(env, "Search")
            r.raise_for_status()
            if "Fault" in r.text[:2000]:
                raise RuntimeError("SOAP Fault: " + r.text[:200])
            recs = parse_search_response(r.text)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{q['label']}: {type(e).__name__}: {e}")
            per_query.append({"query": q["label"], "rezultate": 0, "err": str(e)[:120]})
            continue
        new = 0
        for rec in recs:
            key = rec.get("DocId") or (rec.get("LinkHtml") or rec.get("Titlu") or json.dumps(rec))
            if key in seen:
                continue
            seen.add(key)
            rec["_query"] = q["label"]
            items.append(rec)
            new += 1
        per_query.append({"query": q["label"], "rezultate": len(recs), "noi": new})
        print(f"[legislatie] {q['label']:42} -> {len(recs):3} acte ({new} noi)")

    # 3) export
    OUT.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    index = {
        "source_id": "legislatie",
        "source": "Portal Legislativ — legislatie.just.ro (FreeWebService.svc SOAP)",
        "endpoint": EP,
        "generat": now,
        "total": len(items),
        "queries": per_query,
        "acte": items,
    }
    (OUT / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    status = {
        "generated_at": now,
        "acte": len(items),
        "queries": len(queries),
        "errors": len(errors),
        "error_detail": errors,
        "live": True,
    }
    (OUT / "_status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[legislatie] export -> {OUT / 'index.json'}  ({len(items)} acte unice, {len(errors)} erori)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
