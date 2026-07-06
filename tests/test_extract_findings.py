"""Tests for the pure functions in extract_findings.py. No Ollama calls."""
import pytest

import extract_findings as ef
from schemas import DollarAmount, Finding, ReportExtraction


HEADER = (
    "Title: Test Agency - Fiscal Year Ended June 30, 2020\n"
    "Date: 01/15/2021\n"
    "Type: Fiscal Compliance\n"
    "URL: https://example.com/GetReport?fileId=abc\n"
    "Extracted: 2025-06-16T22:37:14\n"
    + "-" * 80 + "\n\n"
)

BODY = """--- Page 1 ---
Audit Report
Test Agency
Fiscal Year Ended June 30, 2020
OFFICE OF LEGISLATIVE AUDITS

--- Page 2 ---
For further information concerning this report contact:
Department of Legislative Services
The Office of Legislative Audits operates a Fraud Hotline to report
fraud, waste, or abuse involving State of Maryland government resources.
The Department of Legislative Services does not discriminate on the basis of age, ancestry, color,
creed, marital status, national origin, race, religion, gender.

--- Page 3 ---
Table of Contents
Finding 1 - Cash receipts were not deposited timely
Finding 2 - Payroll adjustments lacked approval

--- Page 4 ---
Status of Findings From Preceding Audit Report
Our audit included a review of the 3 findings in our preceding audit
report dated June 19, 2019. We determined that 1 finding was repeated.

Findings and Recommendations

Finding 1
Cash receipts totaling $1,234 were not deposited timely.
Analysis
Deposits of cash receipts were made up to 30 days late. Amounts
involved totaled $11.3 million during the audit period.
Recommendation 1
We recommend that the Agency deposit receipts timely (repeat).

Finding 2
Payroll adjustments lacked supervisory approval.
Analysis
We tested 10 payroll adjustments totaling $5,678.90 and found none
were approved.
Recommendation 2
We recommend supervisory approval of payroll adjustments.
"""

RAW = HEADER + BODY


class TestSplitHeader:
    def test_splits_header_and_body(self):
        header, body = ef.split_header(RAW)
        assert header.startswith("Title: Test Agency")
        assert header.rstrip().endswith("-" * 80)
        assert body.startswith("--- Page 1 ---")

    def test_no_header_returns_text_unchanged(self):
        header, body = ef.split_header(BODY)
        assert header == ""
        assert body == BODY

    def test_dashes_deep_in_body_not_treated_as_header(self):
        text = "some text\n" + "x" * 3000 + "\n" + "-" * 80 + "\nmore"
        header, body = ef.split_header(text)
        assert header == ""
        assert body == text


class TestPreprocess:
    def test_strips_page_markers(self):
        clean, _, _ = ef.preprocess(RAW)
        assert "--- Page" not in clean

    def test_strips_boilerplate_page(self):
        clean, _, _ = ef.preprocess(RAW)
        assert "Fraud Hotline" not in clean
        assert "does not discriminate" not in clean

    def test_keeps_findings_content(self):
        clean, _, _ = ef.preprocess(RAW)
        assert "Cash receipts totaling $1,234 were not deposited timely." in clean
        assert "Status of Findings From Preceding Audit Report" in clean

    def test_counts_findings(self):
        _, count, _ = ef.preprocess(RAW)
        assert count == 2

    def test_estimates_tokens(self):
        clean, _, tokens = ef.preprocess(RAW)
        assert tokens == len(clean) // 4

    def test_boilerplate_page_with_finding_heading_is_kept(self):
        text = ("--- Page 1 ---\noperates a Fraud Hotline\nFinding 1\n"
                "The agency misused hotline funds.\n")
        clean = ef.strip_boilerplate(text)
        assert "Finding 1" in clean


class TestCountFindingsHeadings:
    def test_toc_entries_not_counted(self):
        assert ef.count_findings_headings("Finding 1 - Cash receipts were bad\n") == 0

    def test_heading_alone_counted(self):
        assert ef.count_findings_headings("Finding 1\nCash was missing.\n") == 1

    def test_asterisk_marked_heading_counted(self):
        assert ef.count_findings_headings("Finding 3 *\ntext\n* Finding 4\ntext\n") == 2

    def test_duplicate_numbers_counted_once(self):
        text = "Finding 1\ntext\nFinding 1\ntext\nFinding 2\ntext\n"
        assert ef.count_findings_headings(text) == 2


class TestDedupeTexts:
    def test_groups_by_body_hash(self, tmp_path):
        body = "--- Page 1 ---\nSame report body.\n"
        header_a = HEADER
        header_b = HEADER.replace("01/15/2021", "03/20/2013")  # different metadata
        (tmp_path / "aaa.txt").write_text(header_a + body)
        (tmp_path / "bbb.txt").write_text(header_b + body)
        (tmp_path / "ccc.txt").write_text(HEADER + "--- Page 1 ---\nDifferent body.\n")

        groups, hash_by_fid = ef.dedupe_texts(["bbb", "aaa", "ccc"], text_dir=tmp_path)

        assert len(groups) == 2
        assert hash_by_fid["aaa"] == hash_by_fid["bbb"]
        assert hash_by_fid["aaa"] != hash_by_fid["ccc"]
        # canonical (first) member is the sorted-first file_id
        assert groups[hash_by_fid["aaa"]] == ["aaa", "bbb"]

    def test_missing_file_skipped(self, tmp_path):
        (tmp_path / "aaa.txt").write_text(HEADER + "body")
        groups, hash_by_fid = ef.dedupe_texts(["aaa", "nope"], text_dir=tmp_path)
        assert "nope" not in hash_by_fid
        assert len(groups) == 1


