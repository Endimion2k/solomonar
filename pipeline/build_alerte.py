"""Construiește ALERTE / semnale de interes din datele SOLOMONAR (data/v1/alerte.json).

Inspirat de cdep-alerts, dar pe datele noastre: reguli DETERMINISTE, fiecare cu
severitate + titlu + explicație + provenance (sursa exactă din care a rezultat semnalul).

Reguli:
  (1) CONFLICT CONFIRMAT  — persoană cu firmă în PROPRIA declarație de interese
      care a câștigat contracte (follow_the_money.confirmate). Severitate MARE.
  (2) PARLAMENTAR -> SOE  — parlamentar care conduce o companie de stat.
  (3) SOE PIERDERE+CONTRACTE — companie de stat cu profit net negativ dar contracte mari.
  (4) OUTLIER CONTRACTE   — firmă cu contracte foarte mari raportat la nr. de contracte
      (posibil acord-cadru / valoare cumulată — de verificat).
  (5) CONCENTRARE PERSOANĂ — persoană în >3 companii.
  (6) PARTID SUBVENȚIE 0 PARLAMENTARI — partid cu subvenție mare dar 0 deputați+senatori.

⚠️ DISCLAIMER: acestea sunt SEMNALE DE INTERES, nu acuzații. Legăturile firmă↔persoană
sunt în mare parte pe NUME (fără CNP) => pot fi OMONIMI. Singurele defensabile sunt cele
din declarația de interese PROPRIE (regula 1). Restul = de verificat manual (ONRC + declarații).

Output: data/v1/alerte.json -> {disclaimer, generat, total, pe_severitate, pe_tip, alerte:[...]}
Fiecare alertă: {tip, severitate, scor, titlu, entitate, detalii, provenance}.
Sortat descrescător pe scor de severitate.
"""

from __future__ import annotations

import datetime
import json
import os

try:
    import duckdb
except Exception:  # pragma: no cover
    duckdb = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V = os.path.join(ROOT, "data/v1")
DB = os.path.join(ROOT, "data/gold/solomonar.duckdb")

# ---- praguri (constante, fără magic numbers în logică) ----
PRAG_OUTLIER_AVG_RON = 50_000_000      # valoare medie / contract peste care e outlier
PRAG_OUTLIER_TOTAL_RON = 100_000_000   # plus total contracte minim pt. a conta ca outlier
PRAG_SOE_CONTRACTE_RON = 5_000_000     # contracte minime pt. regula 3 (SOE pe pierdere)
PRAG_CONCENTRARE_COMPANII = 3          # >3 companii = concentrare
PRAG_PARTID_SUBVENTIE_LEI = 1_000_000  # subvenție istorică mare pt. regula 6

# ordinea severităților -> scor numeric (folosit la sortare)
SEV_SCOR = {"mare": 3, "medie": 2, "mica": 1}

# roluri considerate "de conducere / control" pentru regula 2
ROLURI_CONDUCERE = (
    "administrator",
    "director",
    "presedinte",
    "membru in consiliul",
    "membru in directorat",
    "reprezentant",
)


def _load(p):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return {}


def _nume(s: str) -> str:
    return (s or "").strip().title()


def _e_rol_conducere(rol: str) -> bool:
    r = (rol or "").lower()
    return any(k in r for k in ROLURI_CONDUCERE)


def _build_cui_financials(persoane: list) -> dict:
    """Hartă cui -> financials (profit_net etc.). DuckDB are profit_ron NULL,
    datele financiare reale sunt în companii[].financials din persoane_gold.json."""
    out: dict = {}
    for pr in persoane:
        for c in pr.get("companii", []) or []:
            fin = c.get("financials")
            cui = c.get("cui")
            if cui and fin and fin.get("profit_net") is not None and cui not in out:
                out[cui] = fin
    return out


# =========================================================================
# REGULA 1 — CONFLICT CONFIRMAT (din follow_the_money.confirmate)
# =========================================================================
def regula1_conflict_confirmat(fm: dict) -> list:
    alerte = []
    for c in fm.get("confirmate", []) or []:
        firme = c.get("firme_contracte_autodeclarate", []) or []
        if not firme:
            continue
        total = sum(f.get("total_ron") or 0 for f in firme)
        e_parl = bool(c.get("parlamentar"))
        # severitate mare; high dacă e și parlamentar (provenance de încredere mai mare)
        sev = "mare"
        firme_str = ", ".join(f.get("nume", "?") for f in firme)
        alerte.append({
            "tip": "conflict_confirmat",
            "severitate": sev,
            "titlu": f"Conflict documentat: {_nume(c.get('nume_key'))} are în declarația de interese firmă cu contracte de stat",
            "entitate": _nume(c.get("nume_key")),
            "detalii": {
                "romega_id": c.get("romega_id"),
                "este_parlamentar": e_parl,
                "incredere_link": c.get("incredere"),
                "firme": [{"cui": f.get("cui"), "nume": f.get("nume"), "total_ron": f.get("total_ron")} for f in firme],
                "total_contracte_ron": total,
                "n_declaratii": c.get("n_declaratii"),
            },
            "provenance": "data/v1/graf/follow_the_money.json#confirmate (firmă apare în PROPRIA declarație de interese a persoanei -> conflict documentat)",
        })
    return alerte


