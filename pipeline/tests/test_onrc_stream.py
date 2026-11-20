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


class _Resp:
    def __init__(self, status, headers, parts, rupe=False):
        self.status_code, self.headers, self.parts, self.rupe = status, headers, parts, rupe

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def raise_for_status(self):
        pass

    def iter_content(self, chunk_size):
        yield from self.parts
        if self.rupe:
            import requests
            raise requests.exceptions.ChunkedEncodingError("rupt")


def _server(monkeypatch, data: bytes, taieturi: list[int], mod="range"):
    """Server fals care închide conexiunea după fiecare poziție din `taieturi`.

    mod: "range" = respectă Range (206); "de_la_zero" = ca data.gov.ro, 200 + tot fișierul de la 0;
    "sare" = răspunde de la alt octet decât cel cerut.
    """
    cereri = []

    def get(url, headers, **kw):
        cerut = int(headers["Range"].split("=")[1].rstrip("-"))
        cereri.append(cerut)
        start = {"range": cerut, "de_la_zero": 0, "sare": cerut + 3 if cerut else 0}[mod]
        stop = next((t for t in taieturi if t > cerut), len(data))
        h = {"Content-Range": f"bytes {start}-{len(data) - 1}/{len(data)}"}
        parti = [data[start:stop][i:i + 4] for i in range(0, stop - start, 4)]   # bucăți mici, ca la rețea
        return _Resp(200 if mod == "de_la_zero" else 206, h, parti, rupe=stop < len(data) and stop == taieturi[-1])

    monkeypatch.setattr(o.requests, "get", get)
    return cereri


def test_resumes_after_dropped_connection(monkeypatch):
    data = "CUI^DENUMIRE\n1^ȘANTIER SRL\n2^ÎNTREPRINDERE\n3^ULTIMA\n".encode("utf-8")
    cereri = _server(monkeypatch, data, [9, 20])      # tăiat în mijlocul lui „Ș”, apoi cu excepție
    rows = [p for p, _ in o.randuri("https://x/od_firme.csv")]
    assert rows == [["1", "ȘANTIER SRL"], ["2", "ÎNTREPRINDERE"], ["3", "ULTIMA"]]
    assert cereri == [0, 9, 20]


def test_resumes_when_server_restarts_from_zero(monkeypatch):
    data = "CUI^DENUMIRE\n1^ȘANTIER SRL\n2^ÎNTREPRINDERE\n3^ULTIMA\n".encode("utf-8")
    cereri = _server(monkeypatch, data, [9, 30], mod="de_la_zero")
    rows = [p for p, _ in o.randuri("https://x/od_firme.csv")]
    assert rows == [["1", "ȘANTIER SRL"], ["2", "ÎNTREPRINDERE"], ["3", "ULTIMA"]]
    assert cereri == [0, 9, 30]


def test_refuses_when_resume_would_skip_bytes(monkeypatch):
    import pytest
    data = b"CUI^DENUMIRE\n1^A\n2^B\n3^C\n"
    _server(monkeypatch, data, [10], mod="sare")
    with pytest.raises(o.DescarcareIncompleta):
        list(o.randuri("https://x/od_firme.csv"))


def test_total_size_from_headers():
    assert o.marime_totala({"Content-Range": "bytes 0-334855885/334855886"}) == 334855886
    assert o.marime_totala({"Content-Length": "120"}) == 120
    assert o.marime_totala({}) == 0
