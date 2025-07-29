# Maryland Audit Bot - Development Notes

## Overview

This prototype is a web-based tool for analyzing Maryland legislative audit reports using Large Language Models (LLMs). It takes audit text data and generates journalistic analysis highlighting key findings, newsworthy issues, and follow-up opportunities.

## Architecture

### Core Components

1. **Flask Web Application** (`app.py`)
   - Simple web interface with agency selection and model choice
   - API endpoints for analysis and data retrieval
   - Model configuration management

2. **LLM Analysis Engine** (`llm_analyzer.py`)
   - Multi-model support with intelligent fallback
   - Text compression for model context limits
   - Model-specific configuration and output cleanup

3. **Data Utilities** (`utils.py`)
   - Text file loading and agency report aggregation
   - Date parsing and formatting
   - Agency statistics and metadata

4. **Frontend** (`templates/index.html`)
   - Bootstrap-based responsive interface
   - Dynamic model selection dropdown
   - Real-time analysis results display

## Key Design Decisions

### 1. Multi-Model LLM Support

**Decision**: Support multiple LLM providers (Google Gemini, Groq) with intelligent fallback.

**Rationale**: 
- Different models have different strengths for text analysis
- API rate limits and availability issues require fallbacks
- Cost optimization through model selection

**Implementation**:
- Environment-based model configuration
- Prioritized model list with automatic fallback
- User-selectable model override

### 2. Context-Aware Text Compression

**Decision**: Implement model-specific text compression rather than simple truncation.

**Rationale**:
- Models have vastly different context window sizes (20k to 150k characters)
- Simple truncation loses important recent audit findings
- Need to preserve both recent reports and key historical patterns

**Implementation**:
```python
model_limits = {
    'llama-4-scout': 80000,  # Llama4 Scout can handle more
    'qwen3-32b': 20000,      # Token rate limit constraints
    'gemini-2.5-pro': 150000,
    'gemini-2.5-flash': 100000,
    'groq': 30000,           # Default for most Groq models
}
```

**Compression Strategy**:
- Prioritize recent reports marked as `[RECENT/HIGH PRIORITY]`
- Extract key findings using keyword detection
- Preserve audit structure and context
- Include timeline information

### 3. Model-Specific Output Handling

**Decision**: Implement per-model configuration for API options and output cleanup.

**Rationale**: Each LLM has unique quirks and limitations:
- **Gemini 2.5 Flash**: Includes "thinking mode" output that needs suppression
- **Qwen3**: Outputs XML-style thinking blocks that need removal
- **Kimi**: Has strict token limits (2048 max_tokens vs 4000 for others)
- **Groq models**: Various rate and context limits

**Implementation**:
```python
if 'gemini-2.5-flash' in model_name:
    options['thinking_budget'] = 0
elif 'qwen' in model_name.lower():
    pass  # No special options - they break content generation
elif 'kimi' in model_name.lower():
    options.update({'stream': False, 'max_tokens': 2000})
elif 'groq' in model_name.lower():
    options.update({'stream': False, 'max_tokens': 4000})
```

### 4. Journalist-Focused Output Format

**Decision**: Structure output specifically for journalistic follow-up rather than general analysis.

**Rationale**:
- Target audience is investigative journalists
- Need actionable leads, not just summaries
- Require specific questions, contacts, and story angles

**Output Sections**:
- **Agency Overview**: Plain-language explanation
- **Audit Timeline**: Clear date ranges and scope
- **Key Findings**: Prioritized by newsworthiness
- **Why This Matters**: Real-world impact explanation
- **Story Ideas and Follow-Up**: Specific actionable items

## Technical Challenges and Solutions

### 1. LLM Context Window Management

**Challenge**: Audit reports often exceed model context limits.

**Solution**: Intelligent compression that preserves key information:
- Section-based splitting by report boundaries
- Keyword-based importance scoring
- Graduated compression (full → compressed → key findings only)
- Recent report prioritization

### 2. Rate Limiting and API Errors

**Challenge**: Different providers have varying rate limits and error patterns.

**Examples Encountered**:
- Groq Qwen3: 6000 tokens/minute limit (required 20k char limit)
- Kimi: 2048 max_tokens validation error
- Compound-beta: Model discontinued, needed removal

**Solution**: 
- Model-specific configuration with conservative limits
- Graceful fallback to alternative models
- Error logging and user feedback

### 3. Output Quality Control

**Challenge**: LLMs produce inconsistent output with model-specific artifacts.

**Issues Found**:
- Gemini: Unwanted "thinking mode" output
- Qwen3: XML-style `<thinking>` blocks
- General: HTML code block markers in responses