# =========================================================================
# REGULA 2 — PARLAMENTAR conduce SOE
# =========================================================================
def regula2_parlamentar_soe(con) -> list:
    alerte = []
    rows = con.execute(
        """
        SELECT p.romega_id, p.nume, p.camera, p.partid,
               c.cui, c.nume AS firma, pc.rol, c.tutela, c.procent_stat
        FROM person p
        JOIN person_company pc ON p.romega_id = pc.romega_id
        JOIN company c ON pc.cui = c.cui
        WHERE p.camera IS NOT NULL AND p.camera <> ''
          AND c.is_soe = TRUE
        """
    ).fetchall()
    for rid, nume, camera, partid, cui, firma, rol, tutela, ps in rows:
        if not _e_rol_conducere(rol):
            continue
        alerte.append({
            "tip": "parlamentar_conduce_soe",
            "severitate": "medie",
            "titlu": f"Parlamentar la conducerea unei companii de stat: {_nume(nume)} ({rol}) la {firma}",
            "entitate": _nume(nume),
            "detalii": {
                "romega_id": rid,
                "camera": camera,
                "partid": partid,
                "firma": firma,
                "cui": cui,
                "rol": rol,
                "tutela": tutela or None,
                "procent_stat": ps,
            },
            "provenance": "solomonar.duckdb: person(camera) JOIN person_company(rol) JOIN company(is_soe=TRUE)",
        })
    return alerte


# =========================================================================
# REGULA 3 — SOE cu profit negativ dar contracte mari
# =========================================================================
def regula3_soe_pierdere_contracte(con, cui_fin: dict) -> list:
    alerte = []
    rows = con.execute(
        "SELECT cui, nume, contracte_ron, contracte_nr, tutela FROM company "
        "WHERE is_soe = TRUE AND contracte_ron > 0"
    ).fetchall()
    for cui, nume, ctr, nr, tutela in rows:
        fin = cui_fin.get(cui)
        if not fin:
            continue
        profit = fin.get("profit_net")
        if profit is None or profit >= 0:
            continue
        if (ctr or 0) < PRAG_SOE_CONTRACTE_RON:
            continue
        alerte.append({
            "tip": "soe_pierdere_contracte_mari",
            "severitate": "medie",
            "titlu": f"Companie de stat pe pierdere cu contracte mari: {nume}",
            "entitate": nume,
            "detalii": {
                "cui": cui,
                "profit_net_ron": profit,
                "cifra_afaceri_ron": fin.get("cifra_afaceri"),
                "an_financiar": fin.get("an"),
                "contracte_ron": ctr,
                "contracte_nr": nr,
                "tutela": tutela or None,
            },
            "provenance": "solomonar.duckdb company(is_soe,contracte_ron) + financials.profit_net din persoane_gold.json",
        })
    return alerte


# =========================================================================
# REGULA 4 — outlier valoare/contract (posibil acord-cadru / cumul)
# =========================================================================
def regula4_outlier_contracte(con) -> list:
    alerte = []
    rows = con.execute(
        "SELECT cui, nume, contracte_ron, contracte_nr, tutela FROM company "
        "WHERE contracte_ron > 0 AND contracte_nr > 0"
    ).fetchall()
    for cui, nume, ctr, nr, tutela in rows:
        avg = ctr / nr if nr else 0
        if avg < PRAG_OUTLIER_AVG_RON or ctr < PRAG_OUTLIER_TOTAL_RON:
            continue
        alerte.append({
            "tip": "outlier_valoare_contract",
            "severitate": "mica",
            "titlu": f"Valoare medie/contract foarte mare (de verificat): {nume}",
            "entitate": nume,
            "detalii": {
                "cui": cui,
                "contracte_ron": ctr,
                "contracte_nr": nr,
                "valoare_medie_ron": round(avg, 2),
                "tutela": tutela or None,
                "nota": "Valoare medie mare pe contract poate indica acord-cadru, valoare cumulată multianuală sau un singur contract major — de verificat în SICAP.",
            },
            "provenance": "solomonar.duckdb company(contracte_ron/contracte_nr)",
        })
    return alerte


