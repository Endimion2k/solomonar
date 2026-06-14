"""Test offline pentru parserul harvesterului ANI (portal vechi)."""
import importlib.util
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_spec = importlib.util.spec_from_file_location(
    "harvest_ani", os.path.join(ROOT, "pipeline", "harvest_ani.py"))
hani = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hani)


# Un rând real din tabelul de rezultate (form:resultsTable_body), trunchiat la celulele cheie.
ROW_HTML = (
    '<table><tbody id="form:resultsTable_body">'
    '<tr class=" ui-datatable-even " id="form:resultsTable_row_0">'
    '<td><span id="form:resultsTable:0:numeCell">IOHANNIS GH KLAUS WERNER</span></td>'
    '<td><span id="form:resultsTable:0:institutieCell">Administratia Prezidentiala</span></td>'
    '<td><span id="form:resultsTable:0:functieCell">PreÈ\x99edintele RomÃ¢niei</span></td>'
    '<td><span id="form:resultsTable:0:localitateCell">Sectorul 6</span></td>'
    '<td><span id="form:resultsTable:0:judetCell">Bucuresti</span></td>'
    '<td><span id="form:resultsTable:0:dataCompletareCell">31.05.2023</span></td>'
    '<td><span id="form:resultsTable:0:tipDeclaratieCell">DeclaraÅ£ie de avere</span></td>'
    '<td><a href="/DownloadServlet?fileName=14636741_2283877_a.pdf'
    '&amp;uniqueIdentifier=NTNTARTLNE_14636741" target="_self">Vezi document</a></td>'
    '</tr></tbody></table>'
)


def test_parse_rows_extracts_metadata():
    rows = hani._parse_rows(ROW_HTML, "Iohannis", "numePrenume")
    assert len(rows) == 1
    r = rows[0]
    assert r["nume"] == "IOHANNIS GH KLAUS WERNER"
    assert r["institutie"] == "Administratia Prezidentiala"
    assert r["localitate"] == "Sectorul 6"
    assert r["judet"] == "Bucuresti"
    assert r["data_completare"] == "31.05.2023"


def test_parse_rows_fixes_double_encoded_diacritics():
    r = hani._parse_rows(ROW_HTML, "x", "numePrenume")[0]
    # "PreÈ™edintele RomÃ¢niei" (dublu-encodat) → "Președintele României"
    assert r["functie"] == "Președintele României"
    # "DeclaraÅ£ie de avere" → "Declarație de avere"
    assert r["tip_declaratie"] == "Declarație de avere"


def test_parse_rows_extracts_download_link():
    r = hani._parse_rows(ROW_HTML, "x", "numePrenume")[0]
    assert r["file_name"] == "14636741_2283877_a.pdf"
    assert r["unique_identifier"] == "NTNTARTLNE_14636741"
    assert r["unique_id"] == "14636741"
    assert r["download_url"].endswith(
        "DownloadServlet?fileName=14636741_2283877_a.pdf"
        "&uniqueIdentifier=NTNTARTLNE_14636741")


def test_parse_rows_empty_when_no_table():
    assert hani._parse_rows("<html>no results here</html>", "x", "numePrenume") == []


def test_fix_mojarra_does_not_corrupt_partial():
    # String fără markeri de dublu-encodare rămâne neschimbat (doar cedilă→virgulă).
    assert hani.fix_mojarra_utf8("Senatul Romaniei") == "Senatul Romaniei"
    assert hani.fix_mojarra_utf8("") == ""
