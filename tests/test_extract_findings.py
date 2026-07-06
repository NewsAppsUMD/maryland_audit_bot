"""Tests for extract_findings.py. No Ollama calls: model interactions are
exercised through a stubbed llm.get_model."""
import argparse
import json

import pytest

import extract_findings as ef
from schemas import DollarAmount, Finding, FindingsChunk, ReportExtraction


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


def make_finding(number=1, **overrides):
    fields = dict(
        number=number,
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
    fields.update(overrides)
    return Finding(**fields)


def make_extraction(**overrides):
    finding = make_finding()
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

    def test_oversized_single_finding_is_hard_split(self):
        text = ("Transmittal letter.\n"
                + "Finding 1\n" + ("Analysis paragraph text.\n\n" * 100)
                + "Finding 2\nShort analysis.\n")
        chunks = ef.split_into_chunks(text, max_chars=800)
        assert all(len(c) <= 800 for c in chunks)
        assert "".join(chunks) == text

    def test_oversized_prefix_is_hard_split(self):
        prefix = "Transmittal letter paragraph.\n\n" * 100
        text = prefix + "Finding 1\nAnalysis.\n"
        chunks = ef.split_into_chunks(text, max_chars=500)
        assert all(len(c) <= 500 for c in chunks)
        assert "".join(chunks) == text
        assert chunks[0].startswith("Transmittal letter paragraph.")

    def test_hard_split_prefers_paragraph_boundaries(self):
        piece = "para one.\n\npara two.\n\npara three.\n\npara four."
        segments = ef._hard_split(piece, max_chars=25)
        assert "".join(segments) == piece
        assert all(len(s) <= 25 for s in segments)
        # splits land after blank lines, so segments start at paragraph starts
        assert segments[1].startswith("para")


class TestCountAsteriskFindings:
    def test_toc_and_heading_same_number_counted_once(self):
        text = ("* Finding 1 - Cash receipts were bad 9\n"
                "some text\n"
                "Finding 1 *\n"
                "Cash receipts were bad.\n")
        assert ef.count_asterisk_findings(text) == {"1"}

    def test_distinct_numbers_counted_separately(self):
        text = "* Finding 2\ntext\nFinding 5 *\ntext\n"
        assert ef.count_asterisk_findings(text) == {"2", "5"}

    def test_unmarked_findings_not_counted(self):
        assert ef.count_asterisk_findings("Finding 1\ntext\n") == set()


class TestWriteJsonAtomic:
    def test_writes_valid_json_without_tmp_leftover(self, tmp_path):
        path = tmp_path / "out.json"
        ef.write_json_atomic(path, {"a": 1})
        assert json.loads(path.read_text()) == {"a": 1}
        assert list(tmp_path.glob("*.tmp")) == []

    def test_overwrites_existing(self, tmp_path):
        path = tmp_path / "out.json"
        path.write_text("old")
        ef.write_json_atomic(path, [1, 2])
        assert json.loads(path.read_text()) == [1, 2]


class TestDollarAmountZero:
    def test_zero_does_not_match_arbitrary_digits(self):
        assert not ef.dollar_amount_in_text(0.0, "we tested 10 items in 2014")

    def test_zero_matches_explicit_zero(self):
        assert ef.dollar_amount_in_text(0.0, "a balance of $0 remained")


# --- Stubbed-LLM tests for extract() control flow ---

VALID_CHUNK_JSON = '{"findings": []}'
INVALID_JSON = "this is not json"
INVALID_SCHEMA_JSON = '{"findings": "not a list"}'


class StubResponse:
    def __init__(self, text):
        self._text = text

    def text(self):
        return self._text


class StubModel:
    """Pops scripted actions (a JSON string or an Exception) per model name."""

    def __init__(self, name, script, calls):
        self.name = name
        self._script = script
        self._calls = calls

    def prompt(self, prompt_text, system=None, schema=None, **options):
        self._calls.append({"model": self.name, "prompt": prompt_text,
                            "system": system, "schema": schema,
                            "options": options})
        action = self._script[self.name].pop(0)
        if isinstance(action, Exception):
            raise action
        return StubResponse(action)


@pytest.fixture
def stub_llm(monkeypatch):
    script = {}
    calls = []
    monkeypatch.setattr(ef.llm, "get_model",
                        lambda name: StubModel(name, script, calls))
    return script, calls


class TestExtractControlFlow:
    def test_success_first_attempt(self, stub_llm):
        script, calls = stub_llm
        script["prim"] = [VALID_CHUNK_JSON]
        result, model, attempts, error = ef.extract(
            "the prompt", FindingsChunk, "prim", "esc")
        assert result == FindingsChunk(findings=[])
        assert (model, attempts, error) == ("prim", 1, None)
        assert len(calls) == 1
        assert calls[0]["options"] == {"temperature": 0, "num_ctx": ef.NUM_CTX}
        assert "failed validation" not in calls[0]["prompt"]

    def test_repair_prompt_threads_error_back(self, stub_llm):
        script, calls = stub_llm
        script["prim"] = [INVALID_JSON, VALID_CHUNK_JSON]
        result, model, attempts, _ = ef.extract(
            "the prompt", FindingsChunk, "prim", "esc")
        assert result is not None
        assert (model, attempts) == ("prim", 2)
        repair_prompt = calls[1]["prompt"]
        assert repair_prompt.startswith("the prompt")
        assert "failed validation" in repair_prompt

    def test_schema_validation_error_also_repaired(self, stub_llm):
        script, calls = stub_llm
        script["prim"] = [INVALID_SCHEMA_JSON, VALID_CHUNK_JSON]
        result, model, attempts, _ = ef.extract(
            "p", FindingsChunk, "prim", "esc")
        assert result is not None
        assert attempts == 2

    def test_escalates_after_primary_exhausted(self, stub_llm):
        script, calls = stub_llm
        script["prim"] = [INVALID_JSON] * 3
        script["esc"] = [VALID_CHUNK_JSON]
        result, model, attempts, _ = ef.extract("p", FindingsChunk, "prim", "esc")
        assert result is not None
        assert (model, attempts) == ("esc", 4)
        assert [c["model"] for c in calls] == ["prim"] * 3 + ["esc"]
        # repair error does not leak across models: escalation starts fresh
        assert "failed validation" not in calls[3]["prompt"]

    def test_non_validation_error_breaks_to_escalation(self, stub_llm):
        script, calls = stub_llm
        script["prim"] = [RuntimeError("connection refused")]
        script["esc"] = [VALID_CHUNK_JSON]
        result, model, attempts, _ = ef.extract("p", FindingsChunk, "prim", "esc")
        assert result is not None
        assert (model, attempts) == ("esc", 2)

    def test_all_models_fail(self, stub_llm):
        script, calls = stub_llm
        script["prim"] = [INVALID_JSON] * 3
        script["esc"] = [INVALID_JSON] * 3
        result, model, attempts, error = ef.extract("p", FindingsChunk, "prim", "esc")
        assert result is None
        assert model is None
        assert attempts == 6
        assert error

    def test_same_primary_and_escalation_not_retried_twice(self, stub_llm):
        script, calls = stub_llm
        script["only"] = [INVALID_JSON] * 3
        result, model, attempts, error = ef.extract("p", FindingsChunk, "only", "only")
        assert result is None
        assert attempts == 3


class TestExtractReportChunking:
    def fake_extract_factory(self, responses, seen):
        def fake_extract(prompt_text, schema, model_name, escalation_model_name,
                         system_prompt=ef.SYSTEM_PROMPT):
            seen.append({"prompt": prompt_text, "schema": schema,
                         "system": system_prompt})
            return responses.pop(0)
        return fake_extract

    def test_small_text_single_call(self, monkeypatch):
        seen = []
        responses = [(make_extraction(), "m", 1, None)]
        monkeypatch.setattr(ef, "extract", self.fake_extract_factory(responses, seen))
        result, models, attempts, error = ef.extract_report("short text", "m", "big")
        assert result is not None
        assert len(seen) == 1
        assert seen[0]["schema"] is ReportExtraction

    def test_chunk_merge_keeps_chunk1_version_and_sorts(self, monkeypatch):
        monkeypatch.setattr(ef, "CHUNK_THRESHOLD_CHARS", 5)
        monkeypatch.setattr(ef, "split_into_chunks", lambda text: ["c1", "c2"])
        chunk1 = make_extraction(findings=[
            make_finding(3, title="three from chunk1"),
            make_finding(1, title="one from chunk1"),
        ])
        chunk2 = FindingsChunk(findings=[
            make_finding(3, title="three DUPLICATE from chunk2"),
            make_finding(2, title="two from chunk2"),
        ])
        seen = []
        responses = [(chunk1, "m", 1, None), (chunk2, "m", 2, None)]
        monkeypatch.setattr(ef, "extract", self.fake_extract_factory(responses, seen))

        result, models, attempts, error = ef.extract_report("x" * 10, "m", "big")

        assert error is None
        assert [f.number for f in result.findings] == [1, 2, 3]
        # chunk 1's version of finding 3 wins (setdefault semantics)
        assert result.findings[2].title == "three from chunk1"
        assert attempts == 3
        assert models == "m"
        assert len(seen) == 2
        assert seen[1]["schema"] is FindingsChunk
        assert "LATER PORTION" in seen[1]["system"]

    def test_chunk_failure_fails_whole_report(self, monkeypatch):
        monkeypatch.setattr(ef, "CHUNK_THRESHOLD_CHARS", 5)
        monkeypatch.setattr(ef, "split_into_chunks", lambda text: ["c1", "c2"])
        responses = [(make_extraction(), "m", 1, None), (None, None, 6, "boom")]
        monkeypatch.setattr(ef, "extract", self.fake_extract_factory(responses, []))

        result, models, attempts, error = ef.extract_report("x" * 10, "m", "big")

        assert result is None
        assert attempts == 7
        assert "chunk 2 failed" in error

    def test_chunk1_failure_short_circuits(self, monkeypatch):
        monkeypatch.setattr(ef, "CHUNK_THRESHOLD_CHARS", 5)
        monkeypatch.setattr(ef, "split_into_chunks", lambda text: ["c1", "c2"])
        seen = []
        responses = [(None, None, 6, "boom")]
        monkeypatch.setattr(ef, "extract", self.fake_extract_factory(responses, seen))

        result, models, attempts, error = ef.extract_report("x" * 10, "m", "big")

        assert result is None
        assert len(seen) == 1  # chunk 2 never attempted


# --- process_reports integration (tmp dirs, stubbed extract_report) ---

SHARED_BODY = ("--- Page 1 ---\nShared report body.\n\nFinding 1\n"
               "Cash receipts totaling $1,234 were not deposited timely.\n"
               "Analysis (repeat)\n")
UNIQUE_BODY = ("--- Page 1 ---\nUnique report body.\n\nFinding 1\n"
               "Cash receipts totaling $1,234 were not deposited timely.\n"
               "Analysis (repeat)\n")


class PipelineEnv:
    def __init__(self, tmp_path):
        self.text_dir = tmp_path / "text"
        self.ext_dir = tmp_path / "extractions"
        self.failures = tmp_path / "failures.json"


@pytest.fixture
def pipeline_env(tmp_path, monkeypatch):
    env = PipelineEnv(tmp_path)
    env.text_dir.mkdir()
    monkeypatch.setattr(ef, "TEXT_DIR", env.text_dir)
    monkeypatch.setattr(ef, "EXTRACTIONS_DIR", env.ext_dir)
    monkeypatch.setattr(ef, "FAILURES_FILE", env.failures)
    # aaa and bbb share a body (duplicates); ccc is unique
    (env.text_dir / "aaa.txt").write_text(HEADER + SHARED_BODY)
    (env.text_dir / "bbb.txt").write_text(
        HEADER.replace("01/15/2021", "03/20/2013") + SHARED_BODY)
    (env.text_dir / "ccc.txt").write_text(HEADER + UNIQUE_BODY)
    index = {fid: {"file_id": fid, "title": f"Report {fid}",
                   "type": "Fiscal Compliance"}
             for fid in ("aaa", "bbb", "ccc")}
    monkeypatch.setattr(ef, "load_index", lambda filename="ola_reports.json": index)
    return env


def make_args(**overrides):
    defaults = dict(limit=None, file_id=None, model="stub", escalation_model="big",
                    report_type=None, force=False, retry_failures=False)
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def stub_extract_report(calls, result_factory=None):
    def fake(clean_text, model_name, escalation_model_name):
        calls.append(clean_text)
        if result_factory:
            return result_factory(clean_text)
        return make_extraction(), model_name, 1, None
    return fake


def read_output(env, fid):
    return json.loads((env.ext_dir / f"{fid}.json").read_text())


class TestProcessReports:
    def test_extracts_once_per_group_and_fans_out(self, pipeline_env, monkeypatch):
        calls = []
        monkeypatch.setattr(ef, "extract_report", stub_extract_report(calls))
        ef.process_reports(make_args())

        assert len(calls) == 2  # aaa/bbb group once, ccc once
        a, b, c = (read_output(pipeline_env, fid) for fid in ("aaa", "bbb", "ccc"))
        assert a["duplicate_of"] is None
        assert b["duplicate_of"] == "aaa"
        assert a["content_hash"] == b["content_hash"]
        assert c["duplicate_of"] is None
        assert c["content_hash"] != a["content_hash"]
        assert a["extraction"]["findings"][0]["number"] == 1

    def test_rerun_skips_everything(self, pipeline_env, monkeypatch):
        calls = []
        monkeypatch.setattr(ef, "extract_report", stub_extract_report(calls))
        ef.process_reports(make_args())
        calls.clear()
        ef.process_reports(make_args())
        assert calls == []

    def test_missing_duplicate_restored_without_llm(self, pipeline_env, monkeypatch):
        calls = []
        monkeypatch.setattr(ef, "extract_report", stub_extract_report(calls))
        ef.process_reports(make_args())
        (pipeline_env.ext_dir / "bbb.json").unlink()
        calls.clear()

        ef.process_reports(make_args())

        assert calls == []  # copy path, no extraction
        assert read_output(pipeline_env, "bbb")["duplicate_of"] == "aaa"

    def test_limit_counts_extractions(self, pipeline_env, monkeypatch):
        calls = []
        monkeypatch.setattr(ef, "extract_report", stub_extract_report(calls))
        ef.process_reports(make_args(limit=1))
        assert len(calls) == 1
        # the duplicate group was fanned out before the limit stopped the run
        assert (pipeline_env.ext_dir / "aaa.json").exists()
        assert (pipeline_env.ext_dir / "bbb.json").exists()
        assert not (pipeline_env.ext_dir / "ccc.json").exists()

    def test_failures_recorded_and_run_continues(self, pipeline_env, monkeypatch):
        def failing(clean_text):
            return None, None, 6, "model exploded"
        calls = []
        monkeypatch.setattr(ef, "extract_report",
                            stub_extract_report(calls, failing))
        ef.process_reports(make_args())

        failures = json.loads(pipeline_env.failures.read_text())
        assert {f["file_id"] for f in failures} == {"aaa", "bbb", "ccc"}
        assert not pipeline_env.ext_dir.exists() or not list(pipeline_env.ext_dir.glob("*.json"))

    def test_unexpected_exception_guarded(self, pipeline_env, monkeypatch):
        def factory(clean_text):
            if "Unique report body" in clean_text:
                return make_extraction(), "stub", 1, None
            raise RuntimeError("kaboom")
        calls = []
        monkeypatch.setattr(ef, "extract_report", stub_extract_report(calls, factory))

        ef.process_reports(make_args())  # must not raise

        assert (pipeline_env.ext_dir / "ccc.json").exists()
        failures = json.loads(pipeline_env.failures.read_text())
        failed_ids = {f["file_id"] for f in failures}
        assert "aaa" in failed_ids and "bbb" in failed_ids
        assert all("kaboom" in f["error"] for f in failures)

    def test_success_clears_failure_entry(self, pipeline_env, monkeypatch):
        ef.record_failure("aaa", "old error", 6)
        calls = []
        monkeypatch.setattr(ef, "extract_report", stub_extract_report(calls))
        ef.process_reports(make_args())
        failures = json.loads(pipeline_env.failures.read_text())
        assert failures == []

    def test_retry_failures_selects_only_failed(self, pipeline_env, monkeypatch):
        ef.record_failure("ccc", "old error", 6)
        calls = []
        monkeypatch.setattr(ef, "extract_report", stub_extract_report(calls))
        ef.process_reports(make_args(retry_failures=True))
        assert len(calls) == 1
        assert (pipeline_env.ext_dir / "ccc.json").exists()
        assert not (pipeline_env.ext_dir / "aaa.json").exists()

    def test_copy_for_duplicate_clears_failure(self, pipeline_env, monkeypatch):
        calls = []
        monkeypatch.setattr(ef, "extract_report", stub_extract_report(calls))
        ef.process_reports(make_args())
        (pipeline_env.ext_dir / "bbb.json").unlink()
        ef.record_failure("bbb", "old error", 6)

        ef.process_reports(make_args())

        failures = json.loads(pipeline_env.failures.read_text())
        assert failures == []
