import json
import os
from pathlib import Path
from datetime import datetime

def format_date_readable(date_str):
    """Convert YYYY-MM-DD date to readable format like 'March 15, 2025'"""
    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        return date_obj.strftime("%B %d, %Y")
    except ValueError:
        # If conversion fails, return original string
        return date_str

def get_test_agencies():
    """Return the 3 test agencies for the prototype"""
    return [
        "Division of Occupational and Professional Licensing",
        "Office of the Public Defender", 
        "Maryland Legal Services Corporation"
    ]

def load_reports_data():
    """Load the reports JSON data"""
    data_path = Path(__file__).parent / "data" / "ola_reports.json"
    try:
        with open(data_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: {data_path} not found. Please copy ola_reports.json to the data directory.")
        return []

def get_reports_for_agency(agency_name):
    """Get all reports for a specific agency"""
    reports = load_reports_data()
    agency_reports = []
    
    for report in reports:
        title = report.get('title', '')
        
        # Handle different agency matching strategies
        if agency_name == "Maryland Legal Services Corporation":
            # Match various health department variations
            if any(term in title for term in [
                "Maryland Legal Services Corporation", 
                "Legal Services Corporation"
            ]):
                agency_reports.append(report)
                
        elif agency_name == "Office of the Public Defender":
            # Exact match for this agency
            if "Public Defender" in title:
                agency_reports.append(report)
                
        elif agency_name == "Division of Occupational and Professional Licensing":
            # Match various licensing division variations
            if any(term in title for term in [
                "Division of Occupational and Professional Licensing",
                "Occupational and Professional Licensing"
            ]):
                agency_reports.append(report)
    
    return agency_reports

def load_text_files_for_agency(agency_name):
    """Load and combine all text files for an agency, prioritizing recent reports
    Returns: (combined_text, citation_references)
    """
    reports = get_reports_for_agency(agency_name)
    
    # Sort reports by date (most recent first)
    reports_with_dates = []
    reports_without_dates = []
    
    for report in reports:
        date = report.get('date', '')
        if date:
            reports_with_dates.append(report)
        else:
            reports_without_dates.append(report)
    
    # Sort dated reports by date (newest first) - dates are now in YYYY-MM-DD format
    def parse_date(date_str):
        try:
            # Handle YYYY-MM-DD format
            return datetime.strptime(date_str, '%Y-%m-%d')
        except:
            # Fallback to string sorting if parsing fails
            return date_str
    
    reports_with_dates.sort(key=lambda x: parse_date(x.get('date', '')), reverse=True)
    
    # Combine: dated reports first (newest to oldest), then undated reports
    sorted_reports = reports_with_dates + reports_without_dates
    
    combined_text = ""
    citation_references = {}  # Store citation information
    text_dir = Path(__file__).parent / "data" / "text"
    
    for i, report in enumerate(sorted_reports):
        file_id = report.get('file_id')
        if file_id:
            text_file = text_dir / f"{file_id}.txt"
            try:
                with open(text_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # Add clear separators and priority indicators
                    priority_indicator = f"[Report {i+1} of {len(sorted_reports)}]"
                    if i < 3:  # Mark first 3 as highest priority
                        priority_indicator += " [RECENT/HIGH PRIORITY]"
                    
                    # Create citation reference
                    citation_key = f"[{i+1}]"
                    citation_references[citation_key] = {
                        'title': report.get('title', 'Unknown'),
                        'date': format_date_readable(report.get('date', 'Unknown Date')),
                        'url': report.get('url', ''),
                        'type': report.get('type', 'Unknown Type')
                    }
                    
                    combined_text += f"\n\n--- {priority_indicator} {report.get('title', 'Unknown')} ({format_date_readable(report.get('date', 'Unknown Date'))}) {citation_key} ---\n"
                    combined_text += content
            except FileNotFoundError:
                print(f"Warning: Text file not found for {file_id}")
                continue
    
    return combined_text.strip(), citation_references

def get_agency_stats():
    """Get basic statistics about each test agency"""
    stats = {}
    for agency in get_test_agencies():
        reports = get_reports_for_agency(agency)
        stats[agency] = {
            'report_count': len(reports),
            'date_range': get_date_range(reports)
        }
    return stats

def get_date_range(reports):
    """Get the date range for a list of reports in readable format"""
    if not reports:
        return "No reports"
    
    dates = [r.get('date', '') for r in reports if r.get('date')]
    if not dates:
        return "Unknown dates"
    
    # Sort dates to get min and max
    dates.sort()
    min_date = format_date_readable(dates[0])
    max_date = format_date_readable(dates[-1])
    
    if min_date == max_date:
        return min_date
    else:
        return f"{min_date} to {max_date}"
