"""Extragerea totalurilor pe tabele din rapoartele financiare ale partidelor (fără rețea)."""

from pipeline import harvest_rvc_partide as h

ANTET = "Denumirea partidului politic: Partidul Exemplu Sediul partidului politic: București Nr. crt. | "

RAPORT = "\n".join([
    "Situația cuantumului total al cotizațiilor primite în anul 2025 " + ANTET
    + "Organizația | Cuantumul total al cotizațiilor primite în luna ianuarie |",
    "1 | ALBA | 45.680,00 |",
    "Cuantumul total | 11.448.430,02 |",
    "Lista membrilor de partid care au plătit în anul 2025 cotizații a căror valoare depășește baremul "
    + ANTET + "Numele | Valoarea cotizației |",
    "Cuantumul total | 410.762,61 |",
    "^1 În cazul în care există persoane juridice care au făcut donații în mai multe organizații",
    "Lista persoanelor fizice care au făcut în anul 2025 donații " + ANTET + "Numele | Valoarea donației |",
    "Cuantumul total | 3.074.005,00 |",
    "Suma totală a donațiilor confidențiale primite în anul 2025 " + ANTET + "Organizația |",
    "Cuantumul total | — |",
    "Lista persoanelor juridice care au făcut în anul 2025 donații " + ANTET + "Denumirea donatorului |",
    "Cuantumul total | n/a |",
    "^1 nota de subsol care pomenește din nou donații",
    "Suma totală a împrumuturilor cu o valoare mai mică de 100 de salarii " + ANTET + "Organizația |",
    "Cuantumul total | 30.000 |",
    "Situația centralizată a cuantumurilor totale ale veniturilor obținute în anul 2025 " + ANTET
    + "Activitatea generatoare de venit | Cuantum anual |",
    "Cuantumul total | 9.887.259,34 |",
    "Situația sumelor ce fac obiectul aportului financiar în asocierea cu formațiuni nepolitice " + ANTET,
    "Cuantumul total | 0,00 |",
])


def test_suma_formats():
    assert h._suma("11.448.430,02") == 11448430.02
    assert h._suma("2.850") == 2850.0
    assert h._suma("6.800.000") == 6800000.0
    assert h._suma("0") == 0.0
    assert h._suma("-") == 0.0 and h._suma("—") == 0.0 and h._suma("") == 0.0
    assert h._suma("n/a") is None
    assert h._suma("1.23") is None          # nu e nici mie, nici zecimală românească


def test_sectiuni_classified_by_table_heading():
    s = h.parse_sectiuni(RAPORT)
    assert s["cotizatii"] == 11448430.02
    assert s["cotizatii_peste_barem"] == 410762.61   # sublistă: separată, nu adunată la cotizații
    assert s["donatii"] == 3074005.0                 # „—” = 0, „n/a” ignorat
    assert s["imprumuturi"] == 30000.0               # nota despre donații nu schimbă tipul tabelului
    assert s["alte_venituri"] == 9887259.34
    assert s["aport_asociere"] == 0.0


def test_income_excludes_loans_and_sublists():
    s = h.parse_sectiuni(RAPORT)
    venituri = sum(s[k] for k in h.VENITURI_DIN if k in s)
    assert round(venituri, 2) == round(11448430.02 + 3074005.0 + 9887259.34, 2)


def test_report_without_tables_has_no_sections():
    assert h.parse_sectiuni("Denumirea partidului politic: X\nfără niciun tabel") == {}