class TestDollarAmountInText:
    def test_comma_formatted(self):
        assert ef.dollar_amount_in_text(1234.0, "receipts totaling $1,234 were")

    def test_plain_digits(self):
        assert ef.dollar_amount_in_text(1234.0, "totaling 1234 dollars")

    def test_cents(self):
        assert ef.dollar_amount_in_text(5678.90, "adjustments totaling $5,678.90")

    def test_millions_phrasing(self):
        assert ef.dollar_amount_in_text(11300000.0, "totaled $11.3 million during")

    def test_billions_phrasing(self):
        assert ef.dollar_amount_in_text(2500000000.0, "spent $2.5 billion on")

    def test_absent_amount(self):
        assert not ef.dollar_amount_in_text(999999.0, "no such figure here")


class TestValidDate:
    def test_valid(self):
        assert ef.valid_date("2020-06-30")

    def test_bad_format(self):
        assert not ef.valid_date("06/30/2020")

    def test_none(self):
        assert not ef.valid_date(None)

    def test_year_too_early(self):
        assert not ef.valid_date("1990-01-01")

    def test_year_too_late(self):
        assert not ef.valid_date("2030-01-01")


def make_extraction(**overrides):
    finding = Finding(
        number=1,
        title="Cash receipts totaling $1,234 were not deposited timely.",
        description="Deposits were late.",
        category="cash_receipts",
        is_repeat=True,
        prior_finding_number=None,
        dollar_amounts=[DollarAmount(amount=1234.0, context="late deposits")],
        recommendation="Deposit timely.",
        agency_agrees=True,
        agency_completion_date=None,
    )
    fields = dict(
        agency_name="Test Agency",
        parent_department=None,
        report_date="2021-01-15",
        audit_period_start="2019-07-01",
        audit_period_end="2020-06-30",
        findings=[finding],
        prior_findings_count=3,
        prior_findings_repeated=1,
        criminal_referral=False,
        fraud_hotline_origin=False,
        agency_response_summary="The agency agreed.",
        total_dollar_impact=None,
        extraction_notes=None,
    )
    fields.update(overrides)
    return ReportExtraction(**fields)


class TestValidateExtraction:
    def test_clean_extraction_when_counts_match(self):
        extraction = make_extraction()
        raw = "Finding 1\nCash receipts totaling $1,234 (repeat)\n"
        assert ef.validate_extraction(extraction, raw, 1) == []

    def test_findings_count_mismatch(self):
        flags = ef.validate_extraction(make_extraction(), "some text repeat 1,234", 3)
        assert any("findings_count_mismatch" in f for f in flags)

    def test_dollar_amount_not_in_text(self):
        flags = ef.validate_extraction(make_extraction(), "no numbers here repeat", 1)
        assert any("dollar_amount_not_in_text" in f for f in flags)

    def test_criminal_referral_without_mention(self):
        extraction = make_extraction(criminal_referral=True)
        flags = ef.validate_extraction(extraction, "1,234 repeat", 1)
        assert any("criminal_referral_true" in f for f in flags)

    def test_criminal_mention_without_referral(self):
        raw = "referred to the Criminal Division 1,234 repeat"
        flags = ef.validate_extraction(make_extraction(), raw, 1)
        assert any("criminal_division_in_text" in f for f in flags)

    def test_bad_date_flagged(self):
        extraction = make_extraction(report_date="January 2021")
        flags = ef.validate_extraction(extraction, "1,234 repeat", 1)
        assert any("bad_date: report_date" in f for f in flags)

    def test_repeat_claimed_but_no_repeat_language(self):
        flags = ef.validate_extraction(make_extraction(), "text with 1,234 only", 1)
        assert any("no_repeat_language" in f for f in flags)


class TestSplitIntoChunks:
    def test_small_text_single_chunk(self):
        assert ef.split_into_chunks("short text", max_chars=100) == ["short text"]

    def test_chunks_reassemble_to_original(self):
        prefix = "Transmittal letter and Status of Preceding Findings.\n" * 20
        sections = "".join(
            f"Finding {n}\n" + ("Analysis text. " * 100) + "\n" for n in range(1, 8)
        )
        text = prefix + sections
        chunks = ef.split_into_chunks(text, max_chars=3000)
        assert len(chunks) > 1
        assert "".join(chunks) == text

    def test_chunk_one_contains_transmittal(self):
        prefix = "Transmittal letter text.\n" * 50
        sections = "".join(
            f"Finding {n}\n" + ("Analysis. " * 200) + "\n" for n in range(1, 6)
        )
        chunks = ef.split_into_chunks(prefix + sections, max_chars=4000)
        assert chunks[0].startswith("Transmittal letter text.")

    def test_later_chunks_start_on_finding_boundaries(self):
        prefix = "Letter.\n" * 10
        sections = "".join(
            f"Finding {n}\n" + ("Analysis. " * 200) + "\n" for n in range(1, 6)
        )
        chunks = ef.split_into_chunks(prefix + sections, max_chars=3000)
        for chunk in chunks[1:]:
            assert chunk.lstrip().startswith("Finding")

    def test_no_finding_boundaries_hard_splits(self):
        text = "x" * 250
        chunks = ef.split_into_chunks(text, max_chars=100)
        assert "".join(chunks) == text
        assert all(len(c) <= 100 for c in chunks)
