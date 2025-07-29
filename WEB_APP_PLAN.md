# Maryland Audit Reports Web Application Plan

## Overview
This document outlines the plan to create a Flask-based web application that analyzes Maryland legislative audit reports and generates AI-powered summaries of potential newsworthy issues by agency.

## Application Features

### Core Functionality
1. **Agency Selection**: Display a dropdown/list of distinct agencies from audit reports in alphabetical order
2. **Dynamic Analysis**: When an agency is selected, collect all related audit texts and submit them to an LLM
3. **AI-Generated Summary**: Display a professional journalism-focused summary of potential newsworthy issues
4. **Single-Page Design**: Simple, responsive interface with dropdown selection and results display

## Technical Architecture

### Technology Stack
- **Backend**: Python Flask
- **Frontend**: HTML/CSS/JavaScript with Bootstrap for responsive design
- **AI Integration**: Python `llm` library
- **Data Storage**: JSON files (existing structure)
- **Deployment**: PythonAnywhere (recommended), Heroku, DigitalOcean, or similar

### Project Structure
```
maryland_audit_webapp/
├── app.py                 # Main Flask application
├── pyproject.toml         # uv project configuration (local dev)
├── requirements.txt       # pip requirements (deployment)
├── uv.lock               # uv lockfile (local dev)
├── config.py             # Configuration settings
├── static/
│   ├── css/
│   │   └── style.css     # Custom styles
│   └── js/
│       └── app.js        # Frontend JavaScript
├── templates/
│   ├── base.html         # Base template
│   └── index.html        # Main page template
├── data/
│   ├── ola_reports.json  # Reports metadata (copy from existing)
│   └── text/             # Text files directory (copy from existing)
└── utils/
    ├── __init__.py
    ├── data_processor.py # Data processing utilities
    └── llm_analyzer.py   # LLM integration
```

## Implementation Plan

### Phase 1: Data Processing & Backend Setup

#### 1.1 Data Analysis & Processing (`utils/data_processor.py`)
```python
# Key functions needed:
- extract_unique_agencies() -> List[str]
- get_reports_by_agency(agency_name: str) -> List[dict]
- load_text_files_for_agency(agency_name: str) -> str
- clean_agency_names() -> standardize naming
```

**Agency Name Extraction Strategy:**
- Parse all `title` fields from `ola_reports.json`
- Extract base agency names (remove sub-divisions, dates, specific program names)
- Handle variations like:
  - "Department of Agriculture" vs "Maryland Department of Agriculture"
  - **Special Case - University System**: Keep individual universities as distinct agencies:
    - "University System of Maryland - Bowie State University" → "Bowie State University"
    - "University System of Maryland - Towson University" → "Towson University"
    - "University System of Maryland - University of Maryland, College Park" → "University of Maryland, College Park"
  - "Office of the Clerk of Circuit Court - Baltimore County" → "Office of the Clerk of Circuit Court"

#### 1.2 LLM Integration (`utils/llm_analyzer.py`)
```python
# Core functionality:
- configure_llm_models() -> setup with API keys for multiple providers
- analyze_agency_reports(combined_text: str, agency_name: str, model: str = "qwen3") -> str
- handle_rate_limiting() -> manage API calls across providers
- cache_results() -> optional caching for performance
- model_fallback() -> switch between Qwen3, Llama4, and Gemini if needed
```

**Supported LLM Models:**
- **Primary**: Qwen3 via Groq (fast, cost-effective)
- **Secondary**: Llama4 via Groq (alternative model)
- **Backup**: Gemini via Google AI (fallback option)

**LLM Setup Requirements:**
```bash
# Local development with uv:
uv add llm
uv run llm-install llm-groq llm-gemini

# Configure API keys (same for both local and deployment)
llm keys set groq  # Enter Groq API key
llm keys set gemini  # Enter Google AI API key

# Test model availability
uv run llm models list  # Should show qwen3, llama4, gemini models

# For deployment, generate requirements.txt:
uv pip compile pyproject.toml -o requirements.txt
```

