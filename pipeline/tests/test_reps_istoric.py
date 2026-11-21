"""Istoricul reprezentanților legali între dump-uri ONRC (fără rețea)."""

from pipeline.reps_istoric import combina, data_dump, disparute

IUN, NOI, FEB = "2026-06-03", "2026-11-04", "2027-02-01"


def _r(nume, cal="administrator"):
    return {"nume": nume, "calitate": cal}


def test_data_dump():
    assert data_dump("ONRC până la 04.11.2026 (set c2c8)") == NOI
    assert data_dump(None) is None and data_dump("fără dată") is None


def test_prima_rulare_fara_istoric():
    out = combina([], None, {1: [_r("POPESCU ION")]}, IUN, {1: "A SRL"})
    assert out == [{"cui": 1, "denumire": "A SRL",
                    "reprezentanti": [{"nume": "POPESCU ION", "calitate": "administrator", "vazut_din": IUN}]}]


def test_schimbare_de_administrator():
    prev = combina([], None, {1: [_r("POPESCU ION"), _r("IONESCU ANA", "lichidator")]}, IUN, {1: "A SRL"})
    out = combina(prev, IUN, {1: [_r("IONESCU ANA", "lichidator"), _r("VASILE DAN")]}, NOI, {})
    c = out[0]
    assert c["denumire"] == "A SRL"
    assert {r["nume"]: r for r in c["reprezentanti"]} == {
        "IONESCU ANA": {"nume": "IONESCU ANA", "calitate": "lichidator", "vazut_din": IUN},
        "VASILE DAN": {"nume": "VASILE DAN", "calitate": "administrator", "vazut_din": NOI, "aparut_dupa": IUN}}
    assert c["fosti"] == [{"nume": "POPESCU ION", "calitate": "administrator", "vazut_din": IUN,
                           "vazut_pana_la": IUN, "absent_din": NOI}]
    # la următorul dump istoricul se păstrează, iar datele inițiale nu se pierd
    out2 = combina(out, NOI, {1: [_r("VASILE DAN")]}, FEB, {})
    c2 = out2[0]
    assert [f["nume"] for f in c2["fosti"]] == ["POPESCU ION", "IONESCU ANA"]
    assert c2["fosti"][1] == {"nume": "IONESCU ANA", "calitate": "lichidator", "vazut_din": IUN,
                              "vazut_pana_la": NOI, "absent_din": FEB}
    assert c2["reprezentanti"][0]["aparut_dupa"] == IUN and c2["reprezentanti"][0]["vazut_din"] == NOI


def test_aceeasi_persoana_scrisa_cu_sedila_nu_e_schimbare():
    prev = combina([], None, {1: [_r("POPESCU ŞTEFAN")]}, IUN, {})
    out = combina(prev, IUN, {1: [_r("Popescu  Ștefan")]}, NOI, {})
    assert "fosti" not in out[0] and out[0]["reprezentanti"][0]["vazut_din"] == IUN
    # diacritice adăugate și cratimă în loc de spațiu: tot aceeași persoană; se afișează forma nouă
    prev = combina([], None, {1: [_r("FORNA CALIN VASILE"), _r("ALBU CĂLIN MIRCEA")]}, IUN, {})
    out = combina(prev, IUN, {1: [_r("FORNA CĂLIN VASILE"), _r("ALBU CĂLIN-MIRCEA")]}, NOI, {})
    assert "fosti" not in out[0]
    assert [r["nume"] for r in out[0]["reprezentanti"]] == ["FORNA CĂLIN VASILE", "ALBU CĂLIN-MIRCEA"]


def test_firma_noua_in_acoperire_nu_primeste_aparut_dupa():
    out = combina([], IUN, {2: [_r("X")]}, NOI, {})
    assert out[0]["reprezentanti"] == [{"nume": "X", "calitate": "administrator", "vazut_din": NOI}]


def test_firma_disparuta_ramane_cu_fosti():
    prev = combina([], None, {1: [_r("A")], 2: [_r("B")]}, IUN, {})
    out = combina(prev, IUN, {1: [_r("A")]}, NOI, {})
    assert out[1] == {"cui": 2, "denumire": "", "reprezentanti": [],
                      "fosti": [{"nume": "B", "calitate": "administrator", "vazut_din": IUN,
                                 "vazut_pana_la": IUN, "absent_din": NOI}]}
    assert disparute(prev, {1: [_r("A")]}) == 1
    # rulare repetată pe același dump: nicio schimbare nouă, dar istoricul rămâne
    again = combina(out, NOI, {1: [_r("A")]}, NOI, {})
    assert again == out


def test_acelasi_dump_nu_inregistreaza_schimbari():
    prev = combina([], None, {1: [_r("A"), _r("B")]}, NOI, {})
    out = combina(prev, NOI, {1: [_r("A")]}, NOI, {})
    assert "fosti" not in out[0] and [r["nume"] for r in out[0]["reprezentanti"]] == ["A"]
