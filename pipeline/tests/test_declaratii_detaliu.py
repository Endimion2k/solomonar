"""Anul declarației și rolurile din declarațiile de interese (fără rețea, fără fișiere)."""

from pipeline import build_declaratii_detaliu as b

AN = 2026


def test_year_prefers_file_name_over_upload_path():
    url = "https://x.ro/wp-content/uploads/2023/03/Declaratie-avere-Andronie-Eugen-numire-28.06.2022.pdf"
    assert b.an_din_url(url, AN) == (2022, "nume_fisier")


def test_year_from_path_when_file_name_has_none():
    assert b.an_din_url("https://www.cdep.ro/declaratii/deputati/2024/avere/153a.pdf", AN) == (2024, "cale")


def test_year_ignores_out_of_range_numbers_and_ids():
    assert b.an_din_url("https://x.ro/media/00/d8/00d8c361-2031-4810/vass_a_elod.pdf", AN) == (None, None)
    assert b.an_din_url("https://x.ro/doc/2003/raport.pdf", AN) == (None, None)      # înainte de formulare
    assert b.an_din_url("https://x.ro/files/120254/declaratie.pdf", AN) == (None, None)  # „2025” în alt număr


def test_year_handles_encoded_names():
    assert b.an_din_url("https://x.ro/d/Abrudan+Valerica+-+DA+2024-A.pdf", AN) == (2024, "nume_fisier")
    assert b.an_din_url("https://x.ro/d/declara%C8%9Bie%202021.pdf", AN) == (2021, "nume_fisier")


def test_roles_come_from_row_numbering():
    r = b.roluri_din_entitati([
        "1.1 TERMO PLOIESTI SRL - Ploiesti", "2.1 CNAIR SA Sectorul 1 Bucuresti",
        "4.1 PARTIDUL NATIONAL LIBERAL GORJ - PRESEDINTE", "3.1 Sindicatul ECOLOGISTUL - membru",
        "Mosilor 268, bl. 12, sc. 1", "SC ECODET", "1.1 TERMO PLOIESTI SRL - Ploiesti",
    ])
    assert [(x["sectiune"], x["entitate"]) for x in r] == [
        (1, "TERMO PLOIESTI SRL - Ploiesti"), (2, "CNAIR SA Sectorul 1 Bucuresti"),
        (4, "PARTIDUL NATIONAL LIBERAL GORJ - PRESEDINTE"), (3, "Sindicatul ECOLOGISTUL - membru")]
    assert r[0]["rol"] == "asociat sau acționar" and r[2]["rol"] == "funcție în partid"


def test_annotation_prefers_document_date_and_keeps_tables():
    rec = {"pdf_url": "https://x.ro/2023/a.pdf", "entitati": ["1.2 ACME SRL"]}
    b.adnoteaza(rec, "interese", {"an_document": 2022, "participatii": [{"firma": "ACME SRL"}]}, AN)
    assert (rec["an"], rec["an_sursa"]) == (2022, "document")
    assert rec["roluri"][0]["entitate"] == "ACME SRL" and rec["participatii"] == [{"firma": "ACME SRL"}]
    b.adnoteaza(rec, "interese", None, AN)        # fără extragere: revine la URL, tabelele dispar
    assert (rec["an"], rec["an_sursa"]) == (2023, "cale") and "participatii" not in rec


def test_wealth_records_get_no_roles():
    rec = {"pdf_url": "https://x.ro/d/declaratie-2024.pdf"}
    b.adnoteaza(rec, "avere", None, AN)
    assert rec["an"] == 2024 and "roluri" not in rec


# ---- extragerea din tabelele PDF-urilor (funcțiile pure, fără PDF) ----
from pipeline import extract_declaratii_tabele as x  # noqa: E402


def test_document_date_uses_last_occurrence():
    text = "exemplu 01.01.2019\nData completării\nSemnătura\n30-12-2024\n19 / 19"
    assert x.an_din_text(text) == 2024
    assert x.an_din_text("fără dată") is None


def test_table_kind_from_header():
    assert x.clasifica_antet(["Emitent titlu/societatea în care persoana este acționar", "Tipul*"]) == "avere_IV2"
    assert x.clasifica_antet(["Unitatea – denumirea şi adresa –", "Calitatea deţinută",
                              "Nr. de părţi sociale sau de acţiuni", "Valoarea totală"]) == "interese_1"
    assert x.clasifica_antet(["Unitatea – denumirea şi adresa –", "Calitatea deţinută",
                              "Valoarea beneficiilor"]) == "interese_2"
    assert x.clasifica_antet(["Nr. crt.", "Marca", "An fabricație"]) is None


def test_entity_keeps_name_drops_address_and_numbering():
    assert x.nume_entitate("1 .1 TERMO PLOIESTI SRL - Ploiesti Prahova, str. Vlad Tepes nr. 37") == "TERMO PLOIESTI SRL"
    assert x.nume_entitate("MAXIMUS GENERAL SERVICES srl - Sectorul 5 Bucuresti STR. X, NR. 14, AP. 8") \
        == "MAXIMUS GENERAL SERVICES srl"
    assert x.nume_entitate("ROMGAZ SA") == "ROMGAZ SA"


def test_rows_skip_blanks_headers_and_personal_loans():
    assert x.rand_participatie("interese_1", ["-", "-", "", "-"]) is None
    assert x.rand_participatie("interese_2", ["Unitatea – denumirea şi adresa –", "Calitatea deţinută", "Valoarea"]) is None
    # împrumut acordat unei persoane fizice: nu se publică
    assert x.rand_participatie("avere_IV2", ["POPESCU ION", "Împrumuturi acordate în nume personal",
                                             "198000", "198000 RON"]) is None
    r = x.rand_participatie("avere_IV2", ["SC ACME SA", "Acţiuni sau părţi sociale în societăţi comerciale",
                                          "100", "5000 RON"])
    assert r == {"sursa": "avere_IV2", "entitate": "SC ACME SA",
                 "calitate": "Acţiuni sau părţi sociale în societăţi comerciale", "nr": "100", "valoare": "5000 RON"}
    r = x.rand_participatie("interese_1", ["1 .1 MAXIMUS SRL - Buzau, cart. Brosteni", "Asociat",
                                           "50 Părţi sociale", "200 RON"])
    assert (r["entitate"], r["calitate"], r["nr"], r["valoare"]) == ("MAXIMUS SRL", "Asociat", "50 Părţi sociale", "200 RON")
    r = x.rand_participatie("interese_2", ["TERMO PLOIESTI SRL - Ploiesti", "Membru consiliu de administratie", "9000 RON"])
    assert (r["entitate"], r["valoare"], r["nr"]) == ("TERMO PLOIESTI SRL", "9000 RON", "")