**LLM Prompt Template:**
```
You are a professional reporter who covers Maryland government. Based on the material included, prepare a high-level overview of potential newsworthy issues surfaced in legislative audit reports for {agency_name}, prioritizing more recent and more significant issues, including fraud or abuse and those that impact the most people or have the potential to cause significant harm. Cite a few examples with references to the audits, but do not go into great detail. The result should be no longer than 500 words.

Audit Materials:
{combined_text}
```

**Model Selection Strategy:**
```python
# Example implementation for model selection
def get_available_model():
    """Select best available model with fallback"""
    try:
        # Try Qwen3 first (fast, efficient for analysis)
        return "groq:qwen2.5-72b-instruct"
    except:
        try:
            # Fallback to Llama4 via Groq
            return "groq:llama-3.1-70b-versatile"
        except:
            # Final fallback to Gemini
            return "gemini:gemini-1.5-flash"

def analyze_with_model_fallback(text, agency_name):
    """Analyze with automatic model fallback"""
    models = [
        "groq:qwen2.5-72b-instruct",
        "groq:llama-3.1-70b-versatile", 
        "gemini:gemini-1.5-flash"
    ]
    
    for model in models:
        try:
            return llm.prompt(prompt_template, model=model)
        except Exception as e:
            print(f"Model {model} failed: {e}")
            continue
    
    raise Exception("All LLM models failed")
```

### Phase 2: Flask Application (`app.py`)

#### 2.1 Core Routes
```python
@app.route('/')
def index():
    # Load and display agency list
    
@app.route('/api/agencies')
def get_agencies():
    # Return JSON list of agencies
    
@app.route('/api/analyze/<agency_name>')
def analyze_agency(agency_name):
    # Process agency reports and return LLM analysis
    
@app.route('/api/status/<task_id>')
def check_status(task_id):
    # For async processing if needed
```

#### 2.2 Error Handling & Validation
- Validate agency names against known list
- Handle missing text files gracefully
- Implement rate limiting for LLM calls
- Provide meaningful error messages to users

### Phase 3: Frontend Development

#### 3.1 User Interface (`templates/index.html`)
- **Header**: Application title and description
- **Agency Selector**: Searchable dropdown with all agencies
- **Loading State**: Progress indicator during analysis
- **Results Section**: Formatted display of AI analysis
- **Responsive Design**: Mobile-friendly layout

#### 3.2 JavaScript Functionality (`static/js/app.js`)
```javascript
// Key features:
- populateAgencyDropdown()
- handleAgencySelection()
- submitAnalysisRequest()
- displayResults()
- showLoadingState()
- errorHandling()
```

### Phase 4: Advanced Features (Optional)

#### 4.1 Caching System
- Cache LLM results to avoid repeated expensive API calls
- Use file-based caching or Redis for production
- Implement cache invalidation when new reports are added

#### 4.2 Batch Processing
- Pre-generate analyses for all agencies
- Run as background job daily/weekly
- Store results in database for instant retrieval

#### 4.3 Enhanced UI
- Agency search/filtering
- Download analysis as PDF
- Share analysis via URL
- Date range filtering for reports

## Data Processing Considerations

### Agency Name Standardization
The application will need to intelligently group reports by agency, handling variations such as:

1. **Sub-agencies and Divisions**:
   - "Maryland Department of Health - Medical Care Programs Administration" → "Maryland Department of Health"
   - **University System Exception**: Keep universities distinct:
     - "University System of Maryland - Bowie State University" → "Bowie State University"
     - "University System of Maryland - Salisbury University" → "Salisbury University"
     - "University System of Maryland - University of Maryland, Baltimore" → "University of Maryland, Baltimore"

2. **Naming Changes Over Time**:
   - "Department of Health and Mental Hygiene" → "Maryland Department of Health"
   - Historical vs. current agency names

