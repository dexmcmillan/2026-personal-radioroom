# test_province.py
import csv, textwrap
from pathlib import Path
import pytest
import scan

@pytest.fixture
def patched_sources(tmp_path, monkeypatch):
    content = textwrap.dedent("""\
        Name of police service,url,link_selector,date_selector,province
        Test Police,https://example.com,,,Ontario
        Another Service,https://example2.com,,,British Columbia
    """)
    csv_file = tmp_path / "sources.csv"
    csv_file.write_text(content)
    monkeypatch.setattr(scan, "SOURCES_FILE", csv_file)
    return csv_file

def test_load_sources_returns_province(patched_sources):
    sources = scan.load_sources()
    assert len(sources) == 2
    assert sources[0]["province"] == "Ontario"
    assert sources[1]["province"] == "British Columbia"

def test_load_sources_province_missing_is_empty_string(tmp_path, monkeypatch):
    content = textwrap.dedent("""\
        Name of police service,url,link_selector,date_selector
        Old Format Police,https://example.com,,,
    """)
    csv_file = tmp_path / "sources.csv"
    csv_file.write_text(content)
    monkeypatch.setattr(scan, "SOURCES_FILE", csv_file)
    sources = scan.load_sources()
    assert sources[0].get("province", "") == ""
