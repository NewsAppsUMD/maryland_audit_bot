#!/usr/bin/env python3
"""
Fix date formats in ola_reports.json from MM/DD/YYYY to YYYY-MM-DD
"""

import json
from datetime import datetime

def convert_date(date_str):
    """Convert MM/DD/YYYY format to YYYY-MM-DD"""
    try:
        # Parse MM/DD/YYYY format
        date_obj = datetime.strptime(date_str, '%m/%d/%Y')
        # Return in YYYY-MM-DD format
        return date_obj.strftime('%Y-%m-%d')
    except ValueError:
        print(f"Warning: Could not parse date '{date_str}'")
        return date_str  # Return original if parsing fails

def fix_dates_in_reports():
    """Fix all dates in the reports JSON file"""
    
    # Load the reports
    with open('../ola_reports.json', 'r') as f:
        reports = json.load(f)
    
    print(f"Loaded {len(reports)} reports")
    
    # Convert dates
    converted_count = 0
    for report in reports:
        old_date = report.get('date', '')
        if old_date and '/' in old_date:  # Only convert MM/DD/YYYY format
            new_date = convert_date(old_date)
            if new_date != old_date:
                report['date'] = new_date
                converted_count += 1
                print(f"Converted: {old_date} -> {new_date}")
    
    print(f"Converted {converted_count} dates")
    
    # Save back to file
    with open('../ola_reports.json', 'w') as f:
        json.dump(reports, f, indent=2, ensure_ascii=False)
    
    print("Saved updated reports to ola_reports.json")
    
    # Also update the prototype copy
    with open('data/ola_reports.json', 'w') as f:
        json.dump(reports, f, indent=2, ensure_ascii=False)
    
    print("Updated prototype copy as well")

if __name__ == "__main__":
    fix_dates_in_reports()