3. **Similar Agencies**:
   - "Office of the Clerk of Circuit Court" (various counties)
   - "Office of the Register of Wills" (various counties)
   - **University System Universities**: Each treated as distinct agencies:
     - Bowie State University
     - Coppin State University  
     - Frostburg State University
     - Salisbury University
     - Towson University
     - University of Maryland, Baltimore
     - University of Maryland, College Park
     - University of Maryland Eastern Shore
     - University of Maryland Global Campus
     - University of Maryland, Baltimore County

### Text Processing Strategy
1. **File Identification**: Use `file_id` to match JSON records to text files
2. **Content Aggregation**: Combine all text files for selected agency
3. **Size Management**: Handle large text volumes (may need chunking for LLM)
4. **Date Prioritization**: Weight more recent reports higher in analysis

## Security & Performance

### Security Considerations
- Sanitize user inputs
- Validate file paths to prevent directory traversal
- Secure API key storage for LLM service
- Rate limiting on API endpoints

### Performance Optimization
- Implement caching for agency lists
- Lazy loading of text content
- Async processing for LLM calls
- Optimize JSON parsing and text file reading

## Deployment Plan

### PythonAnywhere Deployment (Recommended)

PythonAnywhere is ideal for this application because:
- **Simple Flask deployment** with built-in WSGI support
- **File storage included** - can upload JSON and text files directly
- **No Docker complexity** - straightforward Python environment
- **Cost-effective** - Free tier available, paid plans very affordable
- **Academic-friendly** - Popular with educational institutions

#### PythonAnywhere Setup Steps:

**1. Account Setup**
- Create PythonAnywhere account (free tier sufficient for prototype)
- Upgrade to paid plan for production (Hacker plan $5/month recommended)

**2. File Upload**
```bash
# Upload via web interface or use rsync
# Upload these directories:
/home/yourusername/maryland_audit_webapp/
├── app.py
├── requirements.txt
├── data/
│   ├── ola_reports.json
│   └── text/               # All text files
├── templates/
├── static/
└── utils/
```

**3. Environment Setup**
```bash
# In PythonAnywhere Bash console (using pip for deployment):
cd /home/yourusername/maryland_audit_webapp
pip3.10 install --user -r requirements.txt

# Install LLM plugins
pip3.10 install --user llm llm-groq llm-gemini

# Set environment variables in .env file
echo "GROQ_API_KEY=your_groq_api_key_here" > .env
echo "GEMINI_API_KEY=your_gemini_api_key_here" >> .env
echo "FLASK_SECRET_KEY=your_secret_key" >> .env

# Configure LLM keys (alternative method)
export GROQ_API_KEY=your_groq_api_key_here
export GEMINI_API_KEY=your_gemini_api_key_here

# Test LLM setup
python3.10 -c "import llm; print([m.model_id for m in llm.get_models()])"

# Note: requirements.txt should be generated from uv locally:
# uv pip compile pyproject.toml -o requirements.txt
```

**4. WSGI Configuration**
```python
# Edit /var/www/yourusername_pythonanywhere_com_wsgi.py
import sys
import os

# Add your project directory to the sys.path
path = '/home/yourusername/maryland_audit_webapp'
if path not in sys.path:
    sys.path.insert(0, path)

# Import your Flask app
from app import app as application

# Set environment variables for LLM providers
os.environ['GROQ_API_KEY'] = 'your_groq_api_key_here'
os.environ['GEMINI_API_KEY'] = 'your_gemini_api_key_here'
os.environ['FLASK_SECRET_KEY'] = 'your_secret_key'
```

**5. Web App Configuration**
- Go to "Web" tab in PythonAnywhere dashboard
- Create new web app (Flask, Python 3.10)
- Set source code directory: `/home/yourusername/maryland_audit_webapp`
- Set WSGI file path as configured above
- Reload web app

#### PythonAnywhere Advantages for This Project:
- **File Management**: Easy to upload and manage text files via web interface
- **No Database Required**: JSON files work perfectly
- **Persistent Storage**: Files remain available between deployments
- **HTTPS Included**: Free SSL certificates
- **Monitoring**: Built-in error logs and usage statistics
- **Easy Updates**: Simple file upload to update code or data

