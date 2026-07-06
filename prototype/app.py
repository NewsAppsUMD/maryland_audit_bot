from flask import Flask, render_template, request, jsonify, abort
import os
from dotenv import load_dotenv
from utils import get_test_agencies, get_agency_stats
from llm_analyzer import analyze_agency

# Load environment variables
load_dotenv()

app = Flask(__name__)
secret_key = os.getenv('FLASK_SECRET_KEY')
if secret_key:
    app.secret_key = secret_key
else:
    app.secret_key = 'dev-secret-key-change-in-production'
    app.logger.warning(
        "FLASK_SECRET_KEY environment variable is not set! "
        "Falling back to an insecure development default. "
        "Set FLASK_SECRET_KEY before deploying this app anywhere real."
    )

def get_available_models():
    """Get list of available models with display information"""
    default_model = os.getenv('DEFAULT_MODEL', 'gemini-2.5-flash')
    fallback_models_str = os.getenv('FALLBACK_MODELS', 'gpt-5-mini,groq/meta-llama/llama-4-scout-17b-16e-instruct,groq/moonshotai/kimi-k2-instruct-0905,groq/qwen/qwen3-32b')
    fallback_models = [m.strip() for m in fallback_models_str.split(',')]
    
    all_models = [default_model] + fallback_models
    
    # Create model objects with display names
    models = []
    for i, model_id in enumerate(all_models):
        # Create a friendly display name
        display_name = model_id
        if 'gemini' in model_id:
            display_name = model_id.replace('gemini-', 'Gemini ').title()
        elif 'groq' in model_id:
            # Extract just the model name from groq URLs
            if '/' in model_id:
                display_name = model_id.split('/')[-1].replace('-', ' ').title()
        
        models.append({
            'id': model_id,
            'display_name': display_name,
            'is_default': i == 0
        })
    
    return models

@app.route('/')
def index():
    """Main page with agency selector"""
    agencies = get_test_agencies()
    stats = get_agency_stats()
    models = get_available_models()
    return render_template('index.html', agencies=agencies, stats=stats, models=models)

@app.route('/api/agencies')
def get_agencies():
    """API endpoint to get list of agencies"""
    return jsonify(get_test_agencies())

@app.route('/api/analyze/<agency_name>')
def analyze_agency_api(agency_name):
    """API endpoint to analyze an agency"""
    # Validate agency name
    if agency_name not in get_test_agencies():
        abort(404, description="Agency not found")
    
    # Get the selected model from query parameter
    selected_model = request.args.get('model')
    
    try:
        result = analyze_agency(agency_name, preferred_model=selected_model)
        return jsonify(result)
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'content': ''
        }), 500

@app.route('/api/stats')
def get_stats():
    """API endpoint to get agency statistics"""
    return jsonify(get_agency_stats())

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    # Check if data files exist
    from pathlib import Path
    data_path = Path(__file__).parent / "data" / "ola_reports.json"
    if not data_path.exists():
        print("WARNING: ola_reports.json not found in data/ directory")
        print("Please copy ola_reports.json from the main project")
    
    text_path = Path(__file__).parent / "data" / "text"
    if not text_path.exists():
        print("WARNING: text/ directory not found in data/")
        print("Please copy the text/ directory from the main project")
    
if __name__ == '__main__':
    print("Starting Maryland Audit Reports Prototype...")
    print("Available agencies:", get_test_agencies())
    app.run(debug=True, port=5000)
