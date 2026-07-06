# maryland_audit_bot

A pipeline for collecting and analyzing audit reports from the Maryland Office of Legislative Audits (OLA). It scrapes report metadata from the [OLA report search page](https://www.ola.state.md.us/Search/Report), downloads the report PDFs, extracts their text, and includes a prototype Flask web app that uses LLMs to summarize an agency's audit history for journalists.

## Requirements

- Python >= 3.13
- [uv](https://docs.astral.sh/uv/) for dependency management
- Playwright browsers for the scraping steps: `uv run playwright install chromium`

## Repo layout

```
scraper.py          Scrapes OLA report metadata into ola_reports.json
pdf_parser.py       Downloads report PDFs and extracts their text
ola_reports.json    Report metadata database (date, type, title, url, file_id)
pdfs/               Downloaded report PDFs, named by file_id
text/               Extracted text for each PDF, named by file_id
prototype/          Flask web app prototype for LLM analysis of agencies
tests/              Pytest suite for the pure helper functions
```

## Running the pipeline

### 1. Scrape report metadata

```
uv run scraper.py
```

Loads the OLA report search page with Playwright, extracts every report row (date, type, title, URL, file id), and appends any reports not already present to `ola_reports.json`. Safe to re-run; existing entries are kept and deduplicated by URL (or title + date when there is no URL).

### 2. Download PDFs and extract text

```
uv run pdf_parser.py
```

For each report in `ola_reports.json` with a URL, downloads the PDF into `pdfs/` (via Playwright, since the OLA site serves downloads behind its search page) and extracts the text with pdfplumber into `text/`. Reports whose text file already exists are skipped, so this is also safe to re-run incrementally.

### 3. Prototype web app

The `prototype/` directory contains a Flask app that lets a reporter pick one of six test agencies and get an LLM-generated summary of that agency's audit findings, with citations back to the source reports. It expects copies of the data in `prototype/data/`:

```
cp ola_reports.json prototype/data/
cp -r text prototype/data/
```

Then, from `prototype/` (see `prototype/README.md` for model configuration and API keys):

```
cd prototype
uv run app.py
```

The app reads model settings from environment variables (`DEFAULT_MODEL`, `FALLBACK_MODELS`) and warns loudly if `FLASK_SECRET_KEY` is unset.

## Automation

A GitHub Actions workflow (`.github/workflows/scrape.yml`) runs the scraper and PDF parser every Monday morning (11:00 UTC) and can also be triggered manually from the Actions tab. When it finds new reports, it commits the updated `ola_reports.json` plus the new files in `pdfs/` and `text/` back to the repository as `github-actions[bot]`.

The findings-extraction step (`extract_findings.py`) requires a local Ollama instance and is not part of the workflow — run it locally after new reports arrive.

## Tests

```
uv run pytest
```

The test suite covers the pure helper functions (URL/date parsing, filename generation, agency title matching) and does not hit the network or require Playwright browsers.

## What's next

A structured findings-extraction pipeline (`extract_findings.py`), which pulls individual audit findings out of the report text for analysis, is being added separately.
