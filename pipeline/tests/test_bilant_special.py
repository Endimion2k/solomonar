"""Bilanțurile băncilor, IFN-urilor și asigurătorilor aduse la câmpurile comune (fără rețea)."""

from pipeline import enrich_financials as e

BANCA = ("361897,6419,13244394674,1489035733,18352833,0,37887886646,53502663665,5000000,1063212836,348211929,"
         "3174794,0,99650255802,106929701,3499746400,-109167110,2858979074,812756705,3037229701,987725627,"
         "812756705,0,812756705,6457853678")
ASIG = ("25252500,6512,1574452,214077758,78846,27018816,186980096,,,36397792,13261612,1983473,523616,1459857,,"
        "22497897,100729044,38821998,,41753558,,99894693,,3525746,,84559118,1084383,19106934,0,0,0,7435081,"
        "1218709,140848307,115571609,25276698,0,21500000,0,252")


def test_bank_row():
    b = e.bilant_special(BANCA.split(","), e.BANCA)
    assert b == {"cifra_afaceri": 6457853678, "profit_net": 812756705, "datorii": 3174794 + 0 + 99650255802,
                 "nr_salariati": None, "tip_raportare": "banca"}


def test_insurer_row():
    a = e.bilant_special(ASIG.split(","), e.ASIGURATOR)
    assert a == {"cifra_afaceri": 140848307, "profit_net": 21500000, "datorii": 84559118,
                 "nr_salariati": 252, "tip_raportare": "asigurator"}


def test_loss_is_negative_profit_for_insurers():
    p = ASIG.split(",")
    p[37], p[38] = "0", "5000"           # i36 profit net = 0, i37 pierdere netă = 5000
    assert e.bilant_special(p, e.ASIGURATOR)["profit_net"] == -5000


def test_short_row_gives_none_not_an_error():
    assert e.bilant_special(["1", "6419"], e.IFN)["cifra_afaceri"] is None
