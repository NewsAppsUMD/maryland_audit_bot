import json
import logging
import os
import pdfplumber
from pathlib import Path
import time
from datetime import datetime
from playwright.sync_api import sync_playwright
import shutil

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

REPORTS_SEARCH_URL = 'https://www.ola.state.md.us/Search/Report?keyword=&agencyId=&dateFrom=&dateTo='

DEFAULT_HTTP_HEADERS = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Accept-Encoding': 'gzip, deflate',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
}

def load_reports(filename="ola_reports.json"):
    """Load reports from JSON file"""
    if os.path.exists(filename):
        try:
            with open(filename, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            logger.error(f"Could not read {filename}")
            return []
    else:
        logger.error(f"{filename} not found. Run the scraper first.")
        return []

def create_directories():
    """Create necessary directories"""
    Path("pdfs").mkdir(exist_ok=True)
    Path("text").mkdir(exist_ok=True)

def get_file_id_from_url(url):
    """Extract fileId from the URL to use as filename"""
    try:
        if 'fileId=' in url:
            file_id = url.split('fileId=')[1].split('&')[0]
            return f"{file_id}.pdf"
        else:
            # Fallback to original method if no fileId found
            return get_pdf_filename_from_url(url)
    except Exception as e:
        logger.warning(f"Could not build filename from URL {url}: {e}")
        return "unknown_report.pdf"

def get_pdf_filename_from_url(url):
    """Fallback method to generate filename from URL"""
    try:
        # Simple fallback: use a hash or timestamp
        import hashlib
        url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
        return f"report_{url_hash}.pdf"
    except Exception as e:
        logger.warning(f"Could not hash URL {url} for filename: {e}")
        return "unknown_report.pdf"

def get_pdf_filename_from_report(report):
    """Get PDF filename from report, preferring file_id if available"""
    # Use file_id if it exists in the report
    if report.get('file_id'):
        return f"{report['file_id']}.pdf"

    # Fall back to extracting from URL
    url = report.get('url')
    if url:
        return get_file_id_from_url(url)

    return "unknown_report.pdf"

def _find_report_row(page, report_title):
    """Find the table row on the reports page whose title matches report_title"""
    rows = page.query_selector_all('tbody tr')
    for row in rows:
        cells = row.query_selector_all('td')
        if len(cells) >= 3:
            title_cell = cells[2]
            row_title = title_cell.inner_text().strip()
            if row_title == report_title:
                return row
    return None

def _click_and_save_download(page, link, filepath):
    """Click a report link, wait for the download, and move it to filepath.

    Returns True if the file was downloaded and saved, False otherwise.
    """
    # Set up download handling - let it download as GetReport.pdf first
    download_completed = False
    downloaded_file_path = None

    def handle_download(download):
        nonlocal download_completed, downloaded_file_path
        try:
            # Let it download with browser's default name to pdfs folder
            downloaded_file_path = os.path.join("pdfs", "GetReport.pdf")
            download.save_as(downloaded_file_path)
            download_completed = True
            logger.info("    Downloaded as GetReport.pdf")
        except Exception as e:
            logger.error(f"    Error saving download: {e}")

    page.on('download', handle_download)

    # Click the link to trigger download
    logger.info("    Clicking download link...")
    try:
        link.click()

        # Wait for download to complete
        timeout_count = 0
        while not download_completed and timeout_count < 15:
            page.wait_for_timeout(3000)
            timeout_count += 1

        if download_completed and downloaded_file_path and os.path.exists(downloaded_file_path):
            # Now rename/move the file to our desired name
            if downloaded_file_path != filepath:
                shutil.move(downloaded_file_path, filepath)
                logger.info(f"    Renamed to: {os.path.basename(filepath)}")

            file_size = os.path.getsize(filepath)
            logger.info(f"    ✓ PDF saved successfully ({file_size} bytes)")
            return True
        else:
            logger.warning("    Download did not complete within timeout")
            return False

    except Exception as e:
        logger.error(f"    Error during download: {e}")
        return False

def download_pdf_with_playwright(url, filepath, report_title=""):
    """Download PDF using Playwright by clicking link and renaming afterward"""
    try:
        with sync_playwright() as p:
            # Launch browser
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                accept_downloads=True
            )
            page = context.new_page()

            # Set headers similar to the original scraper
            page.set_extra_http_headers(DEFAULT_HTTP_HEADERS)

            # Go to the main reports page
            logger.info("    Loading reports page...")
            page.goto(REPORTS_SEARCH_URL, wait_until='networkidle', timeout=30000)

            # Wait for the table to load
            page.wait_for_selector('tbody')

            # Find the specific report link by title
            logger.info(f"    Looking for report: {report_title[:50]}...")
            target_row = _find_report_row(page, report_title)

            if not target_row:
                logger.warning(f"    Could not find report with title: {report_title}")
                browser.close()
                return False

            # Find the download link in the target row
            title_cell = target_row.query_selector('td:nth-child(3)')
            link = title_cell.query_selector('a')

            if not link:
                logger.warning("    No download link found for this report")
                browser.close()
                return False

            logger.info("    Found report link, starting download...")
            success = _click_and_save_download(page, link, filepath)
            browser.close()
            return success

    except Exception as e:
        logger.error(f"    Error with Playwright download: {e}")
        return False