# =========================================================================
# REGULA 5 — concentrare: persoană în >3 companii
# =========================================================================
def regula5_concentrare_persoana(con) -> list:
    alerte = []
    rows = con.execute(
        """
        SELECT pc.romega_id, p.nume, p.camera, p.partid, count(DISTINCT pc.cui) AS n
        FROM person_company pc
        JOIN person p ON p.romega_id = pc.romega_id
        GROUP BY 1, 2, 3, 4
        HAVING count(DISTINCT pc.cui) > ?
        ORDER BY n DESC
        """,
        [PRAG_CONCENTRARE_COMPANII],
    ).fetchall()
    for rid, nume, camera, partid, n in rows:
        firme = con.execute(
            "SELECT c.cui, c.nume, pc.rol FROM person_company pc "
            "JOIN company c ON pc.cui = c.cui WHERE pc.romega_id = ?",
            [rid],
        ).fetchall()
        alerte.append({
            "tip": "concentrare_persoana",
            "severitate": "mica",
            "titlu": f"Persoană prezentă în {n} companii: {_nume(nume)}",
            "entitate": _nume(nume),
            "detalii": {
                "romega_id": rid,
                "camera": camera,
                "partid": partid,
                "n_companii": n,
                "firme": [{"cui": c[0], "nume": c[1], "rol": c[2]} for c in firme],
            },
            "provenance": "solomonar.duckdb person_company GROUP BY romega_id HAVING count>3",
        })
    return alerte


# =========================================================================
# REGULA 6 — partid cu subvenție mare dar 0 parlamentari (istoric)
# =========================================================================
def regula6_partid_subventie_fara_parlamentari(con) -> list:
    alerte = []
    rows = con.execute(
        "SELECT cod, subventie_lei, nr_deputati, nr_senatori, nr_rvc FROM party "
        "WHERE subventie_lei > ? AND (COALESCE(nr_deputati,0) + COALESCE(nr_senatori,0)) = 0 "
        "ORDER BY subventie_lei DESC",
        [PRAG_PARTID_SUBVENTIE_LEI],
    ).fetchall()
    for cod, sub, nd, ns, nrvc in rows:
        alerte.append({
            "tip": "partid_subventie_fara_parlamentari",
            "severitate": "medie",
            "titlu": f"Partid cu subvenție mare dar 0 parlamentari în mandatul curent: {cod}",
            "entitate": cod,
            "detalii": {
                "cod": cod,
                "subventie_lei": sub,
                "nr_deputati": nd,
                "nr_senatori": ns,
                "nr_rvc": nrvc,
                "nota": "Subvenția poate fi istorică/cumulată; 0 deputați+senatori în mandatul curent. De corelat cu legislatura.",
            },
            "provenance": "solomonar.duckdb party(subventie_lei, nr_deputati, nr_senatori)",
        })
    return alerte


DISCLAIMER = (
    "⚠️ SEMNALE DE INTERES, NU ACUZAȚII. Aceste alerte sunt generate automat din date "
    "deschise prin reguli deterministe. Legăturile firmă↔persoană sunt în mare parte pe NUME "
    "(fără CNP) => candidații pe nume pot fi OMONIMI, mai ales la companii mari. Singurele "
    "defensabile fără verificare suplimentară sunt cele de tip 'conflict_confirmat' (firma apare "
    "în PROPRIA declarație de interese). Restul necesită verificare manuală (ONRC + declarații de "
    "interese + SICAP). Cifrele de contracte pot fi cumulate multianual."
)


def regula7_firma_noua_bani_stat(firme: list) -> list:
    """Firme nou-înființate (≤1 an înainte) care au luat CONTRACTE de stat — posibile firme-paravan.

    Doar canalul contracte (mai mare); cele doar cu achiziții directe mici rămân ca agregat în sumar
    (vezi meta), ca să nu îneace alertele de conflict de mare valoare.
    """
    alerte = []
    for f in firme:
        if not any("nou" in str(x).lower() for x in (f.get("flaguri") or [])):
            continue
        if not f.get("are_contracte"):     # doar contracte (nu achiziții directe mici)
            continue
        canal = "contracte"
        alerte.append({
            "tip": "firma_noua_bani_stat", "severitate": "medie",
            "titlu": f"Firmă nou-înființată ({f.get('an_infiintare', '?')}) cu bani de stat — {f.get('forma_juridica', '')} {f.get('judet', '')}".strip(),
            "entitate": {"cui": f.get("cui"), "forma_juridica": f.get("forma_juridica"),
                         "an_infiintare": f.get("an_infiintare"), "caen": f.get("caen_domeniu")},
            "detalii": {"canal": canal, "an_infiintare": f.get("an_infiintare")},
            "provenance": "ONRC OD_FIRME (an înființare) × SICAP — LEAD, nu probă (poate fi firmă tânără legitimă)"})
    return alerte


