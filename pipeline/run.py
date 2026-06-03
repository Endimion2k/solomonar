"""CLI runner — `python -m pipeline.run --source <id>` / `--list`.

Citește config/sources.yaml, găsește sursa, dispatch la connector-ul implementat. Pentru
surse fără connector încă, raportează planul (status/fază). Apelat de CI (.github/workflows).
"""

from __future__ import annotations

import argparse
import sys

from pipeline.config import find_source, iter_sources, load_sources


def _build_connector(source_id: str):
    """Registry de connectoare implementate (crește pe măsură ce avansează valurile)."""
    if source_id == "cdep":
        from connectors.parlament.cdep import CdepConnector

        return CdepConnector()
    if source_id == "senat":
        from connectors.parlament.senat import SenatConnector

        return SenatConnector()
    if source_id == "ani":
        from connectors.ani.declaratii import AniConnector

        return AniConnector()
    if source_id == "anaf_api":
        from connectors.fiscal.anaf import AnafConnector

        return AnafConnector()
    if source_id == "sicap_bulk":
        from connectors.achizitii.sicap import SicapConnector

        return SicapConnector()
    if source_id == "bnr":
        from connectors.opendata.bnr import BnrConnector

        return BnrConnector()
    if source_id == "legislatie":
        from connectors.legislatie.legislatie import LegislatieConnector

        return LegislatieConnector()
    if source_id == "ins_tempo":
        from connectors.opendata.ins import InsConnector

        return InsConnector()
    if source_id == "ccr":
        from connectors.audit.curteadeconturi import CurteaDeConturiConnector

        return CurteaDeConturiConnector()
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="romega")
    ap.add_argument("--source", help="source_id din config/sources.yaml")
    ap.add_argument("--list", action="store_true", help="listează toate sursele")
    ap.add_argument("--build", action="store_true", help="build gold → data/v1/*.json")
    args = ap.parse_args(argv)

    if args.build:
        from pipeline.build import build_all

        status = build_all()
        print(f"[build] {status['collections']}")
        return 0

    doc = load_sources()

    if args.list:
        for s in iter_sources(doc):
            print(f"{str(s.get('id')):22} {str(s.get('access', '-')):9} phase={s.get('phase')}  {s.get('name', '')}")
        return 0

    if not args.source:
        ap.error("--source este necesar (sau folosește --list)")

    src = find_source(doc, args.source)
    if src is None:
        print(f"sursă necunoscută: {args.source}", file=sys.stderr)
        return 2

    conn = _build_connector(args.source)
    if conn is None:
        print(
            f"[plan] {args.source}: connector neimplementat încă "
            f"(status={src.get('status')}, phase={src.get('phase')}, access={src.get('access')})"
        )
        return 0

    print(
        f"[run] {args.source}: {type(conn).__name__} pregătit. "
        f"Fetch live necesită runner self-hosted în RO (cdep.ro/senat.ro geo-blochează cloud)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
