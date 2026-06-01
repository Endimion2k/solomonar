"""Loader pentru config/sources.yaml — single source of truth pentru connectors.

`iter_sources` aplatizează intrările cu `items` (ministere, agenții, deconcentrate) în
surse individuale, moștenind câmpurile părintelui.
"""

from __future__ import annotations

from pathlib import Path

import yaml

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "config" / "sources.yaml"


def load_sources(path: str | Path = DEFAULT_PATH) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def iter_sources(doc: dict) -> list[dict]:
    """Aplatizează: surse top-level + sub-instituțiile lor (`items`) ca surse de sine stătătoare."""
    out: list[dict] = []
    for s in doc.get("sources", []):
        base = {k: v for k, v in s.items() if k != "items"}
        out.append(base)
        for item in s.get("items", []):
            merged = dict(base)
            merged.update(item)
            merged["parent_group"] = s.get("id")
            out.append(merged)
    return out


def find_source(doc: dict, source_id: str) -> dict | None:
    for s in iter_sources(doc):
        if s.get("id") == source_id:
            return s
    return None