def regula8_firma_mama_straina(firme: list) -> list:
    """Firme cu firmă-mamă în alt stat, care iau bani de stat."""
    alerte = []
    for f in firme:
        if f.get("tara_mama") and (f.get("are_contracte") or f.get("are_achizitii_directe")):
            alerte.append({
                "tip": "firma_mama_straina", "severitate": "mica",
                "titlu": f"Firmă cu mamă în {f.get('tara_mama')} cu bani de stat — CUI {f.get('cui')}",
                "entitate": {"cui": f.get("cui"), "tara_mama": f.get("tara_mama")},
                "detalii": {"tara_mama": f.get("tara_mama")},
                "provenance": "ONRC firmă-mamă × SICAP — context, nu neregulă"})
    return alerte


def main() -> dict:
    if duckdb is None:
        raise RuntimeError("duckdb nu este instalat")

    fm = _load(os.path.join(V, "graf/follow_the_money.json"))
    gold = _load(os.path.join(V, "graf/persoane_gold.json"))
    persoane = gold.get("persoane", []) if isinstance(gold, dict) else []
    cui_fin = _build_cui_financials(persoane)
    firme = _load(os.path.join(V, "companii/firme_onrc.json")).get("firme", [])

    con = duckdb.connect(DB, read_only=True)
    try:
        alerte = []
        alerte += regula1_conflict_confirmat(fm)
        alerte += regula2_parlamentar_soe(con)
        alerte += regula3_soe_pierdere_contracte(con, cui_fin)
        alerte += regula4_outlier_contracte(con)
        alerte += regula5_concentrare_persoana(con)
        alerte += regula6_partid_subventie_fara_parlamentari(con)
        alerte += regula7_firma_noua_bani_stat(firme)
        alerte += regula8_firma_mama_straina(firme)
    finally:
        con.close()

    # scor numeric + sortare descrescătoare (severitate, apoi total contracte dacă există)
    for a in alerte:
        a["scor"] = SEV_SCOR.get(a["severitate"], 0)

    def _sort_key(a):
        det = a.get("detalii", {})
        bani = (
            det.get("total_contracte_ron")
            or det.get("contracte_ron")
            or det.get("subventie_lei")
            or det.get("n_companii")
            or 0
        )
        return (a["scor"], bani)

    alerte.sort(key=_sort_key, reverse=True)

    pe_sev: dict = {}
    pe_tip: dict = {}
    for a in alerte:
        pe_sev[a["severitate"]] = pe_sev.get(a["severitate"], 0) + 1
        pe_tip[a["tip"]] = pe_tip.get(a["tip"], 0) + 1

    # agregate (semnale prea voluminoase pt. listă individuală)
    noi_total = sum(1 for f in firme if any("nou" in str(x).lower() for x in (f.get("flaguri") or [])))
    noi_directe = sum(1 for f in firme
                      if any("nou" in str(x).lower() for x in (f.get("flaguri") or []))
                      and f.get("are_achizitii_directe") and not f.get("are_contracte"))
    out = {
        "disclaimer": DISCLAIMER,
        "generat": datetime.date.today().isoformat(),
        "total": len(alerte),
        "pe_severitate": pe_sev,
        "pe_tip": pe_tip,
        "agregate": {
            "firme_noi_cu_bani_stat_total": noi_total,
            "firme_noi_doar_achizitii_directe": noi_directe,
            "nota_agregat": "Firmele noi cu doar achiziții directe mici NU sunt listate individual "
                            "(prea multe); doar cele cu contracte. Vezi firme_onrc.json pentru toate.",
        },
        "alerte": alerte,
    }

    outp = os.path.join(V, "alerte.json")
    with open(outp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    return out


if __name__ == "__main__":
    res = main()
    print(f"OK -> data/v1/alerte.json | total alerte: {res['total']}")
    print("pe severitate:", res["pe_severitate"])
    print("pe tip:", res["pe_tip"])
    print()
    print("=== TOP 10 ALERTE ===")
    for i, a in enumerate(res["alerte"][:10], 1):
        print(f"{i:2}. [{a['severitate'].upper():5}] ({a['tip']}) {a['titlu']}")
