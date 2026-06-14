"""Helpers de parsing — parsel (CSS/XPath) + handling encoding legacy.

cdep.ro servește HTML în ISO-8859-2 (Latin-2). senat.ro e UTF-8/windows-1250. Acest modul
centralizează decodarea + selectorii ca să nu se repete în fiecare connector.
"""

from __future__ import annotations

from parsel import Selector


def decode(content: bytes, encoding: str | None = None) -> str:
    """Decodează bytes → str. Încearcă encoding-ul dat, apoi fallback-uri uzuale RO."""
    if encoding:
        return content.decode(encoding, errors="replace")
    for enc in ("utf-8", "iso-8859-2", "windows-1250"):
        try:
            return content.decode(enc)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def selector(content: bytes | str, encoding: str | None = None) -> Selector:
    text = decode(content, encoding) if isinstance(content, (bytes, bytearray)) else content
    return Selector(text=text)


def first_text(sel: Selector, css: str, default: str | None = None) -> str | None:
    val = sel.css(css).get()
    return val.strip() if val else default


def all_texts(sel: Selector, css: str) -> list[str]:
    return [t.strip() for t in sel.css(css).getall() if t and t.strip()]
