"""Refresh complet SOLOMONAR — rulează pașii de colectare și construcție în ORDINEA corectă.

Până acum ordinea trăia doar în docstring-uri (docs/AUDIT-2026-09.md, F05/F16). Aici e explicită:

  surse    — colectări rapide (parlament, comisii, DNA, legislație, partide, bugete, BVB, catalog SICAP)
  mari     — colectări lungi (achiziții directe ~22M rânduri, red-flags, ONRC, bilanțuri) — ore
  derivate — gold → splink → ANI → sancțiuni/guvernanță → grafuri → DuckDB → rețele → alerte → căutare
  final    — stats/status, mascare PII, gărzi: 0 PII și niciun fișier > 90 MiB

Declarațiile de avere/interese (OCR, ~o zi de GPU) NU sunt incluse — pas separat, la cerere.

    python -m pipeline.refresh --list
    python -m pipeline.refresh --groups surse
    python -m pipeline.refresh --from gold            # reia de la un pas
    python -m pipeline.refresh --only dna,feeds
    python -m pipeline.refresh --groups mari --continue-on-error

Log-urile fiecărui pas: _local/refresh/<timestamp>/<pas>.log (ne-versionat).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V = os.path.join(ROOT, "data", "v1")
MAX_MIB = 90

# (id, grup, argumente după `python`, variabile de mediu, notă)
STEPS: list[tuple[str, str, list[str], dict, str]] = [
    ("parlament", "surse", ["-m", "pipeline.build_parlament"], {}, "deputați + senatori (cdep.ro/senat.ro)"),
    ("motiuni", "surse", ["-m", "pipeline.harvest_motiuni"], {}, "moțiuni CDep"),
    ("comisii", "surse", ["-m", "pipeline.harvest_comisii"], {"SOLOMONAR_COMISII_FRESH": "1"}, "ședințe + PLx"),
    ("comisii_senat", "surse", ["-m", "pipeline.harvest_comisii_senat"], {}, "componența comisiilor Senatului"),
    ("plx_initiatori", "surse", ["-m", "pipeline.harvest_plx_initiatori"], {}, "inițiatorii PLx"),
    ("comisii_recent", "surse", ["-m", "pipeline.build_comisii_recent"], {}, "activitatea din ultima lună"),
    ("dna", "surse", ["-m", "pipeline.harvest_dna"], {}, "comunicate DNA (+ re-parsare versiuni EN)"),
    ("legislatie", "surse", ["-m", "pipeline.harvest_legislatie_full"], {}, "legislație (bounded)"),
    ("subventii", "surse", ["-m", "pipeline.harvest_subventii_partide"], {}, "subvenții partide (Playwright)"),
    ("rvc", "surse", ["-m", "pipeline.harvest_rvc_partide"], {}, "rapoarte financiare partide"),
    ("partide", "surse", ["-m", "pipeline.build_partide"], {}, "entitatea PARTID"),
    ("bgc", "surse", ["-m", "pipeline.harvest_bgc"], {}, "bugetul general consolidat (lunar)"),
    ("bugete_uat", "surse", ["-m", "pipeline.harvest_bugete_uat"], {}, "bugete UAT"),
    ("curtea_conturi", "surse", ["-m", "pipeline.harvest_curteadeconturi"], {}, "rapoarte Curtea de Conturi"),
    ("bvb", "surse", ["-m", "pipeline.harvest_actionariat_bvb"], {}, "acționariat SOE listate"),
    ("sicap_map", "surse", ["-m", "pipeline.build_achizitii_map"], {}, "catalog SICAP data.gov.ro"),

    ("achizitii_directe", "mari", ["-m", "pipeline.harvest_achizitii_directe"], {}, "~22M rânduri, checkpoint"),
    ("redflags", "mari", ["-m", "pipeline.harvest_redflags"], {}, "single-bid / fragmentare, ore"),
    ("reprezentanti", "mari", ["-m", "pipeline.enrich_reprezentanti"], {}, "reprezentanți legali ONRC"),
    ("firme_onrc", "mari", ["-m", "pipeline.harvest_firme_onrc"], {}, "profil ONRC firme cu bani publici"),
    ("bilanturi", "mari", ["-m", "pipeline.enrich_financials", "2025"], {}, "bilanțuri MF 2025"),
    ("bilanturi_trend", "mari", ["-m", "pipeline.enrich_financials", "trend"], {}, "serii multi-an"),

    ("gold", "derivate", ["-m", "pipeline.build_gold"], {}, "rezoluție canonică persoane"),
    ("splink_apply", "derivate", ["-m", "pipeline.build_splink_apply"], {}, "merge-uri sigure Splink"),
    ("ani_integrate", "derivate", ["-m", "pipeline.build_ani_integrate"], {}, "metadate ANI central"),
    ("opensanctions", "derivate", ["-m", "pipeline.harvest_opensanctions"], {}, "cross-ref sancțiuni/PEP"),
    ("guvernanta", "derivate", ["-m", "pipeline.harvest_guvernanta"], {}, "registrul guvernanta.gov.ro"),
    ("dna_cross", "derivate", ["-m", "pipeline.build_dna_cross"], {}, "DNA ↔ graf"),
    ("graph_full", "derivate", ["-m", "pipeline.build_graph_full"], {}, "graf complet"),
    ("graph_layout", "derivate", ["-m", "pipeline.build_graph_layout"], {}, "layout graf"),
    ("duckdb", "derivate", ["-m", "pipeline.build_duckdb"], {}, "gold relațional + analytics/*"),
    ("network", "derivate", ["-m", "pipeline.build_network"], {}, "inele / hub-uri / poduri"),
    ("alerte", "derivate", ["-m", "pipeline.build_alerte"], {}, "semnale"),
    ("avere_anomalii", "derivate", ["-m", "pipeline.build_avere_anomalii"], {}, "anomalii de avere"),
    ("coverage", "derivate", ["-m", "pipeline.build_coverage"], {}, "raport de acoperire"),
    ("search", "derivate", ["-m", "pipeline.build_search"], {}, "index de căutare"),
    ("feeds", "derivate", ["-m", "pipeline.build_feeds"], {}, "feed-uri DNA/alerte"),
    ("changelog", "derivate", ["-m", "pipeline.build_changelog"], {}, "diff față de ultimul refresh"),

    ("stats", "final", ["-m", "pipeline.build_stats"], {}, "stats.json + status.json"),
    ("pii_scrub", "final", ["-m", "pipeline.scrub_pii"], {}, "mascare PII în data/v1"),
    ("pii_check", "final", ["-m", "pipeline.scrub_pii", "--check"], {}, "GARDĂ: 0 PII"),
]
GROUPS = ["surse", "mari", "derivate", "final"]


def _size_gate() -> list[str]:
    big = []
    for dp, _, fs in os.walk(V):
        for f in fs:
            p = os.path.join(dp, f)
            if os.path.getsize(p) > MAX_MIB * 1024 * 1024:
                big.append(f"{os.path.relpath(p, ROOT)} ({os.path.getsize(p) / 1048576:.1f} MiB)")
    return big


def _json_gate() -> list[str]:
    bad = []
    for dp, _, fs in os.walk(V):
        for f in fs:
            if f.endswith(".json") and not f.startswith("~$"):
                p = os.path.join(dp, f)
                try:
                    with open(p, encoding="utf-8") as fh:
                        json.load(fh)
                except json.JSONDecodeError:
                    with open(p, encoding="utf-8") as fh:        # NDJSON (ex. ftm_entities) e acceptat
                        try:
                            [json.loads(x) for x in fh if x.strip()]
                        except json.JSONDecodeError:
                            bad.append(os.path.relpath(p, ROOT))
    return bad


def select(args) -> list[tuple]:
    steps = [s for s in STEPS if s[1] in args.groups]
    if args.only:
        want = set(args.only.split(","))
        unknown = want - {s[0] for s in STEPS}
        if unknown:
            raise SystemExit(f"pași necunoscuți: {sorted(unknown)}")
        steps = [s for s in STEPS if s[0] in want]
    if args.from_step:
        ids = [s[0] for s in STEPS]
        if args.from_step not in ids:
            raise SystemExit(f"pas necunoscut: {args.from_step}")
        start = ids.index(args.from_step)
        steps = [s for s in steps if ids.index(s[0]) >= start]
    return steps


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="refresh", description=__doc__.splitlines()[0])
    ap.add_argument("--groups", default=",".join(GROUPS), type=lambda s: s.split(","))
    ap.add_argument("--only", help="doar acești pași (id-uri separate prin virgulă)")
    ap.add_argument("--from", dest="from_step", help="reia de la acest pas")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--continue-on-error", action="store_true")
    args = ap.parse_args(argv)

    if args.list:
        for sid, grp, cmd, env, note in STEPS:
            print(f"{grp:9} {sid:18} {' '.join(cmd[1:]):42} {note}")
        return 0
    steps = select(args)
    logdir = os.path.join(ROOT, "_local", "refresh", datetime.now().strftime("%Y%m%d-%H%M%S"))
    os.makedirs(logdir, exist_ok=True)
    print(f"refresh: {len(steps)} pași | log-uri în {os.path.relpath(logdir, ROOT)}", flush=True)
    results = []
    for sid, grp, cmd, env, note in steps:
        line = f"[{grp}] {sid:18} {note}"
        if args.dry_run:
            print("  (dry-run)", line, flush=True)
            continue
        print(f"▶ {line}", flush=True)
        t0 = time.time()
        with open(os.path.join(logdir, f"{sid}.log"), "w", encoding="utf-8") as log:
            rc = subprocess.run([sys.executable, *cmd], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1",
                                     **env}).returncode
        dt = time.time() - t0
        tail = ""
        try:
            with open(os.path.join(logdir, f"{sid}.log"), encoding="utf-8", errors="replace") as log:
                tail = [x.strip() for x in log.read().splitlines() if x.strip()][-1][:160]
        except (OSError, IndexError):
            pass
        results.append((sid, rc, dt))
        print(f"  {'OK ' if rc == 0 else 'EȘEC'} {sid} ({dt / 60:.1f} min) — {tail}", flush=True)
        if rc != 0 and not args.continue_on_error:
            print(f"OPRIT la {sid} (log: {os.path.relpath(logdir, ROOT)}/{sid}.log). "
                  f"Reia cu: python -m pipeline.refresh --from {sid}", flush=True)
            return 1
    if args.dry_run:
        return 0
    failed = [r for r in results if r[1] != 0]
    problems = []
    if any(s[1] == "final" for s in steps) or not args.only:
        big, bad = _size_gate(), _json_gate()
        problems += [f"fișier > {MAX_MIB} MiB: {b}" for b in big] + [f"JSON invalid: {b}" for b in bad]
    print(f"\nREZUMAT: {len(results) - len(failed)}/{len(results)} pași OK, "
          f"{sum(r[2] for r in results) / 60:.0f} min" + (f" | EȘUATE: {[r[0] for r in failed]}" if failed else ""))
    for p in problems:
        print("  GARDĂ:", p)
    return 1 if failed or problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
