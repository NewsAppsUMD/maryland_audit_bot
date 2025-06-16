import json
import os
from urllib.parse import urlparse
import pdfplumber
from pathlib import Path
import time
from datetime import datetime
from playwright.sync_api import sync_playwright
import tempfile
import shutil

def load_reports(filename="ola_reports.json"):
    """Load reports from JSON file"""
    if os.path.exists(filename):
        try:
            with open(filename, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            print(f"Error: Could not read {filename}")
            return []
    else:
        print(f"Error: {filename} not found. Run the scraper first.")
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
    except:
        return "unknown_report.pdf"

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
            page.set_extra_http_headers({
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            })
            
            # Go to the main reports page
            main_url = 'https://www.ola.state.md.us/Search/Report?keyword=&agencyId=&dateFrom=&dateTo='
            print(f"    Loading reports page...")
            page.goto(main_url, wait_until='networkidle', timeout=30000)
            
            # Wait for the table to load
            page.wait_for_selector('tbody')
            
            # Find the specific report link by title
            print(f"    Looking for report: {report_title[:50]}...")
            
            # Get all table rows and find the matching one
            rows = page.query_selector_all('tbody tr')
            target_row = None
            
            for row in rows:
                cells = row.query_selector_all('td')
                if len(cells) >= 3:
                    title_cell = cells[2]
                    row_title = title_cell.inner_text().strip()
                    if row_title == report_title:
                        target_row = row
                        break
            
            if not target_row:
                print(f"    Could not find report with title: {report_title}")
                browser.close()
                return False
            
            # Find the download link in the target row
            title_cell = target_row.query_selector('td:nth-child(3)')
            link = title_cell.query_selector('a')
            
            if not link:
                print(f"    No download link found for this report")
                browser.close()
                return False
            
            print(f"    Found report link, starting download...")
            
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
                    print(f"    Downloaded as GetReport.pdf")
                except Exception as e:
                    print(f"    Error saving download: {e}")
            
            page.on('download', handle_download)
            
            # Click the link to trigger download
            print(f"    Clicking download link...")
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
                        print(f"    Renamed to: {os.path.basename(filepath)}")
                    
                    file_size = os.path.getsize(filepath)
                    print(f"    ✓ PDF saved successfully ({file_size} bytes)")
                    browser.close()
                    return True
                else:
                    print(f"    Download did not complete within timeout")
                    browser.close()
                    return False
            
            except Exception as e:
                print(f"    Error during download: {e}")
                browser.close()
                return False
                
    except Exception as e:
        print(f"    Error with Playwright download: {e}")
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
        print(f"Error extracting text from {pdf_path}: {e}")
        return None

def process_reports():
    """Main function to process all reports"""
    reports = load_reports()
    
    if not reports:
        return
    
    create_directories()
    
    # Filter reports with URLs (likely PDFs)
    pdf_reports = [report for report in reports if report.get('url')]
    
    print(f"Found {len(pdf_reports)} reports with URLs to process")
    
    processed_count = 0
    skipped_count = 0
    error_count = 0
    
    for i, report in enumerate(pdf_reports, 1):
        url = report['url']
        title = report.get('title', 'Unknown')
        
        print(f"\n[{i}/{len(pdf_reports)}] Processing: {title[:60]}...")
        
        # Create filename for PDF using fileId
        pdf_filename = get_file_id_from_url(url)
        pdf_path = os.path.join("pdfs", pdf_filename)
        
        # Create corresponding text filename
        text_filename = pdf_filename.rsplit('.', 1)[0] + '.txt'
        text_path = os.path.join("text", text_filename)
        
        # Skip if text file already exists (meaning we've already processed this PDF)
        if os.path.exists(text_path):
            print(f"  Text file already exists, skipping: {text_filename}")
            skipped_count += 1
            continue
        
        # Download PDF if not exists
        if not os.path.exists(pdf_path):
            print(f"  Downloading PDF...")
            if not download_pdf_with_playwright(url, pdf_path, title):
                error_count += 1
                continue
            time.sleep(2)  # Be polite to the server
        else:
            print(f"  PDF already exists: {pdf_filename}")
        
        # Always extract text if we got here (text file doesn't exist)
        print(f"  Extracting text...")
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
                
                print(f"  ✓ Saved text to: {text_filename}")
                processed_count += 1
                
            except Exception as e:
                print(f"  Error saving text file: {e}")
                error_count += 1
        else:
            print(f"  ✗ Failed to extract text")
            error_count += 1
    
    print(f"\n" + "="*60)
    print(f"Processing complete!")
    print(f"  Processed: {processed_count}")
    print(f"  Skipped (already exists): {skipped_count}")
    print(f"  Errors: {error_count}")
    print(f"  Total reports with URLs: {len(pdf_reports)}")

if __name__ == "__main__":
    print("OLA Reports PDF Text Extractor")
    print("="*40)
    process_reports()