#### PythonAnywhere Limitations:
- **CPU Seconds**: Free tier has daily CPU limits (upgrade for production)
- **External API Calls**: LLM API calls count toward limits
- **Custom Domains**: Requires paid plan for custom domain names

### Alternative Deployment Options

#### Heroku Deployment
- **Pros**: Git-based deployment, easy scaling
- **Cons**: File storage requires add-ons, more complex for this use case
- **Setup**: Requires Procfile and handling of static files

#### DigitalOcean App Platform
- **Pros**: More control, competitive pricing
- **Cons**: Requires containerization or more setup
- **Best For**: Production applications with high traffic

### Development Environment
```bash
# Local development setup using uv:
1. Create project with uv: uv init maryland_audit_webapp
2. Add dependencies: uv add flask llm llm-groq llm-gemini python-dotenv
3. Set environment variables (LLM API keys)
4. Copy data files from existing project
5. Run: uv run python app.py

# Generate requirements.txt for deployment:
uv pip compile pyproject.toml -o requirements.txt
```

### Production Deployment Checklist
- **Environment Variables**: Groq API key, Gemini API key, Flask secret key
- **LLM Plugins**: Install llm-groq and llm-gemini plugins
- **Model Testing**: Verify all three models are accessible
- **File Storage**: Ensure text files are accessible (PythonAnywhere handles this)
- **Process Management**: PythonAnywhere handles WSGI automatically
- **Monitoring**: Use PythonAnywhere's built-in logs and error tracking
- **Backups**: Regular backup of data files and analysis cache
- **Rate Limiting**: Monitor API usage across Groq and Gemini
- **Model Fallback**: Test failover between Qwen3 → Llama4 → Gemini

## Dependencies 

**Local Development (`pyproject.toml`):**
```toml
[project]
name = "maryland-audit-webapp"
version = "0.1.0"
dependencies = [
    "flask>=2.3.3",
    "llm>=0.12.0",
    "llm-groq>=0.1.0",
    "llm-gemini>=0.1.0",
    "python-dotenv>=1.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest",
    "black",
    "flake8",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

**Deployment (`requirements.txt` - generated from uv):**
```
Flask==2.3.3
llm==0.12.0
llm-groq==0.1.0
llm-gemini==0.1.0
python-dotenv==1.0.0
gunicorn==21.2.0
requests==2.31.0
```

**Development Workflow:**
```bash
# Local development:
uv run python app.py        # Run locally with uv
uv add new-package          # Add new dependencies
uv pip compile pyproject.toml -o requirements.txt  # Update for deployment

# Deployment preparation:
git add requirements.txt    # Commit updated requirements
# Upload requirements.txt to PythonAnywhere
```

**LLM Model Comparison:**

| Model | Provider | Speed | Cost | Best For |
|-------|----------|-------|------- |----------|
| Qwen2.5-72B | Groq | Very Fast | Low | Primary analysis |
| Llama-3.1-70B | Groq | Fast | Low | Alternative analysis |
| Gemini-1.5-Flash | Google | Medium | Medium | Backup/fallback |

**Model Selection Logic:**
1. **Qwen3 (Primary)**: Fast inference via Groq, excellent for summarization tasks
2. **Llama4 (Secondary)**: Good alternative if Qwen3 is unavailable or rate-limited
3. **Gemini (Backup)**: Reliable fallback with different API limits

## Prototype Development Plan

### Rapid Prototype: 3-Agency MVP
For rapid development and testing, we recommend starting with a minimal viable product (MVP) focusing on just 3 representative agencies:

#### Recommended Test Agencies:
1. **Maryland Department of Health** - Large agency with many reports and sub-divisions
2. **Office of Administrative Hearings** - Smaller agency with fewer, simpler reports
3. **Bowie State University** - Individual university within the University System of Maryland

#### Prototype Scope Reduction:
- **No Agency Name Standardization**: Use exact titles from JSON, manually curate the 3 agencies
- **Simplified UI**: Basic dropdown without search functionality
- **No Caching**: Direct LLM calls for immediate feedback
- **Local Development Only**: Skip production deployment considerations
- **Hardcoded Agency List**: No complex parsing algorithm needed

#### Prototype Implementation Steps:

**Day 1: Data Setup (2-3 hours)**
```python
# Create simplified data_processor.py
def get_test_agencies():
    return [
        "Maryland Department of Health",
        "Office of Administrative Hearings", 
        "Bowie State University"
    ]

