"""Valori nete pe firmă: un contract se numără o dată, plafoanele de acord-cadru stau separat (fără rețea)."""

from pipeline import harvest_contracte_nete as h


def test_contract_type_from_export_label():
    assert h.tip_incheiere("Cu acord cadru") == h.CADRU
    assert h.tip_incheiere("Cu acord cadru subsecvent") == h.SUBSECVENT
    assert h.tip_incheiere("Fara acord cadru") == h.SIMPLU
    assert h.tip_incheiere("") == h.SIMPLU


def _contracte():
    c: dict = {}
    k1 = ("AC1", "CAN1", "1", "100", "1/2/2024")
    for cui, nume in (("11", "ALFA"), ("22", "BETA"), ("33", "GAMA")):      # asociere: 900 scris pe 3 rânduri
        h.adauga(c, k1, h.SIMPLU, 900.0, cui, nume, "Spital")
    h.adauga(c, ("AC1", "CAN2", "1", "200", "3/2/2024"), h.SIMPLU, 500.0, "11", "ALFA", "Primarie")
    k3 = ("AC2", "CAN3", "1", "300", "5/2/2024")
    for cui, nume in (("11", "ALFA"), ("22", "BETA")):                      # acord-cadru: plafon 10.000
        h.adauga(c, k3, h.CADRU, 10_000.0, cui, nume, "Minister")
    h.adauga(c, ("AC2", "CAN3", "1", "301", "6/2/2024"), h.SUBSECVENT, 400.0, "22", "BETA", "Minister")
    return c


def test_shared_contract_is_split_and_frameworks_are_kept_apart():
    f = h.agrega(_contracte())
    assert f["11"]["total_ron"] == 800.0            # 900/3 + 500
    assert f["11"]["total_ron_singur"] == 500.0
    assert f["11"]["total_ron_brut"] == 11_400.0    # metoda veche: 900 + 500 + 10.000
    assert f["11"]["plafon_acorduri_ron"] == 5_000.0
    assert (f["11"]["nr_contracte"], f["11"]["nr_contracte_comune"], f["11"]["nr_acorduri_cadru"]) == (2, 1, 1)
    assert f["22"]["total_ron"] == 700.0            # 900/3 + 400 subsecvent
    assert f["33"]["total_ron"] == 300.0
    assert f["11"]["top_autoritati"] == ["Primarie", "Spital"]


def test_net_total_equals_money_actually_contracted():
    f = h.agrega(_contracte())
    assert round(sum(x["total_ron"] for x in f.values())) == 900 + 500 + 400


def test_same_row_twice_does_not_add_a_signatory():
    c: dict = {}
    k = ("AC", "CAN", "1", "1", "d")
    h.adauga(c, k, h.SIMPLU, 100.0, "11", "ALFA", "X")
    h.adauga(c, k, h.SIMPLU, 100.0, "11", "ALFA SRL", "X")
    assert h.agrega(c)["11"]["total_ron"] == 100.0


def test_misspelled_header_of_2024_files_is_recognised():
    from pipeline import sicap_io

    antet = ["Data contract", "Numar contract", "Incheiar prin ", "Valoare contract (RON)"]
    assert sicap_io.pick(antet, h.COL_INCHEIAT) == 2


def test_numeric_xlsx_cells_do_not_grow_a_trailing_zero():
    from pipeline import sicap_io
    from pipeline.harvest_redflags import _cui

    assert _cui(sicap_io.celula(4930083621.0)) == "4930083621"
    assert sicap_io.celula(1234.5) == "1234.5" and sicap_io.celula(None) == "" and sicap_io.celula("RO 12") == "RO 12"
