"""Connector legislatie — Portal Legislativ (legislatie.just.ro) + parsare referințe de acte.

- parse_law_references: extrage citări (Legea 176/2010, OUG 109/2011, HG 617/2023...) din text.
  Util pentru a lega proiecte ↔ legi și pentru cross-referințe (declarații interese, contracte).
- link_laws_to_bills: leagă acte de proiecte după (număr, an).
- LegislatieConnector: SOAP GetToken → Search (best-effort; namespace/envelope de validat pe
  WSDL live, pe runner). Monitorul Oficial PDF e paywall — folosim acest portal gratuit.
"""

from __future__ import annotations

import re

from romega_core.http import Client

WS = "http://legislatie.just.ro/apiws"

RE_LAW = re.compile(
    r"(Legea|Lege|O\.?U\.?G\.?|OUG|O\.?G\.?|OG|H\.?G\.?|HG|"
    r"Ordonan\w+\s+de\s+urgen\w+|Ordonan\w+|Hot\w+r\w+rea)\s*"
    r"(?:nr\.?\s*)?(\d+)\s*/\s*(\d{4})",
    re.IGNORECASE,
)
RE_TOKEN = re.compile(r"<[^>]*[Tt]oken[^>]*>([^<]+)<")


def _norm_tip(t: str) -> str:
    s = t.lower().replace(".", "").replace(" ", "")
    if s.startswith("lege"):
        return "lege"
    if "oug" in s or "urgen" in s:
        return "oug"
    if s.startswith("hotar") or s == "hg":
        return "hg"
    if s.startswith("ordonan") or s == "og":
        return "og"
    return s


def parse_law_references(text: str) -> list[dict]:
    """Extrage referințe de acte normative din text (deduplicat)."""
    seen: set[tuple] = set()
    out: list[dict] = []
    for tip, nr, an in RE_LAW.findall(text):
        key = (_norm_tip(tip), int(nr), int(an))
        if key in seen:
            continue
        seen.add(key)
        out.append({"tip": key[0], "numar": key[1], "an": key[2]})
    return out


def link_laws_to_bills(laws: list[dict], bills: list[dict]) -> list[dict]:
    """Leagă acte de proiecte după (număr, an)."""
    idx = {(int(b["numar"]), int(b["an"])): b for b in bills if b.get("numar") and b.get("an")}
    out = []
    for law in laws:
        bill = idx.get((law["numar"], law["an"]))
        if bill:
            out.append({"law": law, "bill": bill})
    return out


def get_token_envelope(namespace: str = "http://tempuri.org/") -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
        f'<soap:Body><GetToken xmlns="{namespace}"/></soap:Body></soap:Envelope>'
    )


def parse_token(xml: bytes | str) -> str | None:
    text = xml.decode("utf-8", "replace") if isinstance(xml, (bytes, bytearray)) else xml
    m = RE_TOKEN.search(text)
    return m.group(1) if m else None


class LegislatieConnector:
    source_id = "legislatie"

    def __init__(self, client: Client | None = None, namespace: str = "http://tempuri.org/") -> None:
        self.client = client or Client()
        self.ns = namespace

    def get_token(self) -> str | None:  # pragma: no cover - SOAP live
        r = self.client.post(
            WS,
            data=get_token_envelope(self.ns),
            headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": f"{self.ns}GetToken"},
        )
        r.raise_for_status()
        return parse_token(r.text)
