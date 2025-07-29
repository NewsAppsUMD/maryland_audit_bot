import json
import os
from datetime import datetime
from playwright.sync_api import sync_playwright

def load_existing_reports(filename="ola_reports.json"):
    """Load existing reports from JSON file"""
    if os.path.exists(filename):
        try:
            with open(filename, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            print(f"Warning: Could not read {filename}, starting fresh")
            return []
    return []

def save_reports(reports, filename="ola_reports.json"):
    """Save reports to JSON file"""
    with open(filename, "w") as f:
        json.dump(reports, f, indent=2, ensure_ascii=False)

def extract_file_id_from_url(url):
    """Extract fileId from the URL"""
    if url and 'fileId=' in url:
        try:
            return url.split('fileId=')[1].split('&')[0]
        except:
            return None
    return None

def convert_date_to_iso(date_str):
    """Convert MM/DD/YYYY date to YYYY-MM-DD format"""
    try:
        # Parse the MM/DD/YYYY format
        date_obj = datetime.strptime(date_str, "%m/%d/%Y")
        # Return in ISO format
        return date_obj.strftime("%Y-%m-%d")
    except ValueError:
        # If conversion fails, return original string
        return date_str

def create_report_key(report):
    """Create a unique key for a report based on URL or title+date"""
    if report.get('url'):
        return report['url']
    else:
        # Fallback to title + date if no URL
        return f"{report.get('title', '')}__{report.get('date', '')}"

def backfill_file_ids(reports):
    """Add file_id to existing reports that don't have it"""
    updated_count = 0
    for report in reports:
        if 'file_id' not in report and report.get('url'):
            file_id = extract_file_id_from_url(report['url'])
            report['file_id'] = file_id
            if file_id:
                updated_count += 1
    return updated_count

def run_scraper():
    # Load existing reports
    existing_reports = load_existing_reports()
    
    # Backfill file_ids for existing reports
    backfilled_count = backfill_file_ids(existing_reports)
    if backfilled_count > 0:
        print(f"Backfilled file_id for {backfilled_count} existing reports")
    
    existing_keys = {create_report_key(report) for report in existing_reports}
    
    with sync_playwright() as p:
        # Launch browser (use headless=False to see the browser in action)
        browser = p.chromium.launch(headless=True)
        
        # Create a new page
        page = browser.new_page()
        
        # Set user agent and other headers
        page.set_extra_http_headers({
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
        
        # Navigate to the URL
        url = 'https://www.ola.state.md.us/Search/Report?keyword=&agencyId=&dateFrom=&dateTo='
        page.goto(url, wait_until='networkidle')
        
        # Wait for the table to load
        page.wait_for_selector('tbody')
        
        # Extract data using Playwright's DOM querying
        new_reports = []
        
        # Get all table rows
        rows = page.query_selector_all('tbody tr')
        
        for row in rows:
            cells = row.query_selector_all('td')
            
            if len(cells) >= 3:  # Ensure we have enough cells
                report = {}
                
                # Extract date (first cell) and convert to ISO format
                raw_date = cells[0].inner_text().strip()
                report['date'] = convert_date_to_iso(raw_date)
                
                # Extract type (second cell)
                report['type'] = cells[1].inner_text().strip()
                
                # Extract title and URL (third cell)
                title_cell = cells[2]
                report['title'] = title_cell.inner_text().strip()
                
                # Check if cell contains a link
                link = title_cell.query_selector('a')
                if link:
                    href = link.get_attribute('href')
                    if href:
                        report['url'] = "https://www.ola.state.md.us" + href
                        # Extract file_id from URL
                        report['file_id'] = extract_file_id_from_url(report['url'])
                else:
                    report['url'] = None
                    report['file_id'] = None
                
                # Add scraped timestamp
                report['scraped_at'] = datetime.now().isoformat()
                
                # Check if this is a new report
                report_key = create_report_key(report)
                if report_key not in existing_keys:
                    new_reports.append(report)
        
        # Close the browser
        browser.close()
    
    # Combine existing and new reports
    all_reports = existing_reports + new_reports
    
    # Save all reports
    save_reports(all_reports)
    
    print(f"Found {len(new_reports)} new reports")
    print(f"Total reports in database: {len(all_reports)}")
    
    if new_reports:
        print("\nNew reports:")
        for report in new_reports:
            print(f"  - {report['date']}: {report['title'][:80]}...")
    
    return new_reports

if __name__ == "__main__":
    run_scraper()