"""Tests for prototype/utils.py: agency matching and date formatting."""
import pytest

import utils


FAKE_REPORTS = [
    {"title": "Maryland Legal Services Corporation", "date": "2024-01-15"},
    {"title": "Legal Services Corporation Follow-up Review", "date": "2020-06-01"},
    {"title": "Office of the Public Defender", "date": "2023-03-10"},
    {"title": "Division of Occupational and Professional Licensing", "date": "2022-08-20"},
    {"title": "Department of Labor - Occupational and Professional Licensing", "date": "2019-05-05"},
    {"title": "Office of the Clerk of Circuit Court - Talbot County", "date": "2021-11-30"},
    {"title": "Clerk of Circuit Court - Anne Arundel County", "date": "2021-04-12"},
    {"title": "Office of the Register of Wills - Talbot County", "date": "2020-09-09"},
    {"title": "Register of Wills - Baltimore City", "date": "2018-02-14"},
    {"title": "Talbot County Public Schools", "date": "2023-07-01"},
    {"title": "Board of Education of Talbot County Schools", "date": "2017-10-25"},
    {"title": "Department of Health", "date": "2024-02-02"},
    {"title": "", "date": "2024-03-03"},
    {"date": "2024-04-04"},  # no title key at all
]


@pytest.fixture
def fake_reports(monkeypatch):
    """Patch load_reports_data so agency matching runs against fixture data."""
    monkeypatch.setattr(utils, "load_reports_data", lambda: FAKE_REPORTS)
    return FAKE_REPORTS


def titles(reports):
    return [r.get("title", "") for r in reports]


class TestGetReportsForAgency:
    def test_legal_services_matches_both_variants(self, fake_reports):
        results = titles(utils.get_reports_for_agency("Maryland Legal Services Corporation"))
        assert results == [
            "Maryland Legal Services Corporation",
            "Legal Services Corporation Follow-up Review",
        ]

    def test_public_defender(self, fake_reports):
        results = titles(utils.get_reports_for_agency("Office of the Public Defender"))
        assert results == ["Office of the Public Defender"]

    def test_licensing_matches_both_variants(self, fake_reports):
        results = titles(utils.get_reports_for_agency(
            "Division of Occupational and Professional Licensing"))
        assert results == [
            "Division of Occupational and Professional Licensing",
            "Department of Labor - Occupational and Professional Licensing",
        ]

    def test_talbot_clerk_requires_talbot_in_title(self, fake_reports):
        results = titles(utils.get_reports_for_agency(
            "Office of the Clerk of Circuit Court - Talbot County"))
        # The Anne Arundel clerk report must NOT match
        assert results == ["Office of the Clerk of Circuit Court - Talbot County"]

    def test_talbot_register_of_wills_requires_talbot(self, fake_reports):
        results = titles(utils.get_reports_for_agency(
            "Office of the Register of Wills - Talbot County"))
        # The Baltimore City register report must NOT match
        assert results == ["Office of the Register of Wills - Talbot County"]

    def test_talbot_schools_matches_variants(self, fake_reports):
        results = titles(utils.get_reports_for_agency("Talbot County Public Schools"))
        assert results == [
            "Talbot County Public Schools",
            "Board of Education of Talbot County Schools",
        ]

    def test_unknown_agency_returns_empty(self, fake_reports):
        assert utils.get_reports_for_agency("Department of Health") == []

    def test_all_test_agencies_have_patterns(self):
        # Every agency exposed by get_test_agencies must have matching rules
        for agency in utils.get_test_agencies():
            assert agency in utils.AGENCY_TITLE_PATTERNS


class TestFormatDateReadable:
    def test_valid_date(self):
        assert utils.format_date_readable("2025-03-15") == "March 15, 2025"

    def test_invalid_date_returned_unchanged(self):
        assert utils.format_date_readable("03/15/2025") == "03/15/2025"

    def test_empty_string(self):
        assert utils.format_date_readable("") == ""

    def test_garbage_string(self):
        assert utils.format_date_readable("Unknown Date") == "Unknown Date"
