"""Structured extraction pipeline for Maryland OLA audit report text files.

Reads text/{file_id}.txt files produced by pdf_parser.py, sends the report body
to a local Ollama model (via the llm library) with a Pydantic schema, validates
the result mechanically, and writes extractions/{file_id}.json.

Idempotent and resumable: files with existing extractions are skipped unless
--force is given. Duplicate report bodies (the same PDF published under
multiple file_ids) are extracted once and the result is written for every
member of the duplicate group.

Usage:
    uv run python extract_findings.py --limit 10
    uv run python extract_findings.py --file-id 5a8f4d0acc9d724560674266
    uv run python extract_findings.py --report-type "Fiscal Compliance"
    uv run python extract_findings.py --spot-check 5
"""
import argparse
import hashlib
import json
import logging
import os
import random
import re
from datetime import datetime
from pathlib import Path

import llm
from pydantic import ValidationError

from schemas import FindingsChunk, ReportExtraction

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)  # quiet ollama HTTP chatter
logger = logging.getLogger(__name__)

TEXT_DIR = Path("text")
EXTRACTIONS_DIR = Path("extractions")
FAILURES_FILE = Path("extraction_failures.json")

DEFAULT_MODEL = "qwen3.5:9b"
DEFAULT_ESCALATION_MODEL = "qwen3.5:35b"
NUM_CTX = 32768  # Ollama silently truncates at its small default; set explicitly
MAX_ATTEMPTS_PER_MODEL = 3  # 1 fresh attempt + 2 repair attempts
CHARS_PER_TOKEN = 4  # rough token estimate
CHUNK_THRESHOLD_CHARS = 100_000  # bodies larger than this get chunked
MAX_CHUNK_CHARS = 80_000  # ~20k tokens per chunk, leaves headroom in num_ctx

# A "Finding N" heading alone on a line (optionally marked with an asterisk,
# which OLA uses to denote "repeated in full or part from preceding audit
# report"). Table-of-contents entries ("Finding 1 - Blah...") don't match.
FINDING_HEADING_RE = re.compile(r"^[ \t]*[\*∗✱]?[ \t]*Finding\s+(\d+)[ \t]*[\*∗✱]?[ \t]*$", re.MULTILINE)
ASTERISK_FINDING_RE = re.compile(r"^[ \t]*[\*∗✱][ \t]*Finding\s+(\d+)|^[ \t]*Finding\s+(\d+)[ \t]*[\*∗✱]", re.MULTILINE)
PAGE_MARKER_RE = re.compile(r"^--- Page \d+ ---[ \t]*$", re.MULTILINE)
HEADER_SEPARATOR_RE = re.compile(r"^-{40,}[ \t]*$", re.MULTILINE)

# Pages containing any of these phrases are OLA boilerplate (contact info,
# fraud hotline notice, nondiscrimination statement, committee rosters) and
# are dropped before the text is sent to the model.
BOILERPLATE_MARKERS = (
    "For further information concerning this report contact",
    "operates a Fraud Hotline",
    "does not discriminate on the basis of",
    "This report and any related follow-up correspondence are available",
    "Electronic copies of our audit reports can be viewed",
    "Alternate formats may be requested through the Maryland Relay",
    "JOINT AUDIT AND EVALUATION COMMITTEE",
    "JOINT COMMITTEE ON THE MANAGEMENT OF PUBLIC FUNDS",
)

SYSTEM_PROMPT = """\
You extract structured data from Maryland Office of Legislative Audits (OLA) audit reports.
Extract ONLY what is explicitly stated in the text. Never guess or infer; use null for anything not stated.

Rules:
- Findings are the numbered "Finding N" sections of the report. A finding's title is the bold summary sentence that immediately follows the "Finding N" heading. Do not treat table-of-contents entries or executive summary lists as separate findings.
- description: a 1-3 sentence summary of that finding's Analysis section.
- is_repeat: true only if the finding is marked with an asterisk (*), noted as "(repeat)", or explicitly listed as repeated from the preceding audit report (e.g., in the Status of Preceding Findings section). Set prior_finding_number only if the prior report's finding number is stated.
- criminal_referral: true ONLY if the report states a matter WAS actually referred to the Office of the Attorney General - Criminal Division. Statements that no referral was warranted, or generic boilerplate describing the referral process, do NOT count.
- fraud_hotline_origin: true only if the audit or review originated from a complaint or allegation received through the OLA fraud hotline.
- report_date: the date of the transmittal letter inside the document text (do not use any other date).
- audit_period_start / audit_period_end: from language like "for the period beginning X and ending Y".
- All dates must be formatted YYYY-MM-DD. If only a month and year are stated, use the first day of that month. Use null when no date is stated.
- dollar_amounts: dollar figures explicitly tied to the finding, each with a short context phrase. Convert phrases like "$1.4 million" to 1400000.
- recommendation, agency_agrees, agency_completion_date: from the recommendation for the finding and the agency's response to it (Agree/Disagree and estimated completion date), if present.
- prior_findings_count / prior_findings_repeated: from the Status of Preceding Findings discussion (how many findings the preceding report contained and how many are repeated in this report).
- total_dollar_impact: the sum of clearly quantified questioned or unaccounted-for amounts across findings, or null if none are quantified.
- agency_response_summary: 1-3 sentences summarizing the agency's overall response.
"""