def get_reports_for_test_agency(agency_name):
    # Filter ola_reports.json for reports containing agency_name in title
    # For universities, match the specific university name after " - "
    # Return list of file_ids for that agency
```

**Day 2: Basic Flask App (4-5 hours)**
```python
# Minimal app.py
from flask import Flask, render_template, request, jsonify
import json
import os

@app.route('/')
def index():
    agencies = get_test_agencies()
    return render_template('index.html', agencies=agencies)

@app.route('/analyze/<agency>')
def analyze(agency):
    # Load text files for agency
    # Call LLM with simple prompt
    # Return results

# Local development: uv run python app.py
# Deployment: generate requirements.txt with uv pip compile
```

**Day 3: Frontend & LLM Integration (4-5 hours)**
- Basic HTML template with dropdown
- Simple JavaScript for AJAX calls
- LLM integration with hardcoded prompt
- Display results in text area

#### Prototype File Structure:
```
prototype/
├── app.py                    # 50 lines
├── pyproject.toml           # uv configuration (local)
├── requirements.txt         # pip requirements (deployment)
├── uv.lock                  # uv lockfile
├── templates/
│   └── index.html           # Simple single template
├── static/
│   └── style.css           # Basic styling
├── data/
│   ├── ola_reports.json    # Copy from main project
│   └── text/               # Copy subset of text files
└── utils.py                # 30 lines of helper functions
```

#### Prototype Benefits:
- **Quick Validation**: Test core concept in 1-2 days
- **LLM Cost Control**: Limit API usage to 3 agencies
- **Stakeholder Demo**: Show working prototype for feedback
- **Technical Risk Reduction**: Identify integration issues early
- **Scope Refinement**: Learn what features are actually needed

#### From Prototype to Full Application:
1. **Validate Approach**: Ensure LLM analysis quality meets expectations
2. **Test Performance**: Check response times with real text volumes
3. **Gather Feedback**: Show to stakeholders for UI/UX input
4. **Expand Gradually**: Add 5-10 more agencies, then implement full parsing
5. **Add Features**: Caching, better UI, error handling as needed

#### Prototype Limitations (Acceptable for MVP):
- Manual agency curation instead of algorithmic extraction
- No handling of agency name variations
- Basic error handling only
- No performance optimization
- Simple text concatenation (no intelligent chunking)

## Full Application Timeline

### Week 1: Backend Development
- Day 1-2: Data processing utilities
- Day 3-4: LLM integration
- Day 5-7: Flask application core

### Week 2: Frontend & Testing
- Day 1-3: HTML/CSS/JavaScript implementation
- Day 4-5: Integration testing
- Day 6-7: Performance optimization and bug fixes

### Week 3: Polish & Deployment
- Day 1-2: UI/UX improvements
- Day 3-4: Production deployment setup
- Day 5-7: Documentation and final testing

## Success Metrics
- **Functionality**: All agencies can be analyzed successfully
- **Performance**: Analysis completes within 30 seconds per agency
- **Accuracy**: LLM summaries are relevant and well-formatted
- **Usability**: Intuitive interface requiring no training
- **Reliability**: 99%+ uptime with proper error handling

## Future Enhancements
1. **Multi-agency Comparison**: Compare issues across agencies
2. **Trend Analysis**: Track issues over time
3. **Alert System**: Notify of new significant findings
4. **Data Visualization**: Charts showing audit trends
5. **Export Features**: PDF reports, CSV data export
6. **User Authentication**: Save favorite agencies, custom alerts
