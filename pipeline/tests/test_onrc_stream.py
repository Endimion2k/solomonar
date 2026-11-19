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


def test_total_size_from_headers():
    assert o.marime_totala({"Content-Range": "bytes 0-334855885/334855886"}) == 334855886
    assert o.marime_totala({"Content-Length": "120"}) == 120
    assert o.marime_totala({}) == 0
