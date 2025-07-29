# Maryland Audit Reports Analyzer - Prototype

A Flask web application that uses AI to analyze Maryland legislative audit reports and identify newsworthy issues.

## Features

- **Agency Selection**: Choose from 3 test agencies (Department of Agriculture, Department of Transportation, University System of Maryland)
- **AI Analysis**: Uses multiple LLM models (Qwen3, Llama4 via Groq, Gemini) with automatic fallback
- **Newsworthy Focus**: Identifies fraud, financial mismanagement, policy failures, and public safety concerns
- **Clean UI**: Bootstrap-based responsive interface

## Setup

### Local Development (with uv)

1. **Install dependencies**:
   ```bash
   cd prototype
   uv sync
   ```

2. **Set up environment**:
   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

3. **Run the application**:
   ```bash
   uv run flask run --debug
   ```

### Deployment (with pip)

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Set up environment variables** (method varies by platform):
   - PythonAnywhere: Use Files tab to create .env file
   - Heroku: Use config vars
   - Other platforms: Set environment variables as appropriate

3. **Run the application**:
   ```bash
   python -m flask run
   ```

## Configuration

### Required API Keys

- **Groq API Key**: For Llama4 model access
  - Get from: https://console.groq.com/
  - Set as: `GROQ_API_KEY`

- **Google API Key**: For Gemini model access
  - Get from: https://aistudio.google.com/
  - Set as: `GOOGLE_API_KEY`

### Data Setup

The prototype expects the following data structure in the parent directory:
- `ola_reports.json`: Report metadata with file_id attributes
- `text/`: Directory containing extracted text files (named by file_id)

## API Endpoints

- `GET /`: Main web interface
- `GET /api/agencies`: List available agencies (JSON)
- `GET /api/analyze/<agency>`: Analyze reports for an agency (JSON)
- `GET /api/stats`: Agency statistics (JSON)

## Architecture

- **Frontend**: Bootstrap 5 + vanilla JavaScript
- **Backend**: Flask with modular components
- **AI Integration**: `llm` library with multiple model support
- **Data**: JSON file storage (prototype-level)

## Files

- `app.py`: Main Flask application
- `utils.py`: Data processing utilities
- `llm_analyzer.py`: AI analysis logic
- `templates/index.html`: Main web interface
- `static/style.css`: Custom styling
- `pyproject.toml`: uv dependency management
- `requirements.txt`: pip deployment dependencies

## Development Notes

- This is a **prototype** focusing on 3 agencies for testing
- University System sub-agencies are treated as distinct entities
- LLM fallback ensures reliability across different model providers
- Frontend uses progressive enhancement (works without JavaScript for basic functionality)

## Deployment Options

### PythonAnywhere (Recommended)
1. Upload prototype files to your account
2. Create a new web app with manual configuration
3. Set up virtual environment with `pip install -r requirements.txt`
4. Configure WSGI file to point to `app.py`
5. Add environment variables in the Files tab

### Other Platforms
- Heroku: Use `Procfile` with `web: python -m flask run --host=0.0.0.0 --port=$PORT`
- Railway: Use `nixpacks.toml` for configuration
- DigitalOcean App Platform: Use App Spec with Python runtime

## Next Steps

For a production version:
1. Add database storage (PostgreSQL/SQLite)
2. Implement user authentication
3. Add caching for expensive LLM operations
4. Expand to all agencies
5. Add email/webhook notifications for new reports
6. Implement advanced filtering and search
