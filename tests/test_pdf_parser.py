"""Tests for pure functions in pdf_parser.py."""
import hashlib

import pdf_parser


class TestGetPdfFilenameFromReport:
    def test_prefers_file_id(self):
        report = {
            "file_id": "abc123",
            "url": "https://www.ola.state.md.us/Report/GetReport?fileId=other",
        }
        assert pdf_parser.get_pdf_filename_from_report(report) == "abc123.pdf"

    def test_falls_back_to_url_file_id(self):
        report = {"url": "https://www.ola.state.md.us/Report/GetReport?fileId=xyz789"}
        assert pdf_parser.get_pdf_filename_from_report(report) == "xyz789.pdf"

    def test_empty_file_id_falls_back_to_url(self):
        report = {
            "file_id": None,
            "url": "https://www.ola.state.md.us/Report/GetReport?fileId=xyz789",
        }
        assert pdf_parser.get_pdf_filename_from_report(report) == "xyz789.pdf"

    def test_url_without_file_id_uses_hash(self):
        url = "https://example.com/some/report.pdf"
        expected_hash = hashlib.md5(url.encode()).hexdigest()[:12]
        report = {"url": url}
        assert pdf_parser.get_pdf_filename_from_report(report) == f"report_{expected_hash}.pdf"

    def test_no_url_or_file_id(self):
        assert pdf_parser.get_pdf_filename_from_report({}) == "unknown_report.pdf"

    def test_none_url(self):
        assert pdf_parser.get_pdf_filename_from_report({"url": None}) == "unknown_report.pdf"
