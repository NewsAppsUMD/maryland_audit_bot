"""Tests for pure functions in scraper.py."""
import scraper


class TestExtractFileIdFromUrl:
    def test_extracts_file_id(self):
        url = "https://www.ola.state.md.us/Report/GetReport?fileId=abc123"
        assert scraper.extract_file_id_from_url(url) == "abc123"

    def test_extracts_file_id_with_extra_params(self):
        url = "https://www.ola.state.md.us/Report/GetReport?fileId=abc123&other=1"
        assert scraper.extract_file_id_from_url(url) == "abc123"

    def test_no_file_id_param(self):
        assert scraper.extract_file_id_from_url("https://example.com/report") is None

    def test_none_url(self):
        assert scraper.extract_file_id_from_url(None) is None

    def test_empty_url(self):
        assert scraper.extract_file_id_from_url("") is None


class TestConvertDateToIso:
    def test_converts_valid_date(self):
        assert scraper.convert_date_to_iso("03/15/2025") == "2025-03-15"

    def test_converts_single_digit_month_day(self):
        assert scraper.convert_date_to_iso("1/5/2024") == "2024-01-05"

    def test_returns_original_on_invalid_date(self):
        assert scraper.convert_date_to_iso("not a date") == "not a date"

    def test_returns_original_on_iso_input(self):
        # Already-ISO dates don't match MM/DD/YYYY, so they pass through
        assert scraper.convert_date_to_iso("2025-03-15") == "2025-03-15"

    def test_returns_original_on_empty_string(self):
        assert scraper.convert_date_to_iso("") == ""


class TestCreateReportKey:
    def test_uses_url_when_present(self):
        report = {"url": "https://example.com/r?fileId=1", "title": "T", "date": "2025-01-01"}
        assert scraper.create_report_key(report) == "https://example.com/r?fileId=1"

    def test_falls_back_to_title_and_date(self):
        report = {"url": None, "title": "Some Audit", "date": "2025-01-01"}
        assert scraper.create_report_key(report) == "Some Audit__2025-01-01"

    def test_missing_url_key(self):
        report = {"title": "Some Audit", "date": "2025-01-01"}
        assert scraper.create_report_key(report) == "Some Audit__2025-01-01"

    def test_missing_everything(self):
        assert scraper.create_report_key({}) == "__"
