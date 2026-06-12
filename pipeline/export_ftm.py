"""Export ROMEGA → FollowTheMoney (OCCRP / Aleph) entity stream.

Produce a newline-delimited stream of FtM entities (one JSON object per line)
aligned with the real FollowTheMoney vocabulary (https://followthemoney.tech).

Entities emitted:
  - Person       : parlamentari + reprezentanți legali (din DuckDB `person`)
  - Company      : companii de stat / firme conduse (din DuckDB `company`)
  - PublicBody   : "Statul Român" (proprietar pentru holding-urile de stat)
  - Organization : partide politice (din DuckDB `party`)

Edges (interval/interest schemas — fiecare e o entitate de sine stătătoare,
cu source/target = referințe la id-urile entităților):
  - Directorship : person → company   (din `person_company`, rol = funcția)
  - Ownership    : Statul Român → company (din `company.procent_stat` > 0)
  - Membership   : person → party      (din `person.partid`, mapat la cod)

Format de ieșire (Aleph "entity stream"):
    {"id": "...", "schema": "Person", "properties": {"name": ["..."], ...}}

Fiecare proprietate FtM e o LISTĂ (multi-valued) — convenția FtM.
Output: data/v1/graf/ftm_entities.json (NDJSON — o entitate pe linie).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata

import duckdb

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DUCKDB = os.path.join(ROOT, "data/gold/romega.duckdb")
OUT = os.path.join(ROOT, "data/v1/graf/ftm_entities.json")

# Identitatea statului ca proprietar (un singur nod PublicBody).
STATE_ID = "ro-statul-roman"

# Maparea text-liber `person.partid` → cod partid din tabela `party`.
# Acoperă și formele "Grupul parlamentar al ..." și variantele diacritice.
PARTY_PATTERNS = {
    "PSD": ["social democrat", "psd"],
    "PNL": ["national liberal", "naţional liberal", "pnl"],
    "USR": ["salvati romania", "salvaţi românia", "usr"],
    "AUR": ["unirea romanilor", "unirea românilor", "aur"],
    "UDMR": ["maghiara", "maghiară", "udmr", "rmdsz"],
    "SOS": ["s.o.s", "sos romania", "sos românia"],
    "POT": ["oamenilor tineri", "pot"],
    "PMP": ["miscarea populara", "mişcarea populară", "pmp"],
    "ALDE": ["alde"],
}


def _slug(s: str) -> str:
    """Slug ASCII pentru id-uri FtM stabile."""
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "x"


def _hid(prefix: str, *parts: object) -> str:
    """Id determinist pentru edge-uri (hash stabil al componentelor)."""
    raw = "|".join(str(p) for p in parts)
    return f"{prefix}-{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:16]}"


def _ent(eid: str, schema: str, props: dict) -> dict:
    """Construiește o entitate FtM: fiecare valoare devine listă, golurile cad."""
    clean = {}
    for k, v in props.items():
        if v is None or v == "" or v == []:
            continue
        clean[k] = v if isinstance(v, list) else [str(v)]
    return {"id": eid, "schema": schema, "properties": clean}


def _party_code(partid: str | None) -> str | None:
    if not partid:
        return None
    n = unicodedata.normalize("NFKD", partid).encode("ascii", "ignore").decode().lower()
    for code, pats in PARTY_PATTERNS.items():
        if any(p in n for p in pats):
            return code
    return None


def main() -> dict:
    con = duckdb.connect(DUCKDB, read_only=True)

    persons = con.execute(
        "SELECT romega_id, nume, birth_date, incredere, n_declaratii, n_companii, "
        "total_contracte_ron, camera, partid, judet FROM person"
    ).fetchall()
    companies = con.execute(
        "SELECT cui, nume, sector, tutela, judet, bvb, is_soe, ca_ron, profit_ron, "
        "salariati, procent_stat, contracte_ron, contracte_nr FROM company"
    ).fetchall()
    pc = con.execute("SELECT romega_id, cui, rol FROM person_company").fetchall()
    parties = con.execute(
        "SELECT cod, subventie_lei, nr_deputati, nr_senatori, nr_rvc FROM party"
    ).fetchall()
    con.close()

    # CUI-urile prezente în tabela company (ca să emitem doar edge-uri cu target valid
    # și să marcăm care persoane chiar au legături — restul de 56k rămân pe dinafară).
    company_cuis = {c[0] for c in companies}
    # romega_id-urile care apar într-o relație person_company (cu o companie cunoscută).
    linked_persons = {r[0] for r in pc if r[1] in company_cuis}
    # romega_id-uri membre de partid (pt. a le emite chiar dacă n-au companii).
    party_persons = {p[0] for p in persons if _party_code(p[8])}

    emit_persons = linked_persons | party_persons

    entities: list[dict] = []

    # ---- Person ----
    pidx = {p[0]: p for p in persons}
    for rid in sorted(emit_persons):
        p = pidx.get(rid)
        if not p:
            continue
        (romega_id, nume, birth_date, incredere, n_decl, n_comp,
         contracte, camera, partid, judet) = p
        desc = []
        if camera:
            desc.append(camera)
        if partid:
            desc.append(partid)
        entities.append(_ent(
            f"ro-person-{_slug(romega_id)}", "Person",
            {
                "name": nume,
                "birthDate": birth_date,
                "country": "ro",
                "nationality": "ro",
                "description": " · ".join(desc) if desc else None,
                # 'keywords' e multi-valued în FtM — stocăm nivelul de încredere al rezoluției.
                "keywords": [f"incredere:{incredere}"] if incredere else None,
            },
        ))

    # ---- Company ----
    for c in companies:
        (cui, nume, sector, tutela, judet, bvb, is_soe, ca_ron, profit_ron,
         salariati, procent_stat, contracte_ron, contracte_nr) = c
        status = "companie de stat" if is_soe else None
        entities.append(_ent(
            f"ro-company-{cui}", "Company",
            {
                "name": nume,
                "registrationNumber": str(cui),
                "jurisdiction": "ro",
                "sector": sector,
                "status": status,
                "classification": "BVB-listed" if bvb else None,
            },
        ))

    # ---- PublicBody: Statul Român (proprietar) ----
    entities.append(_ent(
        STATE_ID, "PublicBody",
        {"name": "Statul Român", "jurisdiction": "ro", "country": "ro"},
    ))

    # ---- Organization: partide ----
    for cod, subventie, ndep, nsen, nrvc in parties:
        entities.append(_ent(
            f"ro-party-{_slug(cod)}", "Organization",
            {
                "name": cod,
                "legalForm": "partid politic",
                "country": "ro",
                "keywords": [f"subventie_lei:{subventie:.0f}"] if subventie else None,
            },
        ))

    # ---- Directorship edges (person → company) ----
    n_dir = 0
    seen_dir = set()
    for romega_id, cui, rol in pc:
        if cui not in company_cuis or romega_id not in pidx:
            continue
        key = (romega_id, cui, rol)
        if key in seen_dir:
            continue
        seen_dir.add(key)
        entities.append(_ent(
            _hid("ro-dir", romega_id, cui, rol), "Directorship",
            {
                "director": f"ro-person-{_slug(romega_id)}",
                "organization": f"ro-company-{cui}",
                "role": rol,
            },
        ))
        n_dir += 1

    # ---- Ownership edges (Statul Român → company), pe procent_stat ----
    n_own = 0
    for c in companies:
        cui, nume, procent_stat = c[0], c[1], c[10]
        if procent_stat is None or procent_stat <= 0:
            continue
        entities.append(_ent(
            _hid("ro-own", STATE_ID, cui), "Ownership",
            {
                "owner": STATE_ID,
                "asset": f"ro-company-{cui}",
                "percentage": f"{procent_stat:.4f}",
                "role": "shareholder",
            },
        ))
        n_own += 1

    # ---- Membership edges (person → party) ----
    n_mem = 0
    party_codes = {p[0] for p in parties}
    for p in persons:
        romega_id, partid = p[0], p[8]
        code = _party_code(partid)
        if not code or code not in party_codes or romega_id not in emit_persons:
            continue
        entities.append(_ent(
            _hid("ro-mem", romega_id, code), "Membership",
            {
                "member": f"ro-person-{_slug(romega_id)}",
                "organization": f"ro-party-{_slug(code)}",
            },
        ))
        n_mem += 1

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        for e in entities:
            f.write(json.dumps(e, ensure_ascii=False))
            f.write("\n")

    by_schema: dict[str, int] = {}
    for e in entities:
        by_schema[e["schema"]] = by_schema.get(e["schema"], 0) + 1

    print(f"PUBLICAT FtM: {len(entities)} entități → {os.path.relpath(OUT, ROOT)}")
    for s in sorted(by_schema):
        print(f"  {s:14s}: {by_schema[s]}")
    print(f"  edges → Directorship={n_dir} Ownership={n_own} Membership={n_mem}")
    return {"total": len(entities), "by_schema": by_schema}


if __name__ == "__main__":
    main()
