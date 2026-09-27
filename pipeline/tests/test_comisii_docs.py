"""Documentele PLx: normalizare, verdictul comisiei din fraza de decizie, index de căutare."""

from __future__ import annotations

from pipeline.build_comisii_docs import doc_kind, norm, search_terms, verdict


def test_norm_keeps_length_of_flattened_text():
    s = "Comisia  a hotărât\n\tsă acorde ŞI Ţ"
    flat = " ".join(s.split())
    assert norm(s) == "comisia a hotarat sa acorde si t" and len(norm(s)) == len(flat)


def test_aviz_favorabil_and_negativ():
    fav = norm("În urma dezbaterilor, comisia a hotărât, cu majoritate de voturi, să acorde un aviz favorabil, "
               "în forma transmisă de Biroul permanent.")
    assert verdict("aviz_comisie", fav) == {"verdict": "favorabil", "sursa": "comisie", "decizie_start": fav.index("a hotarat"),
                                            "amendamente": False, "vot": "majoritate"}
    neg = norm("membrii comisiei au hotărât, cu unanimitate de voturi, să îi acorde aviz negativ.")
    assert verdict("aviz_comisie", neg)["verdict"] == "negativ"


def test_other_institutions_opinions_are_ignored():
    t = norm("Consiliul Legislativ a avizat favorabil propunerea. Guvernul nu susține adoptarea. "
             "Membrii comisiei au hotărât, cu majoritate de voturi, să acorde aviz negativ.")
    assert verdict("aviz_comisie", t)["verdict"] == "negativ"
    assert verdict("aviz_comisie", norm("Consiliul Legislativ a avizat favorabil propunerea.")) is None


def test_raport_adoptare_respingere_and_amendments():
    ad = norm("membrii comisiei au hotărât, cu unanimitate de voturi, adoptarea proiectului de lege cu "
              "amendamente admise")
    assert verdict("raport", ad) == {"verdict": "adoptare", "sursa": "raport", "decizie_start": 0 + ad.index("au hotarat"),
                                     "amendamente": True, "vot": "unanimitate"}
    rs = norm("deputații au hotărât să propună plenului prezentul raport prin care se propune respingerea "
              "propunerii legislative")
    assert verdict("raport_suplimentar", rs)["verdict"] == "respingere"


def test_stem_and_positive_phrasings():
    assert verdict("aviz_comisie", norm("s-a hotărât, cu unanimitate de voturi, avizarea pozitivă a inițiativei"))[
        "verdict"] == "favorabil"
    assert verdict("aviz_comisie", norm("proiectul de buget a fost avizat favorabil, cu amendamente admise"))[
        "verdict"] == "favorabil"
    assert verdict("raport", norm("au hotărât să propună plenului un raport de adoptare a proiectului"))[
        "verdict"] == "adoptare"


def test_rejected_amendments_do_not_mean_rejection():
    t = norm("au hotărât respingerea amendamentelor depuse și adoptarea proiectului de lege în forma Senatului")
    assert verdict("raport", t)["verdict"] == "adoptare"
    t = norm("au hotărât adoptarea proiectului cu amendamente admise și respinse")
    assert verdict("raport", t)["verdict"] == "adoptare"


def test_preliminary_report_adoption_is_skipped():
    t = norm("au hotărât, cu majoritate de voturi, adoptarea raportului preliminar transmis. Comisia a decis, "
             "cu unanimitate de voturi, respingerea proiectului.")
    assert verdict("raport", t)["verdict"] == "respingere"


def test_government_position():
    nu = norm("Având în vedere cele de mai sus, Guvernul nu susține adoptarea acestei inițiative legislative.")
    assert verdict("punct_vedere_guvern", nu)["verdict"] == "nu_sustine"
    assert verdict("punct_vedere_guvern", nu)["sursa"] == "guvern"
    da = norm("Guvernul susține adoptarea propunerii legislative, sub rezerva însușirii observațiilor.")
    v = verdict("punct_vedere_guvern", da)
    assert v["verdict"] == "sustine" and v["observatii"] is True
    lat = norm("Guvernul lasă la latitudinea Parlamentului decizia asupra inițiativei.")
    assert verdict("punct_vedere_guvern", lat)["verdict"] == "latitudine"


def test_legislative_council_and_ces():
    cl = norm("1. Avizează favorabil propunerea legislativă, cu observații și propuneri.")
    assert verdict("aviz_consiliu_legislativ", cl) == {"verdict": "favorabil", "sursa": "cl",
                                                       "decizie_start": cl.index("avizeaza"), "observatii": True}
    assert verdict("aviz_ces", norm("Consiliul avizează nefavorabil proiectul"))["verdict"] == "negativ"


def test_doc_kind_refines_other_documents_by_filename():
    assert doc_kind("alt", "https://www.cdep.ro/proiecte/2025/100/40/7/pvg112.pdf") == "punct_vedere_guvern"
    assert doc_kind("alt", "https://www.cdep.ro/proiecte/2025/100/40/7/ces112.pdf") == "aviz_ces"
    assert doc_kind("alt", "https://www.cdep.ro/proiecte/2025/100/40/7/oug12.pdf") == "ordonanta"
    assert doc_kind("alt", "https://www.cdep.ro/proiecte/2025/100/40/7/as112.pdf") == "alt"
    assert doc_kind("raport", "https://www.cdep.ro/x/pvg1.pdf") == "raport"


def test_verdict_only_for_committee_opinions_and_reports():
    assert verdict("expunere_motive", norm("au hotărât adoptarea")) is None


def test_search_terms_normalized_without_stopwords():
    c = search_terms(["Legea nr. 227/2015 privind Codul fiscal și pensiile speciale"])
    assert {"legea", "227/2015", "codul", "fiscal", "pensiile", "speciale"} <= set(c)
    assert "privind" not in c and "nr" not in c