def extract_text_from_pdf(pdf_path):
    """Extract text from PDF file using pdfplumber"""
    try:
        text = ""
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                page_text = page.extract_text()
                if page_text:
                    text += f"--- Page {page_num} ---\n"
                    text += page_text + "\n\n"

            return text.strip()
    except Exception as e:
        logger.error(f"Error extracting text from {pdf_path}: {e}")
        return None

def process_reports():
    """Main function to process all reports"""
    reports = load_reports()

    if not reports:
        return

    create_directories()

    # Filter reports with URLs (likely PDFs)
    pdf_reports = [report for report in reports if report.get('url')]

    logger.info(f"Found {len(pdf_reports)} reports with URLs to process")

    processed_count = 0
    skipped_count = 0
    error_count = 0

    for i, report in enumerate(pdf_reports, 1):
        url = report['url']
        title = report.get('title', 'Unknown')

        logger.info(f"\n[{i}/{len(pdf_reports)}] Processing: {title[:60]}...")

        # Create filename for PDF using file_id if available, otherwise extract from URL
        pdf_filename = get_pdf_filename_from_report(report)
        pdf_path = os.path.join("pdfs", pdf_filename)

        # Create corresponding text filename
        text_filename = pdf_filename.rsplit('.', 1)[0] + '.txt'
        text_path = os.path.join("text", text_filename)

        # Skip if text file already exists (meaning we've already processed this PDF)
        if os.path.exists(text_path):
            logger.info(f"  Text file already exists, skipping: {text_filename}")
            skipped_count += 1
            continue

        # Download PDF if not exists
        if not os.path.exists(pdf_path):
            logger.info("  Downloading PDF...")
            if not download_pdf_with_playwright(url, pdf_path, title):
                error_count += 1
                continue
            time.sleep(2)  # Be polite to the server
        else:
            logger.info(f"  PDF already exists: {pdf_filename}")

        # Always extract text if we got here (text file doesn't exist)
        logger.info("  Extracting text...")
        text = extract_text_from_pdf(pdf_path)

        if text:
            # Save text to file
            try:
                with open(text_path, 'w', encoding='utf-8') as f:
                    # Add metadata header
                    f.write(f"Title: {title}\n")
                    f.write(f"Date: {report.get('date', 'Unknown')}\n")
                    f.write(f"Type: {report.get('type', 'Unknown')}\n")
                    f.write(f"URL: {url}\n")
                    f.write(f"Extracted: {datetime.now().isoformat()}\n")
                    f.write("-" * 80 + "\n\n")
                    f.write(text)

                logger.info(f"  ✓ Saved text to: {text_filename}")
                processed_count += 1

            except Exception as e:
                logger.error(f"  Error saving text file: {e}")
                error_count += 1
        else:
            logger.error("  ✗ Failed to extract text")
            error_count += 1

    logger.info("\n" + "="*60)
    logger.info("Processing complete!")
    logger.info(f"  Processed: {processed_count}")
    logger.info(f"  Skipped (already exists): {skipped_count}")
    logger.info(f"  Errors: {error_count}")
    logger.info(f"  Total reports with URLs: {len(pdf_reports)}")

if __name__ == "__main__":
    logger.info("OLA Reports PDF Text Extractor")
    logger.info("="*40)
    process_reports()
