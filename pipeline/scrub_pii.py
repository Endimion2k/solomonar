"""Gardă PII pe output-ul publicat (data/v1) — detectează și maschează date personale.

Legea 176/2010 + GDPR: CNP-uri, telefoane personale, serii CI și IBAN-uri NU se republică.
Harvesterele maschează la sursă (connectors/ani/redaction.py), dar output-ul publicat trebuie
verificat oricum înainte de commit, fiindcă zeci de scripturi scriu direct în data/v1.

    python -m pipeline.scrub_pii --check   # exit 1 dacă găsește PII → pas obligatoriu înainte de publicare
    python -m pipeline.scrub_pii           # maschează in-place, păstrând formatarea fiecărui fișier

Reguli (politica: vezi connectors/ani/redaction.py):
- câmpurile-ID (romega_id, reg_com, src/dst, …) și valorile de tip hash („g:69b8…”) nu se scanează.
- câmp CUI cu un CNP valid → null + "pf": true (persoană fizică; numele rămâne, CNP-ul nu).
- număr JSON care e un CNP valid (în afara câmpurilor-ID) → null.
- cheie de dicționar = CNP valid → „pf:<NUME>” (ca harvesterele) sau „pf-redactat-N”, fără coliziuni.
- câmpul „web” care nu e URL/domeniu (telefon, e-mail, text) → "" (e-mail/telefon = blocant).
- URL-urile nu se modifică (ar rupe linkul la sursă) — sunt doar raportate, pt. verificare manuală.
- restul textului liber → redact_text.
Raportul afișează doar fișier + cale JSON + tip, niciodată valoarea.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from connectors.ani.redaction import cnp_valid, pii_kinds, redact_text  # noqa: E402

V1 = os.path.join(ROOT, "data", "v1")

SKIP_KEYS = frozenset({
    "romega_id", "reg_com", "euid", "id", "idp", "idm", "doc_id", "hash", "sha", "sha1", "sha256",
    "key", "nume_key", "source_hash", "content_hash", "src", "dst", "source", "target",
    "source_id", "target_id", "supplier_id", "contracting_authority_id", "merged_from",
    "person_id", "institution_id", "company_id", "org_id", "entity_id", "node_id",
})
CUI_KEYS = frozenset({
    "cui", "cui_ofertant", "cui_castigator", "castigator_cui", "furnizor_cui", "cui_furnizor",
    "autoritate_cui", "cui_autoritate",
})
# acțiuni care NU blochează publicarea (nu sunt PII, sau se verifică manual)
NON_BLOCKING = ("URL", "web nevalid")

_URL = re.compile(r"^(?:https?|ftp)://", re.I)
_DOMAIN = re.compile(r"^(?:https?://)?(?:www\.)?(?:[a-z0-9-]+\.)+[a-z]{2,}(?:[/:?#].*)?$", re.I)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_HASH_ID = re.compile(r"^[a-z]{1,4}:[0-9a-f]{8,}$")
_CNP_RUN = re.compile(r"(?:(?<=CNP)|(?<=cnp)|(?<![0-9A-Za-z]))[1-8]\d{12}(?!\d)")
_PF_KEY = re.compile(r"^pf-redactat-(\d+)$")
_ESCAPES = [(chr(92) + c, " ") for c in "ntr"]      # \n \t \r din textul JSON brut


@dataclass
class Hit:
    path: str
    kind: str
    action: str


@dataclass
class FileReport:
    file: str
    hits: list[Hit] = field(default_factory=list)
    changed: bool = False
    note: str = ""
    invalid: bool = False


def _has_cnp(s: str) -> bool:
    return any(cnp_valid(m.group()) for m in _CNP_RUN.finditer(s))


def _num_is_cnp(v) -> bool:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return False
    if isinstance(v, float) and (v != v or not v.is_integer()):
        return False
    return cnp_valid(str(int(v)))


def _new_key(k: str, v, taken: set, counters: dict) -> str:
    """Cheie nouă pt. o cheie-CNP: pf:<NUME> dacă se poate, altfel pf-redactat-N; niciodată coliziune."""
    if isinstance(v, dict) and isinstance(v.get("nume"), str) and v["nume"].strip():
        cand = f"pf:{v['nume'].strip().upper()[:80]}"
        if cand not in taken:
            return cand
    n = counters.setdefault("pf_max", max((int(m.group(1)) for t in taken if (m := _PF_KEY.match(str(t)))),
                                          default=0))
    while True:
        n += 1
        cand = f"pf-redactat-{n}"
        if cand not in taken:
            counters["pf_max"] = n
            return cand


def _scrub(obj, path: str, key: str | None, hits: list[Hit], counters: dict):
    """Întoarce obiectul curățat; adaugă în `hits` ce a găsit. Nu modifică `obj` in-place."""
    lk = key.lower() if isinstance(key, str) else key
    if isinstance(obj, dict):
        out: dict = {}
        taken = set(obj.keys())
        for k, v in obj.items():
            nk = k
            if isinstance(k, str) and _has_cnp(k):
                nk = _new_key(k, v, taken | set(out.keys()), counters)
                taken.add(nk)
                hits.append(Hit(f"{path}{{cheie}}", "CNP", "cheie redenumită"))
            nv = _scrub(v, f"{path}.{nk}" if path else str(nk), k, hits, counters)
            out[nk] = nv
            if isinstance(k, str) and k.lower() in CUI_KEYS and v is not None and nv is None:
                out["pf"] = True
        return out
    if isinstance(obj, list):
        return [_scrub(v, f"{path}[{i}]", key, hits, counters) for i, v in enumerate(obj)]
    if lk in SKIP_KEYS:
        return obj
    if lk in CUI_KEYS:
        if isinstance(obj, (int, float)) and not isinstance(obj, bool):
            s = str(int(obj)) if _num_is_cnp(obj) else ""
        else:
            s = str(obj) if isinstance(obj, str) else ""
        if s and _has_cnp(s):
            hits.append(Hit(path, "CNP", "cui → null"))
            return None
        return obj
    if _num_is_cnp(obj):
        hits.append(Hit(path, "CNP", "număr → null"))
        return None
    if not isinstance(obj, str) or not obj:
        return obj
    if _HASH_ID.match(obj):
        return obj
    if lk == "web":
        s = obj.strip()
        if s and not _DOMAIN.match(s):
            personal = pii_kinds(s) or (["email"] if _EMAIL.search(s) else [])
            hits.append(Hit(path, "+".join(personal) or "-", "web → \"\"" if personal else "web nevalid → \"\""))
            return ""
        return obj
    kinds = pii_kinds(obj)
    if not kinds:
        return obj
    if _URL.match(obj.strip()):
        hits.append(Hit(path, "+".join(kinds), "URL — doar raportat"))
        return obj
    hits.append(Hit(path, "+".join(kinds), "mascat"))
    return redact_text(obj)


def _detect_format(raw: str) -> dict:
    """Parametrii json.dumps care reproduc formatarea fișierului (ca diff-ul să atingă doar valorile)."""
    bom = raw.startswith("﻿")
    body = raw[1:] if bom else raw
    nl = "\r\n" if "\r\n" in body[:2000] else "\n"
    lines = body.split(nl, 2)
    indent = None
    if len(lines) > 1 and lines[1][:1] == " ":
        indent = len(lines[1]) - len(lines[1].lstrip(" "))
    head = body[:4000]
    if indent is None:
        seps = (", ", ": ") if re.search(r'":\s', head) else (",", ":")
    else:
        seps = (",", ": ")
    ensure_ascii = "\\u" in head and not any(ord(c) > 127 for c in body[:200000])
    return {"indent": indent, "separators": seps, "ensure_ascii": ensure_ascii,
            "nl": nl, "trailing_nl": body.endswith(nl), "bom": bom}


def _dump(obj, fmt: dict) -> str:
    s = json.dumps(obj, ensure_ascii=fmt["ensure_ascii"], indent=fmt["indent"],
                   separators=fmt["separators"])
    if fmt["nl"] != "\n":
        s = s.replace("\n", fmt["nl"])
    return ("﻿" if fmt.get("bom") else "") + s + (fmt["nl"] if fmt["trailing_nl"] else "")


def _prefilter(raw: str) -> bool:
    """Superset rapid al scanării structurale: are textul brut vreun candidat PII?"""
    t = raw
    for esc, rep in _ESCAPES:
        t = t.replace(esc, rep)
    return bool(pii_kinds(t)) or '"web"' in t


def process_file(fp: str, write: bool) -> FileReport:
    rel = os.path.relpath(fp, ROOT).replace("\\", "/")
    rep = FileReport(rel)
    with open(fp, encoding="utf-8", newline="") as fh:
        raw = fh.read()
    if not _prefilter(raw):
        return rep
    counters: dict = {}
    text = raw[1:] if raw.startswith("﻿") else raw
    try:
        obj = json.loads(text)
        ndjson = False
    except json.JSONDecodeError:
        try:                         # NDJSON (ex. graf/ftm_entities.json — FollowTheMoney)
            obj = [json.loads(line) for line in text.splitlines() if line.strip()]
            ndjson = True
        except json.JSONDecodeError:
            rep.note, rep.invalid = "nu e JSON valid — nu poate fi verificat", True
            return rep
    new = _scrub(obj, "", None, rep.hits, counters)
    if not write or new == obj:
        return rep
    if ndjson:
        out = "\n".join(json.dumps(o, ensure_ascii=False, separators=(",", ":")) for o in new) + "\n"
    else:
        fmt = _detect_format(raw)
        if _dump(obj, fmt) != raw:
            rep.note = "formatarea originală nu se reproduce exact — fișierul a fost reformatat"
        out = _dump(new, fmt)
    with open(fp, "w", encoding="utf-8", newline="") as fh:
        fh.write(out)
    rep.changed = True
    return rep


def iter_files(root: str = V1):
    for dp, _, fns in os.walk(root):
        for fn in sorted(fns):
            if fn.endswith(".json") and not fn.startswith("~$"):
                yield os.path.join(dp, fn)


def scan(root: str = V1, write: bool = False) -> list[FileReport]:
    return [r for r in (process_file(fp, write) for fp in iter_files(root)) if r.hits or r.note]


def blocking_hits(reports: list[FileReport]) -> list[tuple[str, Hit]]:
    """PII care blochează publicarea + fișierele care nu pot fi verificate (JSON invalid)."""
    out = [(r.file, h) for r in reports for h in r.hits if not h.action.startswith(NON_BLOCKING)]
    out += [(r.file, Hit("", "fișier", "JSON invalid")) for r in reports if r.invalid]
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="scrub_pii", description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="doar verifică; exit 1 dacă găsește PII")
    ap.add_argument("--root", default=V1)
    args = ap.parse_args(argv)

    reports = scan(args.root, write=not args.check)
    for r in reports:
        state = "MODIFICAT" if r.changed else ("PII" if r.hits else "")
        print(f"{r.file}  [{state}] {len(r.hits)} potriviri{'  — ' + r.note if r.note else ''}")
        for h in r.hits[:25]:
            print(f"    {h.kind:18} {h.action:22} {h.path}")
        if len(r.hits) > 25:
            print(f"    … încă {len(r.hits) - 25}")
    blocking = blocking_hits(reports)
    if args.check:
        print(f"\n{'EȘEC' if blocking else 'OK'}: {len(blocking)} potriviri PII blocante în {args.root}")
        return 1 if blocking else 0
    print(f"\nScrub terminat: {sum(r.changed for r in reports)} fișiere modificate, "
          f"{sum(len(r.hits) for r in reports)} potriviri ({len(blocking)} PII).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