CHUNK_SYSTEM_PROMPT = SYSTEM_PROMPT + """
This text is a LATER PORTION of a report that was split into parts. It contains only findings sections. Extract every finding present in this text and nothing else.
"""


def load_index(filename="ola_reports.json"):
    """Load ola_reports.json into {file_id: metadata record}."""
    path = Path(filename)
    if not path.exists():
        logger.error(f"{filename} not found. Run the scraper first.")
        return {}
    try:
        with open(path) as f:
            reports = json.load(f)
    except (json.JSONDecodeError, IOError):
        logger.error(f"Could not read {filename}")
        return {}
    return {r["file_id"]: r for r in reports if r.get("file_id")}


def split_header(text):
    """Split a text/ file into (metadata_header, body).

    pdf_parser.py writes a Title/Date/Type/URL/Extracted header followed by a
    line of 80 dashes. The header dates are sometimes wrong, so the body is
    what matters. Files without a recognizable header return ("", text).
    """
    m = HEADER_SEPARATOR_RE.search(text[:2000])
    if m:
        return text[: m.end()], text[m.end():].lstrip("\n")
    return "", text


def content_hash(body):
    """Stable hash of a report body, for duplicate detection."""
    return hashlib.sha1(body.strip().encode("utf-8")).hexdigest()


def dedupe_texts(file_ids, text_dir=None):
    """Group file_ids by body content hash.

    Returns (groups, hash_by_fid) where groups maps content_hash to a sorted
    list of file_ids sharing that body (the first is the canonical copy).
    """
    if text_dir is None:
        text_dir = TEXT_DIR
    groups = {}
    hash_by_fid = {}
    for fid in file_ids:
        path = text_dir / f"{fid}.txt"
        try:
            text = path.read_text(encoding="utf-8")
        except (IOError, UnicodeDecodeError) as e:
            logger.warning(f"Could not read {path}: {e}")
            continue
        _, body = split_header(text)
        h = content_hash(body)
        hash_by_fid[fid] = h
        groups.setdefault(h, []).append(fid)
    for h in groups:
        groups[h].sort()
    return groups, hash_by_fid


def strip_boilerplate(body):
    """Remove page markers and OLA boilerplate pages from a report body."""
    segments = PAGE_MARKER_RE.split(body)
    kept = []
    for segment in segments:
        segment = segment.strip()
        if not segment:
            continue
        has_marker = any(marker in segment for marker in BOILERPLATE_MARKERS)
        if has_marker and not FINDING_HEADING_RE.search(segment):
            continue
        kept.append(segment)
    return "\n\n".join(kept)


def count_findings_headings(text):
    """Count distinct 'Finding N' headings (for validation, not extraction)."""
    return len(set(FINDING_HEADING_RE.findall(text)))


def estimate_tokens(text):
    return len(text) // CHARS_PER_TOKEN


def preprocess(text):
    """Header-strip and clean a raw text/ file for the model.

    Returns (clean_text, expected_findings_count, estimated_tokens).
    """
    _, body = split_header(text)
    clean = strip_boilerplate(body)
    return clean, count_findings_headings(clean), estimate_tokens(clean)


