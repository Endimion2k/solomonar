"""Data-layer SOLOMONAR pentru clientul Streamlit — citește JSON-urile statice din data/v1 (cache).

Sursa = data/v1 local (sau SOLOMONAR_DATA = director / URL bază GitHub Pages). Funcțiile întorc
DataFrame-uri/dict-uri memoizate (@st.cache_data). Contractul stabil folosit de toate paginile.
"""

from __future__ import annotations

import collections
import json
import os
import re
from functools import lru_cache

import pandas as pd
import streamlit as st

_HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("SOLOMONAR_DATA") or os.path.normpath(os.path.join(_HERE, "..", "..", "data", "v1"))
LIVE = DATA.startswith("http")


def _read(rel: str):
    if LIVE:
        import urllib.request
        with urllib.request.urlopen(f"{DATA.rstrip('/')}/{rel}", timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    p = os.path.join(DATA, rel.replace("/", os.sep))
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


_load_raw = lru_cache(maxsize=256)(_read)

# ---------------- prospețimea cache-ului ----------------
# Cache-urile de mai jos nu expiră singure: un push doar de date (fără cod nou) lasă procesul
# Streamlit pornit cu JSON-urile vechi în memorie. Versiunea datelor = câmpul „generat” din
# stats.json, recitit direct de pe disc/URL cel mult o dată la VERSION_TTL secunde.
VERSION_TTL = 300
_seen_version: str | None = None


@st.cache_data(ttl=VERSION_TTL, show_spinner=False)
def _data_version() -> str:
    try:
        return str((_read("stats.json") or {}).get("generat") or "")
    except Exception:  # sursă indisponibilă momentan: păstrăm ce avem în cache
        return ""


def clear_caches() -> None:
    _load_raw.cache_clear()
    st.cache_data.clear()


def refresh_if_new() -> None:
    """Golește toate cache-urile dacă stats.json are alt „generat” decât cel servit până acum.

    Apelat din Overview.py la fiecare rerun. Primul apel din proces golește tot o dată, ca să nu
    supraviețuiască intrări vechi după un reload de modul.
    """
    global _seen_version
    v = _data_version()
    if not v or v == _seen_version:
        return
    _seen_version = v
    clear_caches()


@st.cache_data(show_spinner=False)
def load(rel: str):
    return _load_raw(rel)


# ---------------- sumar ----------------
@st.cache_data(show_spinner=False)
def stats() -> dict:
    return _load_raw("stats.json")


# ---------------- persoane (graf gold) ----------------
@st.cache_data(show_spinner=False)
def persoane_df() -> pd.DataFrame:
    ps = _load_raw("graf/persoane_gold.json").get("persoane", [])
    rows = []
    for p in ps:
        pl = p.get("parlamentar") or {}
        rows.append({
            "romega_id": p.get("romega_id"), "nume": (p.get("nume_key") or "").title(),
            "incredere": p.get("incredere"), "n_declaratii": p.get("n_declaratii", 0),
            "n_companii": p.get("n_companii", 0), "contracte_ron": p.get("total_contracte_ron") or 0,
            "camera": pl.get("camera"), "partid": pl.get("partid"), "judet": pl.get("judet"),
            "comisii": len(pl.get("comisii") or []), "plx_initiate": pl.get("plx_initiate") or 0,
            "are_cv": p.get("are_cv", False),
        })
    return pd.DataFrame(rows)


@st.cache_data(show_spinner=False)
def persoana(romega_id: str) -> dict:
    for p in _load_raw("graf/persoane_gold.json").get("persoane", []):
        if p.get("romega_id") == romega_id:
            return p
    return {}


# ---------------- companii ----------------
def _words(s) -> str:
    """Nume normalizat pe cuvinte (fără diacritice/punctuație), pt. potriviri pe cuvinte întregi."""
    import re
    import unicodedata
    flat = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return " " + re.sub(r"[^a-z0-9]+", " ", flat).strip() + " "


def bvb_pentru(company: dict, bvb: list) -> dict:
    """Acționariatul BVB al unei companii: doar dacă e marcată ca listată ȘI numele BVB apare ca
    cuvinte întregi în denumire (altfel „Compa” se lipea de orice „Compania Națională…”, iar
    filialele primeau procentul companiei-mamă). La mai multe potriviri, cea mai lungă."""
    if not company.get("bvb_listed"):
        return {}
    name = _words(company.get("name"))
    hits = [b for b in bvb if _words(b.get("nume")).strip() and _words(b.get("nume")) in name]
    return max(hits, key=lambda b: len(b.get("nume") or ""), default={})


@st.cache_data(show_spinner=False)
def companii_df() -> pd.DataFrame:
    idx = _load_raw("companii/_index.json").get("data", [])
    cf = {int(r["cui"]): r for r in _load_raw("achizitii/contracte_firme.json").get("firme", [])
          if str(r.get("cui", "")).isdigit()}
    bvb = _load_raw("companii/actionariat_bvb.json").get("companii", [])
    rows = []
    for c in idx:
        try:
            cui = int(c["cui"])
        except (ValueError, TypeError):
            continue
        fin = c.get("financials") or {}
        ctr = cf.get(cui, {})
        bv = bvb_pentru(c, bvb)
        rows.append({
            "cui": cui, "nume": c.get("name", ""), "sector": c.get("sector"),
            "tutela": c.get("tutelary_authority"), "judet": c.get("county"),
            "bvb": bool(c.get("bvb_listed")), "salariati": fin.get("nr_salariati"),
            "cifra_afaceri": fin.get("cifra_afaceri"), "profit": fin.get("profit_net"),
            "procent_stat": bv.get("procent_stat"), "contracte_ron": ctr.get("total_ron"),
            "contracte_nr": ctr.get("nr_contracte"), "nr_reps": len(c.get("legal_reps") or []),
        })
    return pd.DataFrame(rows)


# ---------------- achiziții ----------------
@st.cache_data(show_spinner=False)
def contracte_df() -> pd.DataFrame:
    return pd.DataFrame(_load_raw("achizitii/contracte_firme.json").get("firme", []))


@st.cache_data(show_spinner=False)
def achizitii_directe_df() -> pd.DataFrame:
    """Furnizorii de achiziții directe (cumpărări directe SICAP, agregate pe CUI; vezi meta.acoperire)."""
    d = _load_raw("companii/achizitii_directe.json")
    df = pd.DataFrame(d.get("furnizori", []))
    if not df.empty:
        df["ani_activi"] = df["ani_activi"].apply(lambda a: ", ".join(a) if isinstance(a, list) else (a or ""))
        df["top_autoritati"] = df["top_autoritati"].apply(
            lambda a: " · ".join(a) if isinstance(a, list) else (a or ""))
    return df


@st.cache_data(show_spinner=False)
def achizitii_directe_meta() -> dict:
    d = _load_raw("companii/achizitii_directe.json")
    return {"total_furnizori": d.get("total_furnizori", 0), "total_achizitii": d.get("total_achizitii", 0),
            "valoare_totala_ron": d.get("valoare_totala_ron", 0), "sursa": d.get("sursa", ""),
            "acoperire": d.get("acoperire", ""), "generated_at": d.get("generated_at", "")}


@st.cache_data(show_spinner=False)
def firma_profil(cui) -> dict:
    """Profil 'bani de la stat' al unei firme după CUI: contracte (licitații) + achiziții directe.

    Datele sunt AGREGATE per firmă (total, număr, ani, top autorități) — nu contract-cu-contract;
    obiectul fiecărui contract nu e în setul public. Întoarce {} dacă CUI invalid.
    """
    try:
        cui_i = int(cui)
    except (TypeError, ValueError):
        return {}
    out: dict = {"cui": cui_i}
    for r in _load_raw("achizitii/contracte_firme.json").get("firme", []):
        if str(r.get("cui")) == str(cui_i):
            out["contracte"] = {"total_ron": r.get("total_ron"), "nr": r.get("nr_contracte"),
                                "ani": r.get("ani") or [], "nume": r.get("nume")}
            break
    for r in _load_raw("companii/achizitii_directe.json").get("furnizori", []):
        if str(r.get("cui")) == str(cui_i):
            out["achizitii_directe"] = {"total_ron": r.get("total_ron"), "nr": r.get("nr"),
                                        "ani_activi": r.get("ani_activi") or [],
                                        "top_autoritati": r.get("top_autoritati") or [],
                                        "nume": r.get("nume")}
            break
    for r in _load_raw("companii/firme_onrc.json").get("firme", []):
        if str(r.get("cui")) == str(cui_i):
            out["onrc"] = {"caen": r.get("caen"), "caen_domeniu": r.get("caen_domeniu"),
                           "forma_juridica": r.get("forma_juridica"), "judet": r.get("judet"),
                           "localitate": r.get("localitate"), "an_infiintare": r.get("an_infiintare")}
            break
    return out


@st.cache_data(show_spinner=False)
def firme_nume_map() -> dict:
    """Hartă cui (int) -> denumire firmă. firme_onrc.json (dump ONRC) nu are denumirea; o luăm din
    reprezentanții legali (denumire), cu fallback pe numele din contracte / achiziții directe."""
    out: dict = {}
    for c in _load_raw("companii/reprezentanti.json").get("companii", []) or []:
        try:
            cui = int(c.get("cui"))
        except (TypeError, ValueError):
            continue
        if c.get("denumire"):
            out[cui] = c["denumire"]
    for path, key in (("achizitii/contracte_firme.json", "firme"),
                      ("companii/achizitii_directe.json", "furnizori")):
        for r in _load_raw(path).get(key, []) or []:
            try:
                cui = int(r.get("cui"))
            except (TypeError, ValueError):
                continue
            if cui not in out and r.get("nume"):
                out[cui] = r["nume"]
    return out


# ---------------- analiză de rețea (inele / huburi / poduri) ----------------
@st.cache_data(show_spinner=False)
def network_metrics() -> dict:
    return _load_raw("graf/network_metrics.json")


@st.cache_data(show_spinner=False)
def ro_judete_geojson() -> dict:
    """GeoJSON cu județele RO (simplificat). proprietăți: judet (cheie normalizată), nume (afișare)."""
    return _load_raw("geo/ro_judete.geojson")


@st.cache_data(show_spinner=False)
def changelog() -> dict:
    """Modificări față de rebuild-ul anterior (deepdiff). Gol până la al 2-lea rebuild."""
    return _load_raw("changelog.json")


@st.cache_data(show_spinner=False)
def redflags() -> dict:
    """Red-flags achiziții (single-bid + fragmentare), metodologie OCDS. Vezi harvest_redflags.py."""
    return _load_raw("redflags.json")


@st.cache_data(show_spinner=False)
def avere_anomalii() -> dict:
    """Anomalii de avere (PyOD/ECOD) — profiluri statistic neobișnuite. Vezi build_avere_anomalii.py."""
    return _load_raw("avere_anomalii.json")


@st.cache_data(show_spinner=False)
def comisii_recent() -> dict:
    """Activitatea recentă a comisiilor (ședințe + PLx + acte de bază). Vezi build_comisii_recent.py."""
    return _load_raw("comisii/activitate_recenta.json")


# ---------------- firme ONRC (profil firme cu bani de stat) ----------------
@st.cache_data(show_spinner=False)
def firme_onrc() -> pd.DataFrame:
    """Profil ONRC al firmelor care au luat bani de la stat (contracte + achiziții directe).

    Sursa: data/v1/companii/firme_onrc.json. Adaugă coloane derivate:
      - este_noua: flag 'firmă nouă cu bani de stat' (înființată cu ≤1 an înainte de prima achiziție)
      - mama_straina: are firmă-mamă într-o țară străină (exclude România)
      - flaguri_txt: flagurile concatenate pentru afișare
    """
    firme = _load_raw("companii/firme_onrc.json").get("firme", [])
    df = pd.DataFrame(firme)
    if df.empty:
        return df

    def _flaguri(x):
        return x if isinstance(x, list) else []

    df["flaguri"] = df["flaguri"].apply(_flaguri)
    df["este_noua"] = df["flaguri"].apply(lambda fl: any("firmă nouă" in f for f in fl))
    df["flaguri_txt"] = df["flaguri"].apply(lambda fl: " · ".join(fl))
    tm = df["tara_mama"].fillna("").str.strip()
    df["mama_straina"] = (tm != "") & (tm.str.lower() != "românia")
    df["cui"] = pd.to_numeric(df["cui"], errors="coerce").astype("Int64")   # null (PF) nu mai face float
    df["nume"] = df["cui"].map(firme_nume_map()).fillna("")
    return df


@st.cache_data(show_spinner=False)
def firme_onrc_meta() -> dict:
    d = _load_raw("companii/firme_onrc.json")
    return {
        "total": d.get("total", 0),
        "cu_caen": d.get("cu_caen", 0),
        "cu_mama_straina": d.get("cu_mama_straina", 0),
        "flagged": d.get("flagged", 0),
        "sursa": d.get("sursa", ""),
        "nota": d.get("nota", ""),
    }


# ---------------- follow-the-money ----------------
@st.cache_data(show_spinner=False)
def follow_money() -> dict:
    return _load_raw("graf/follow_the_money.json")


@st.cache_data(show_spinner=False)
def retele_coadministrare() -> pd.DataFrame:
    return pd.DataFrame(_load_raw("analytics/retele_coadministrare.json").get("data", []))


# ---------------- partide ----------------
@st.cache_data(show_spinner=False)
def partide_df() -> pd.DataFrame:
    return pd.DataFrame(_load_raw("partide/partide.json").get("partide", []))


@st.cache_data(show_spinner=False)
def subventii_df() -> pd.DataFrame:
    return pd.DataFrame(_load_raw("partide/subventii.json").get("subventii", []))


# ---------------- bugete ----------------
@st.cache_data(show_spinner=False)
def bugete_uat_df() -> pd.DataFrame:
    return pd.DataFrame(_load_raw("bugete/uat.json"))


@st.cache_data(show_spinner=False)
def bgc_df() -> pd.DataFrame:
    return pd.DataFrame(_load_raw("bugete/bgc.json"))


# ---------------- DNA ----------------
@st.cache_data(show_spinner=False)
def dna_df() -> pd.DataFrame:
    return pd.DataFrame(_load_raw("audit/dna.json").get("data", []))


# ---------------- comisii / legislativ ----------------
@st.cache_data(show_spinner=False)
def comisii_senat() -> list:
    return _load_raw("comisii/senat_comisii.json").get("comisii", [])


@st.cache_data(show_spinner=False)
def plx_initiatori_df() -> pd.DataFrame:
    return pd.DataFrame(_load_raw("comisii/plx_initiatori.json").get("plx", []))


@st.cache_data(show_spinner=False)
def guvernanta() -> dict:
    """Registrul oficial guvernanta.gov.ro: conducerea companiilor de stat centrale (CA, directori),
    remunerație brută lunară, afiliere politică, mandat, CV oficial. Vezi pipeline/harvest_guvernanta.py."""
    try:
        return _load_raw("guvernanta/registry.json") or {}
    except Exception:   # LIVE: fișierul poate lipsi înainte de publicare
        return {}


def guvernanta_companie(cui) -> dict:
    """Conducerea oficială a unei companii (după CUI) + numirile ei; {} dacă nu e în registru."""
    try:
        cui_i = int(cui)
    except (TypeError, ValueError):
        return {}
    g = guvernanta()
    comp = next((c for c in g.get("companii", []) if c.get("cui") == cui_i), None)
    if not comp:
        return {}
    return {**comp, "numiri": [n for n in g.get("numiri", []) if n.get("cui") == cui_i]}


def guvernanta_persoana(romega_id: str) -> list:
    """Numirile oficiale legate de o persoană din graf (potrivire 'confirmat' sau 'candidat')."""
    return [n for n in guvernanta().get("numiri", []) if romega_id and n.get("romega_id") == romega_id]


@st.cache_data(show_spinner=False)
def plx_docs_by_idp() -> dict:
    """Map idp(str) -> {titlu, camera, documente:[{tip,url}]} din plx.json (toate cele ~1920 PLx)."""
    out = {}
    for p in _load_raw("comisii/plx.json").get("plx", []):
        out[str(p.get("idp"))] = {
            "titlu": p.get("titlu"), "camera": p.get("camera"),
            "documente": p.get("documente", [])}
    return out


@st.cache_data(show_spinner=False)
def plx_docs_text() -> dict:
    """url -> {s: stare (ok/scanat/...), x: extras, v: {verdict, amendamente, vot}, p: pagini, o: 1=OCR}."""
    return _load_raw("comisii/documente_text.json").get("documente", {})


@st.cache_data(show_spinner=False)
def plx_search_terms() -> dict:
    """idp -> termenii normalizați (fără diacritice) din titlul și documentele PLx."""
    return _load_raw("comisii/cautare_documente.json").get("termeni", {})


_TR_RO = str.maketrans("ăâîșşțţĂÂÎȘŞȚŢ", "aaisstt" "AAISSTT")


def plx_search(q: str) -> set:
    """idp-urile PLx în care TOȚI termenii interogării apar (ca început de cuvânt) în titlu sau documente.
    „pensii speciale” găsește și „pensiile speciale”; „227/2015” găsește referința la lege."""
    toks = re.findall(r"[a-z0-9/]{2,}", q.translate(_TR_RO).lower())
    toks = [re.sub(r"^0+(?=\d+/)", "", t) for t in toks]      # indexul ține „71/2009”, nu „071/2009”
    if not toks:
        return set()
    pats = [re.compile(r"(?:^| )" + re.escape(t)) for t in toks]
    return {idp for idp, s in plx_search_terms().items() if all(p.search(s) for p in pats)}


@st.cache_data(show_spinner=False)
def plx_verdicts() -> dict:
    """idp -> {"sursa:verdict": n} — ex. comisie:favorabil, raport:respingere, guvern:nu_sustine, cl:favorabil.
    Deciziile sunt extrase automat din avize, rapoarte și punctele de vedere ale Guvernului."""
    txt = plx_docs_text()
    out = {}
    for idp, rec in plx_docs_by_idp().items():
        c = collections.Counter()
        for d in rec["documente"]:
            v = txt.get(d["url"], {}).get("v")
            if v:
                c[f"{v.get('sursa')}:{v.get('verdict')}"] += 1
        if c:
            out[idp] = dict(c)
    return out


# ---------------- analytics (DuckDB views) ----------------
@st.cache_data(show_spinner=False)
def analytics(name: str) -> pd.DataFrame:
    return pd.DataFrame(_load_raw(f"analytics/{name}.json").get("data", []))


# ---------------- alerte (semnale) ----------------
@st.cache_data(show_spinner=False)
def alerte() -> dict:
    """Semnale de interes generate automat din date deschise (NU acuzații).

    Întoarce dict-ul brut: {disclaimer, total, pe_severitate, pe_tip, agregate, alerte:[...]}.
    Câmpul alerte[i].entitate poate fi string SAU dict (ex. {cui, forma_juridica, ...}).
    """
    return _load_raw("alerte.json")


# ---------------- sancțiuni & PEP ----------------
@st.cache_data(show_spinner=False)
def sanctiuni() -> dict:
    """Entități cu legătură RO din OpenSanctions (sancțiuni internaționale + PEP).

    Întoarce: {meta: {total, sanctiuni, pep, in_graf, nota}, df: DataFrame}.
    df coloane: nume, nume_key, schema, dataset ('sanctions'|'peps'), topics, tara,
    pozitie, motiv, liste, in_graf, romega_id, n_declaratii, n_companii.
    """
    d = _load_raw("sanctiuni_ro.json")
    ents = d.get("entitati", [])
    rows = []
    for e in ents:
        rows.append({
            "nume": e.get("nume") or "",
            "nume_key": e.get("nume_key") or "",
            "schema": e.get("schema") or "",
            "dataset": e.get("dataset") or "",
            "topics": e.get("topics") or [],
            "tara": e.get("tara") or [],
            "pozitie": e.get("pozitie"),
            "motiv": e.get("motiv"),
            "liste": e.get("liste") or [],
            "in_graf": bool(e.get("in_graf")),
            "romega_id": e.get("romega_id"),
            "n_declaratii": e.get("n_declaratii", 0),
            "n_companii": e.get("n_companii", 0),
        })
    df = pd.DataFrame(rows)
    meta = {
        "total": d.get("total", len(ents)),
        "sanctiuni": d.get("sanctiuni", 0),
        "pep": d.get("pep", 0),
        "in_graf": d.get("in_graf", 0),
        "nota": d.get("nota", ""),
    }
    return {"meta": meta, "df": df}


# ---------------- declarații: detaliu pe persoană (fișiere mari, citite punctual) ----------------
def _read_json(rel: str):
    """Citește un JSON FĂRĂ memoizare — pentru fișiere mari din care păstrăm doar câteva rânduri.
    `_load_raw` ar ține tot fișierul în memorie pe durata procesului (73 MB de declarații)."""
    if LIVE:
        return _load_raw(rel)
    p = os.path.join(DATA, rel.replace("/", os.sep))
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def _decl_files() -> list[str]:
    """Fișierele cu declarații detaliate (avere_*.json, interese_*.json); [] în modul LIVE."""
    folder = os.path.join(DATA, "declaratii")
    if LIVE or not os.path.isdir(folder):
        return []
    return sorted(f for f in os.listdir(folder)
                  if f.endswith(".json") and f.split("_")[0] in ("avere", "interese"))


@st.cache_data(show_spinner="Se indexează declarațiile…")
def _decl_fisiere_pe_institutie() -> dict:
    """instituție -> fișierele în care apare. Construit o singură dată, citind fișierele pe rând."""
    out: dict = {}
    for f in _decl_files():
        for inst in {r.get("institutie") for r in _read_json(f"declaratii/{f}").get("declaratii", [])}:
            if inst:
                out.setdefault(inst, []).append(f)
    return out


def _name_tokens(s) -> tuple:
    return tuple(sorted(_words(s).split()))


@st.cache_data(show_spinner=False, max_entries=128)
def declaratii_detaliu(nume_key: str, institutii: tuple) -> list:
    """Declarațiile detaliate ale unei persoane: aceleași cuvinte în nume și aceeași instituție ca în graf.

    Întoarce rânduri cu `tip` ('avere' / 'interese') și câmpurile din fișierul-sursă (active, datorii,
    entități declarate, pdf_url). Citește doar fișierele instituțiilor persoanei.
    """
    tinta = _name_tokens(nume_key)
    if not tinta or not institutii:
        return []
    index = _decl_fisiere_pe_institutie()
    fisiere = sorted({f for inst in institutii for f in index.get(inst, [])})
    out = []
    for f in fisiere:
        tip = f.split("_")[0]
        for r in _read_json(f"declaratii/{f}").get("declaratii", []):
            if r.get("institutie") in institutii and _name_tokens(r.get("nume_norm") or r.get("nume")) == tinta:
                out.append({**r, "tip": tip})
    return out


# ---------------- CV: sursa documentului ----------------
@st.cache_data(show_spinner=False)
def _cv_urls() -> dict:
    """cuvintele numelui (sortate) -> URL-ul CV-ului (companii de stat, deputați, senatori)."""
    out: dict = {}
    for rel in ("companii/cv.json", "companii/cv_parlament.json", "companii/cv_senatori.json"):
        for c in _load_raw(rel).get("cv", []) or []:
            if c.get("url") and c.get("nume"):
                out.setdefault(_name_tokens(c["nume"]), c["url"])
    return out


def cv_url(nume_key: str) -> str:
    return _cv_urls().get(_name_tokens(nume_key), "")


# ---------------- bilanțuri pe ani ----------------
@st.cache_data(show_spinner=False)
def _bilanturi_trend() -> dict:
    return {int(t["cui"]): t.get("ani") or {} for t in _load_raw("companii/bilanturi_trend.json").get("trend", [])
            if str(t.get("cui", "")).isdigit()}


def bilanturi_trend(cui) -> pd.DataFrame:
    """Serie anuală (an, cifra_afaceri, profit_net, datorii, nr_salariati) pentru o companie; goală dacă lipsește."""
    try:
        ani = _bilanturi_trend().get(int(cui), {})
    except (TypeError, ValueError):
        ani = {}
    rows = [{"an": int(an), **(vals or {})} for an, vals in ani.items() if str(an).isdigit()]
    return pd.DataFrame(rows).sort_values("an") if rows else pd.DataFrame()


# ---------------- partide: rapoarte financiare ----------------
@st.cache_data(show_spinner=False)
def rapoarte_rvc_df() -> pd.DataFrame:
    """Rapoartele anuale de venituri și cheltuieli publicate de partide în Monitorul Oficial."""
    rows = [{k: r.get(k) for k in ("partid_nume", "partid_cod", "an", "data_publicare", "mo_nr",
                                   "venituri", "cotizatii", "donatii", "alte_venituri", "imprumuturi",
                                   "reprezentant_legal", "url")}
            for r in _load_raw("partide/rapoarte_rvc.json").get("data", [])]
    return pd.DataFrame(rows)


# ---------------- parlament: moțiuni, deputați, senatori ----------------
@st.cache_data(show_spinner=False)
def motiuni_df() -> pd.DataFrame:
    df = pd.DataFrame(_load_raw("parlament/motiuni.json").get("motiuni", []))
    if not df.empty:
        df["data_iso"] = pd.to_datetime(df["data"], format="%d.%m.%Y", errors="coerce")
        df["titlu"] = df["titlu"].fillna("").str.replace(r"\s+", " ", regex=True).str.strip(' "')
    return df


@st.cache_data(show_spinner=False)
def motiune_text(idm, leg, cam) -> dict:
    """Textul unei moțiuni (citit prin OCR din PDF-ul scanat); {} dacă nu a fost încă citit."""
    for m in _load_raw("parlament/motiuni_text.json").get("motiuni", []) or []:
        if (m.get("idm"), m.get("leg"), m.get("cam")) == (idm, leg, cam):
            return m
    return {}


@st.cache_data(show_spinner=False)
def deputati_df() -> pd.DataFrame:
    return pd.DataFrame(_load_raw("parlament/deputati.json").get("data", []))


@st.cache_data(show_spinner=False)
def senatori_df() -> pd.DataFrame:
    return pd.DataFrame(_load_raw("parlament/senatori.json").get("data", []))


# ---------------- search index ----------------
@st.cache_data(show_spinner=False)
def search_index() -> list:
    return _load_raw("search/index.json").get("items", [])
