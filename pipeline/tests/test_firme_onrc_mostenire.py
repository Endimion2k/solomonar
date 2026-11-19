"""Firmele ieșite din listele-sursă plafonate își păstrează contextul publicat anterior (fără rețea)."""

from pipeline import harvest_firme_onrc as h

NOUA = f"{h.FLAG_NOUA} (înființată cu ≤1 an înainte de prima achiziție)"


def test_keeps_money_context_and_new_company_flag():
    f = {"cui": 1}
    vechi = {"are_contracte": False, "are_achizitii_directe": True, "flaguri": [NOUA, "firmă-mamă în Austria"]}
    assert h.mosteneste(f, vechi) == [NOUA]      # restul flag-urilor se recalculează din profilul ONRC
    assert (f["are_contracte"], f["are_achizitii_directe"]) == (False, True)


def test_unknown_company_inherits_nothing():
    f = {"cui": 2}
    assert h.mosteneste(f, None) == [] and f == {"cui": 2}