def _hard_split(piece, max_chars):
    """Split a single oversized piece into segments of at most max_chars.

    Prefers paragraph boundaries (blank lines), then line boundaries, then a
    raw character cut. Concatenating the segments reproduces the input.
    """
    segments = []
    remaining = piece
    while len(remaining) > max_chars:
        cut = remaining.rfind("\n\n", max_chars // 2, max_chars - 1)
        if cut != -1:
            cut += 2  # keep the blank line with the left segment
        else:
            cut = remaining.rfind("\n", max_chars // 2, max_chars)
            if cut != -1:
                cut += 1
            else:
                cut = max_chars
        segments.append(remaining[:cut])
        remaining = remaining[cut:]
    if remaining:
        segments.append(remaining)
    return segments


def split_into_chunks(clean_text, max_chars=MAX_CHUNK_CHARS):
    """Split very large report text on Finding boundaries.

    Chunk 1 always starts with everything before the first finding
    (transmittal letter, background, Status of Preceding Findings). A single
    section larger than max_chars is hard-split (Ollama would otherwise
    silently truncate an oversized prompt). Concatenating the chunks
    reproduces the input exactly.
    """
    if len(clean_text) <= max_chars:
        return [clean_text]
    matches = list(FINDING_HEADING_RE.finditer(clean_text))
    if not matches:
        logger.warning(
            f"  No Finding boundaries in {len(clean_text)}-char text; hard-splitting")
        return _hard_split(clean_text, max_chars)
    starts = [m.start() for m in matches]
    # Pieces: the prefix (transmittal letter etc.), then one per finding section.
    pieces = [clean_text[: starts[0]]]
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(clean_text)
        pieces.append(clean_text[start:end])
    expanded = []
    for piece in pieces:
        if len(piece) > max_chars:
            logger.warning(
                f"  Section of {len(piece)} chars exceeds chunk budget "
                f"({max_chars}); hard-splitting it")
            expanded.extend(_hard_split(piece, max_chars))
        else:
            expanded.append(piece)
    chunks = []
    current = ""
    for piece in expanded:
        if current and len(current) + len(piece) > max_chars:
            chunks.append(current)
            current = piece
        else:
            current += piece
    if current:
        chunks.append(current)
    return chunks


def call_model(model_name, prompt_text, schema, system_prompt, repair_error=None):
    """Single model call with schema; raises on JSON/validation failure."""
    model = llm.get_model(model_name)
    if repair_error:
        prompt_text = (
            prompt_text
            + "\n\nYour previous response failed validation with this error:\n"
            + repair_error
            + "\nReturn corrected JSON that matches the schema exactly."
        )
    response = model.prompt(
        prompt_text,
        system=system_prompt,
        schema=schema,
        temperature=0,
        num_ctx=NUM_CTX,
    )
    data = json.loads(response.text())
    return schema.model_validate(data)


def extract(prompt_text, schema, model_name, escalation_model_name,
            system_prompt=SYSTEM_PROMPT):
    """Call the model with retries and escalation.

    Up to MAX_ATTEMPTS_PER_MODEL attempts on the primary model (repair
    attempts feed the validation error back), then the same on the escalation
    model. Returns (result_or_None, model_used_or_None, attempts, last_error).
    """
    attempts = 0
    last_error = None
    for name in dict.fromkeys([model_name, escalation_model_name]):
        repair_error = None
        for _ in range(MAX_ATTEMPTS_PER_MODEL):
            attempts += 1
            try:
                result = call_model(name, prompt_text, schema, system_prompt,
                                    repair_error=repair_error)
                return result, name, attempts, None
            except (json.JSONDecodeError, ValidationError) as e:
                last_error = str(e)
                repair_error = last_error[:2000]
                logger.warning(f"  Attempt {attempts} ({name}) failed validation: {last_error[:200]}")
            except Exception as e:
                last_error = str(e)
                logger.warning(f"  Attempt {attempts} ({name}) errored: {last_error[:200]}")
                break  # non-validation error: don't repair-loop, try next model
        logger.warning(f"  Escalating past {name}" if name != escalation_model_name
                       else "  All models exhausted")
    return None, None, attempts, last_error


def extract_report(clean_text, model_name, escalation_model_name):
    """Extract a full report, chunking if it is too large for one call.

    Returns (ReportExtraction_or_None, models_used, attempts, error).
    """
    chunks = (split_into_chunks(clean_text)
              if len(clean_text) > CHUNK_THRESHOLD_CHARS else [clean_text])
    if len(chunks) > 1:
        logger.info(f"  Large report: split into {len(chunks)} chunks")

    prompt = "Extract structured data from this Maryland OLA audit report:\n\n" + chunks[0]
    extraction, model_used, attempts, error = extract(
        prompt, ReportExtraction, model_name, escalation_model_name)
    if extraction is None:
        return None, model_used, attempts, error

    models_used = [model_used]
    findings = {f.number: f for f in extraction.findings}
    for i, chunk in enumerate(chunks[1:], 2):
        prompt = (f"Extract the findings from this portion (part {i} of {len(chunks)}) "
                  f"of a Maryland OLA audit report:\n\n{chunk}")
        chunk_result, chunk_model, chunk_attempts, chunk_error = extract(
            prompt, FindingsChunk, model_name, escalation_model_name,
            system_prompt=CHUNK_SYSTEM_PROMPT)
        attempts += chunk_attempts
        if chunk_result is None:
            return None, chunk_model, attempts, f"chunk {i} failed: {chunk_error}"
        models_used.append(chunk_model)
        for finding in chunk_result.findings:
            findings.setdefault(finding.number, finding)

    extraction.findings = [findings[n] for n in sorted(findings)]
    return extraction, ",".join(dict.fromkeys(models_used)), attempts, None


def count_asterisk_findings(text):
    """Distinct finding numbers marked with an asterisk (repeat marker).

    Returns a set of finding-number strings: a finding asterisked in both the
    table of contents and at its own heading counts once.
    """
    return {a or b for a, b in ASTERISK_FINDING_RE.findall(text)}


def dollar_amount_in_text(amount, text):
    """Check whether a dollar amount appears in the raw text in some form."""
    if amount == 0:
        # Bare "0" appears in nearly any text; require an explicit zero amount.
        return "$0" in text or "0.00" in text
    candidates = set()
    if amount == int(amount):
        whole = int(amount)
        candidates.add(f"{whole:,}")
        candidates.add(str(whole))
    else:
        candidates.add(f"{amount:,.2f}")
        candidates.add(f"{amount:.2f}")
    for divisor, word in ((1e9, "billion"), (1e6, "million")):
        if amount >= divisor and (amount / divisor) < 1000:
            scaled = f"{amount / divisor:g}"
            candidates.add(f"{scaled} {word}")
    return any(c in text for c in candidates)


def valid_date(value, min_year=1995, max_year=None):
    """True if value is a parseable YYYY-MM-DD date in a sane year range.

    max_year defaults to next year (report dates can't be in the future).
    """
    if max_year is None:
        max_year = datetime.now().year + 1
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except (ValueError, TypeError):
        return False
    return min_year <= parsed.year <= max_year


def validate_extraction(extraction, raw_text, expected_findings_count):
    """Mechanical cross-checks. Returns a list of flag strings (not fatal)."""
    flags = []
    if len(extraction.findings) != expected_findings_count:
        flags.append(
            f"findings_count_mismatch: extracted {len(extraction.findings)}, "
            f"regex counted {expected_findings_count}")

    for finding in extraction.findings:
        for da in finding.dollar_amounts:
            if not dollar_amount_in_text(da.amount, raw_text):
                flags.append(
                    f"dollar_amount_not_in_text: finding {finding.number} "
                    f"amount {da.amount}")

    mentions_criminal = "Criminal Division" in raw_text
    if extraction.criminal_referral and not mentions_criminal:
        flags.append("criminal_referral_true_but_criminal_division_not_in_text")
    elif not extraction.criminal_referral and mentions_criminal:
        flags.append("criminal_division_in_text_but_referral_false_verify")

    for field in ("report_date", "audit_period_start", "audit_period_end"):
        value = getattr(extraction, field)
        if value is not None and not valid_date(value):
            flags.append(f"bad_date: {field}={value}")

    repeats_claimed = sum(1 for f in extraction.findings if f.is_repeat)
    # Dedupe by finding number: the same finding is often asterisked in both
    # the TOC/summary list and at its heading, and must count as one hint.
    asterisk_hints = len(count_asterisk_findings(raw_text))
    has_repeat_language = bool(re.search(r"repeat", raw_text, re.IGNORECASE))
    if repeats_claimed and not has_repeat_language:
        flags.append(f"repeats_claimed_{repeats_claimed}_but_no_repeat_language_in_text")
    elif asterisk_hints and repeats_claimed != asterisk_hints:
        flags.append(
            f"repeat_count_mismatch: extracted {repeats_claimed}, "
            f"asterisk markers {asterisk_hints}")
    return flags


def write_json_atomic(path, data):
    """Write JSON to path atomically (temp file + os.replace).

    A crash mid-write must never leave a truncated .json file behind: the
    exists-skip logic would trust it forever and downstream readers would
    crash on it.
    """
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def load_failures():
    if FAILURES_FILE.exists():
        try:
            with open(FAILURES_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            logger.warning(f"Could not read {FAILURES_FILE}, starting fresh")
    return []


def record_failure(file_id, error, attempts):
    failures = [f for f in load_failures() if f.get("file_id") != file_id]
    failures.append({
        "file_id": file_id,
        "error": error,
        "attempts": attempts,
        "failed_at": datetime.now().isoformat(),
    })
    write_json_atomic(FAILURES_FILE, failures)


def clear_failure(file_id):
    failures = load_failures()
    remaining = [f for f in failures if f.get("file_id") != file_id]
    if len(remaining) != len(failures):
        write_json_atomic(FAILURES_FILE, remaining)


def write_output(file_id, extraction, flags, model, chash, duplicate_of):
    EXTRACTIONS_DIR.mkdir(exist_ok=True)
    output = {
        "extraction": extraction.model_dump() if hasattr(extraction, "model_dump") else extraction,
        "validation_flags": flags,
        "model": model,
        "extracted_at": datetime.now().isoformat(),
        "content_hash": chash,
        "duplicate_of": duplicate_of,
    }
    path = EXTRACTIONS_DIR / f"{file_id}.json"
    write_json_atomic(path, output)
    return path


def copy_for_duplicate(file_id, canonical_id):
    """Write an extraction for a duplicate file_id from the canonical output."""
    canonical_path = EXTRACTIONS_DIR / f"{canonical_id}.json"
    with open(canonical_path) as f:
        output = json.load(f)
    output["duplicate_of"] = canonical_id
    write_json_atomic(EXTRACTIONS_DIR / f"{file_id}.json", output)
    clear_failure(file_id)


def spot_check(n):
    """Print N random extractions' finding titles beside matching raw text."""
    paths = sorted(EXTRACTIONS_DIR.glob("*.json"))
    if not paths:
        logger.error(f"No extractions found in {EXTRACTIONS_DIR}/")
        return
    for path in random.sample(paths, min(n, len(paths))):
        file_id = path.stem
        with open(path) as f:
            output = json.load(f)
        text_path = TEXT_DIR / f"{file_id}.txt"
        raw_lines = []
        if text_path.exists():
            _, body = split_header(text_path.read_text(encoding="utf-8"))
            raw_lines = body.splitlines()
        print(f"\n{'=' * 70}\n{file_id}  (model: {output.get('model')}, "
              f"flags: {len(output.get('validation_flags', []))})")
        for flag in output.get("validation_flags", []):
            print(f"  FLAG: {flag}")
        for finding in output.get("extraction", {}).get("findings", []):
            title = finding.get("title", "")
            print(f"\n  Finding {finding.get('number')}: {title}")
            words = [re.escape(w) for w in title.split()[:6]]
            window = None
            if words and raw_lines:
                pattern = re.compile(r"\s+".join(words), re.IGNORECASE)
                joined = "\n".join(raw_lines)
                m = pattern.search(joined)
                if m:
                    line_no = joined[: m.start()].count("\n")
                    window = raw_lines[max(0, line_no - 1): line_no + 3]
            if window:
                for line in window:
                    print(f"    | {line}")
            else:
                print("    | (no matching text window found)")


def select_file_ids(index, args):
    """Determine which file_ids to process based on CLI filters."""
    available = sorted(fid for fid in index if (TEXT_DIR / f"{fid}.txt").exists())
    if args.file_id:
        missing = [fid for fid in args.file_id if fid not in index
                   or not (TEXT_DIR / f"{fid}.txt").exists()]
        for fid in missing:
            logger.warning(f"No text file or index entry for {fid}, skipping")
        return [fid for fid in args.file_id if fid not in missing]
    selected = available
    if args.report_type:
        wanted = args.report_type.lower()
        selected = [fid for fid in selected
                    if wanted in (index[fid].get("type") or "").lower()]
    if args.retry_failures:
        failed_ids = {f.get("file_id") for f in load_failures()}
        selected = [fid for fid in selected if fid in failed_ids]
    return selected


def process_reports(args):
    """Run extraction over the selected file_ids.

    Duplicate-group semantics: extraction happens once per unique body and the
    result is written for every file_id in the group. With --force, a selected
    file_id is re-extracted even if it is a non-canonical duplicate, and the
    fresh result overwrites the outputs of ALL members of its group.
    """
    index = load_index()
    if not index:
        return
    selected = select_file_ids(index, args)
    if not selected:
        logger.info("Nothing to process")
        return

    # Dedup across everything with text so duplicate groups and canonical ids
    # are stable regardless of CLI filters.
    all_fids = sorted(fid for fid in index if (TEXT_DIR / f"{fid}.txt").exists())
    groups, hash_by_fid = dedupe_texts(all_fids)
    logger.info(f"{len(all_fids)} text files, {len(groups)} unique report bodies; "
                f"{len(selected)} selected")

    extracted = skipped = copied = failed = 0
    for fid in selected:
        if args.limit and extracted >= args.limit:
            logger.info(f"Reached --limit {args.limit}")
            break
        # Guard the whole per-file body: one corrupt or unreadable file must
        # not kill a long unattended run.
        try:
            out_path = EXTRACTIONS_DIR / f"{fid}.json"
            if out_path.exists() and not args.force:
                skipped += 1
                continue

            chash = hash_by_fid.get(fid)
            group = groups.get(chash, [fid])
            canonical = group[0]

            # If the canonical extraction already exists, copy instead of re-extracting.
            canonical_path = EXTRACTIONS_DIR / f"{canonical}.json"
            if fid != canonical and canonical_path.exists() and not args.force:
                copy_for_duplicate(fid, canonical)
                logger.info(f"{fid}: duplicate of {canonical}, copied extraction")
                copied += 1
                continue

            title = (index.get(fid) or {}).get("title", "")
            logger.info(f"{fid}: extracting ({title[:60]})")
            text = (TEXT_DIR / f"{fid}.txt").read_text(encoding="utf-8")
            _, body = split_header(text)
            clean, expected_count, est_tokens = preprocess(text)
            logger.info(f"  ~{est_tokens} tokens, {expected_count} finding headings")

            start = datetime.now()
            extraction, model_used, attempts, error = extract_report(
                clean, args.model, args.escalation_model)
            elapsed = (datetime.now() - start).total_seconds()

            if extraction is None:
                logger.error(f"  FAILED after {attempts} attempts: {str(error)[:200]}")
                record_failure(fid, str(error), attempts)
                failed += 1
                continue

            flags = validate_extraction(extraction, body, expected_count)
            if flags:
                logger.info(f"  {len(flags)} validation flag(s): {flags}")
            logger.info(f"  OK: {len(extraction.findings)} findings, model {model_used}, "
                        f"{attempts} attempt(s), {elapsed:.1f}s")

            # Write for every file_id in the duplicate group.
            for member in group:
                member_path = EXTRACTIONS_DIR / f"{member}.json"
                if member != fid and member_path.exists() and not args.force:
                    continue
                duplicate_of = None if member == canonical else canonical
                write_output(member, extraction, flags, model_used, chash, duplicate_of)
                clear_failure(member)
            extracted += 1
        except Exception as e:
            logger.error(f"{fid}: unexpected error, skipping: {e}")
            record_failure(fid, f"unexpected error: {e}", 0)
            failed += 1

    logger.info("=" * 60)
    logger.info(f"Done. Extracted: {extracted}, copied from duplicates: {copied}, "
                f"skipped (existing): {skipped}, failed: {failed}")


def main():
    parser = argparse.ArgumentParser(
        description="Extract structured findings from OLA audit report text files")
    parser.add_argument("--limit", type=int, default=None,
                        help="Stop after N new extractions")
    parser.add_argument("--file-id", action="append", default=None,
                        help="Process only this file_id (repeatable)")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"Primary model (default: {DEFAULT_MODEL})")
    parser.add_argument("--escalation-model", default=DEFAULT_ESCALATION_MODEL,
                        help=f"Fallback model (default: {DEFAULT_ESCALATION_MODEL})")
    parser.add_argument("--report-type", default=None,
                        help="Only process reports whose type contains this string")
    parser.add_argument("--force", action="store_true",
                        help="Re-extract even if output exists")
    parser.add_argument("--retry-failures", action="store_true",
                        help="Only process file_ids recorded in extraction_failures.json")
    parser.add_argument("--spot-check", type=int, default=None, metavar="N",
                        help="Sample N existing extractions and print finding titles "
                             "next to matching raw text")
    args = parser.parse_args()

    if args.spot_check:
        spot_check(args.spot_check)
        return
    process_reports(args)


if __name__ == "__main__":
    main()
