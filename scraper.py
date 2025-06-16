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

def create_report_key(report):
    """Create a unique key for a report based on URL or title+date"""
    if report.get('url'):
        return report['url']
    else:
        # Fallback to title + date if no URL
        return f"{report.get('title', '')}__{report.get('date', '')}"

def run_scraper():
    # Load existing reports
    existing_reports = load_existing_reports()
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
                
                # Extract date (first cell)
                report['date'] = cells[0].inner_text().strip()
                
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
                else:
                    report['url'] = None
                
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