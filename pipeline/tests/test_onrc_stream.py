"""Citirea dump-urilor ONRC: linii din bucăți de octeți și mărimea totală din antete (fără rețea)."""

from pipeline import onrc_stream as o


def test_lines_survive_chunk_boundaries_and_count_bytes():
    text = "CUI^DENUMIRE\r\n1^ȘANTIER SRL\r\n2^ÎNTREPRINDERE\n3^fără sfârșit de linie"
    raw = text.encode("utf-8")
    for pas in (1, 3, 7, len(raw)):                     # inclusiv tăieturi în mijlocul unui caracter
        contor = [0]
        got = list(o.linii((raw[i:i + pas] for i in range(0, len(raw), pas)), contor))
        assert got == ["CUI^DENUMIRE", "1^ȘANTIER SRL", "2^ÎNTREPRINDERE", "3^fără sfârșit de linie"]
        assert contor[0] == len(raw)


def _set(id_, titlu, *fisiere, org="onrc"):
    return {"id": id_, "title": titlu, "organization": {"name": org},
            "resources": [{"name": f"{f}.CSV", "url": f"https://x/{id_}/{f.lower()}.csv"} for f in fisiere]}


def test_set_date_from_title():
    from datetime import date
    assert o.data_setului("Firme înregistrate la Registrul Comerțului până la data de 04.11.2026") == date(2026, 11, 4)
    assert o.data_setului("Firme inregistrate la Registrul Comertului pana la data de 3.6.2026") == date(2026, 6, 3)
    assert o.data_setului("Bugete locale 2026") is None


def test_picks_newest_complete_set_by_title_date_not_list_order():
    t = "Firme înregistrate la Registrul Comerțului până la data de {}"
    pachete = [
        _set("iun", t.format("03.06.2026"), "OD_FIRME", "OD_CAEN_AUTORIZAT"),
        _set("nov", t.format("04.11.2026"), "OD_FIRME"),                       # incomplet: sărit
        _set("oct", t.format("19.10.2026"), "OD_FIRME", "OD_CAEN_AUTORIZAT"),
        _set("alt", t.format("01.12.2026"), "OD_FIRME", "OD_CAEN_AUTORIZAT", org="altcineva"),
    ]
    p, d, urls = o.alege_setul(pachete, ["OD_FIRME", "od_caen_autorizat"])
    assert p["id"] == "oct" and d.month == 10
    assert urls == {"OD_FIRME": "https://x/oct/od_firme.csv", "OD_CAEN_AUTORIZAT": "https://x/oct/od_caen_autorizat.csv"}


def test_no_complete_set_fails():
    import pytest
    with pytest.raises(SystemExit):
        o.alege_setul([_set("a", "Registrul Comerțului până la data de 01.01.2026", "OD_FIRME")], ["OD_CAEN_AUTORIZAT"])


def test_total_size_from_headers():
    assert o.marime_totala({"Content-Range": "bytes 0-334855885/334855886"}) == 334855886
    assert o.marime_totala({"Content-Length": "120"}) == 120
    assert o.marime_totala({}) == 0
