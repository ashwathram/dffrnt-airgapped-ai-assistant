import pytest

from dffrnt_assistant.ingest.loaders import load_file, read_csv, read_text_or_md, read_xlsx


def test_text_splits_into_paragraph_sections(tmp_path):
    path = tmp_path / "a.txt"
    path.write_text("Hello world.\n\nSecond paragraph here.")
    doc = read_text_or_md(path)
    assert doc["file_type"] == "txt"
    assert doc["filename"] == "a.txt"
    assert len(doc["sections"]) == 2


def test_csv_becomes_tab_separated_text(tmp_path):
    path = tmp_path / "d.csv"
    path.write_text("name,role\nsarah,eng\n")
    doc = read_csv(path)
    assert "name\trole" in doc["text"]
    assert "sarah\teng" in doc["text"]
    assert doc["file_type"] == "csv"


def test_csv_strips_empty_cells_and_blank_rows(tmp_path):
    path = tmp_path / "e.csv"
    path.write_text("a,,c\n,,\nx,,z\n")
    doc = read_csv(path)
    assert doc["text"].splitlines() == ["a\tc", "x\tz"]


def test_xlsx_strips_empty_cells(tmp_path):
    pytest.importorskip("openpyxl")
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["a", None, "c"])
    sheet.append([None, None, None])
    sheet.append(["x", "", "z"])
    path = tmp_path / "e.xlsx"
    workbook.save(path)

    doc = read_xlsx(path)
    assert doc["text"].splitlines() == ["a\tc", "x\tz"]


def test_load_file_dispatch_and_unsupported(tmp_path):
    md = tmp_path / "a.md"
    md.write_text("# Title\n\nBody text.")
    assert load_file(str(md))["file_type"] == "md"

    bogus = tmp_path / "x.zip"
    bogus.write_bytes(b"PK\x03\x04")
    with pytest.raises(RuntimeError):
        load_file(str(bogus))


def test_xlsx_reads_cells(tmp_path):
    pytest.importorskip("openpyxl")
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "People"
    sheet.append(["name", "role"])
    sheet.append(["sarah", "engineer"])
    path = tmp_path / "b.xlsx"
    workbook.save(path)

    doc = read_xlsx(path)
    assert "sarah" in doc["text"]
    assert doc["file_type"] == "xlsx"