**Solution**: Conservative post-processing cleanup:
```python
# Remove only clearly marked thinking blocks
text = re.sub(r'<thinking>.*?</thinking>\s*', '', text, flags=re.DOTALL)
text = re.sub(r'<think>.*?</think>\s*', '', text, flags=re.DOTALL)
```

### 4. Date Handling Across Reports

**Challenge**: Inconsistent date formats across audit reports spanning 17+ years.

**Solution**: Robust date parsing with multiple format support and readable output formatting.

## Configuration Management

### Environment Variables

```bash
# Model Configuration
DEFAULT_MODEL=gemini-2.5-flash
FALLBACK_MODELS=groq/meta-llama/llama-4-scout-17b-16e-instruct,groq/moonshotai/kimi-k2-instruct,groq/qwen/qwen3-32b

# API Keys
GROQ_API_KEY=your_key_here
GOOGLE_API_KEY=your_key_here

# Data Paths
OLA_REPORTS_PATH=../ola_reports.json
TEXT_FILES_PATH=../text/
```

### Model Priority Order

1. **Primary**: Gemini 2.5 Flash (fast, high-quality, large context)
2. **Fallback 1**: Llama4 Scout (80k context, good reasoning)
3. **Fallback 2**: Kimi (reliable, moderate context)
4. **Fallback 3**: Qwen3 (when working, good analysis)

## Limitations and Trade-offs

### 1. Text Compression Limitations

- **Loss of Detail**: Compression may remove important context
- **Keyword Bias**: Relies on predefined audit keywords
- **Recency Bias**: May over-prioritize recent reports

### 2. Model Dependency

- **API Availability**: Dependent on external service uptime
- **Cost Scaling**: Analysis costs scale with usage
- **Quality Variation**: Different models produce varying output quality

### 3. Data Processing Constraints

- **Static Data**: Requires manual data updates
- **Text-Only**: No analysis of charts, tables, or images in PDFs
- **Format Dependency**: Assumes consistent audit report structure

### 4. User Experience Limitations

- **No Streaming**: Users must wait for complete analysis
- **No Caching**: Repeated analyses re-process same data
- **Single Agency**: No comparative analysis across agencies

## Lessons Learned

### 1. Model-Specific Tuning is Essential

Each LLM requires unique handling:
- API parameters that work for one model break another
- Output formats vary significantly
- Rate limits and context windows differ dramatically

### 2. Conservative Approaches Work Better

- Start with no special options, add only when needed
- Over-aggressive cleanup removes real content
- Fallback strategies are more important than optimization

### 3. Context Window Management is Critical

- Simple truncation loses the most important (recent) information
- Intelligent compression requires domain knowledge
- Model limits change frequently and vary by provider

### 4. User Feedback Drives Development

Key improvements came from real usage:
- Model selection dropdown (user choice preference)
- Better error handling (API failures)
- Improved text limits (rate limit errors)
- Output cleanup (artifact removal)

## Future Improvements

### Short Term

1. **Response Caching**: Cache analysis results to avoid re-processing
2. **Streaming Responses**: Real-time output for better UX
3. **Error Recovery**: More graceful handling of API failures
4. **Batch Processing**: Analyze multiple agencies simultaneously

### Medium Term

1. **Comparative Analysis**: Cross-agency trend analysis
2. **Data Pipeline**: Automated audit report ingestion
3. **Advanced Compression**: ML-based text summarization
4. **User Customization**: Configurable analysis focus areas

### Long Term

1. **Multi-Modal Analysis**: Process charts, tables, and images
2. **Real-Time Updates**: Live audit report monitoring
3. **Collaborative Features**: Multi-user analysis and sharing
4. **Advanced Analytics**: Trend analysis and predictive insights

## Development Setup

### Prerequisites

```bash
# Install dependencies
uv install

# Set up environment variables
cp .env.example .env
# Edit .env with your API keys

# Run the application
python app.py
```

### Key Files

- `app.py`: Flask application and routing
- `llm_analyzer.py`: Core LLM analysis logic
- `utils.py`: Data processing utilities
- `templates/index.html`: Frontend interface
- `.env`: Configuration and API keys

### Testing Strategy

1. **Model Testing**: Verify each LLM works with sample data
2. **Compression Testing**: Ensure text fits within model limits
3. **Output Testing**: Verify cleanup doesn't remove real content
4. **Error Testing**: Confirm graceful fallback behavior

## Conclusion

This prototype successfully demonstrates automated audit analysis using multiple LLMs. The key to success was building robust model-specific handling and intelligent text compression. While limitations exist, the tool provides valuable assistance for investigative journalism and could be extended for broader government transparency applications.

The most important lesson: **start simple, add complexity only when needed, and always prioritize graceful degradation over optimal performance**.
