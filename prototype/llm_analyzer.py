import os
import llm
from utils import load_text_files_for_agency

def compress_text_for_model(text, model_name, max_chars=80000):
    """Compress text based on model capabilities"""
    
    # Define model context limits (conservative estimates)
    # Order matters! More specific patterns should come first
    model_limits = {
        'llama-4-scout': 80000,  # Llama4 Scout can handle more
        'qwen3-32b': 20000,  # Qwen3-32b on Groq has 6000 token/min limit (~20k chars)
        'gemini-2.5-pro': 150000,
        'gemini-2.5-flash': 100000,  # Gemini models can handle more
        'gemini-2.0': 120000,
        'groq': 30000,  # Most other Groq models have smaller context windows
        'llama': 30000,
        'gpt-4o-mini': 80000
    }
    
    # Determine the appropriate limit for this model
    char_limit = max_chars
    for model_key, limit in model_limits.items():
        if model_key.lower() in model_name.lower():
            char_limit = min(char_limit, limit)
            break
    
    print(f"Using character limit of {char_limit} for model {model_name}")
    
    if len(text) <= char_limit:
        return text
    
    # For compression, prioritize recent content and key sections
    # Split by report sections
    sections = text.split('--- [Report')
    if len(sections) <= 1:
        # If no clear sections, just truncate
        return text[:char_limit]
    
    # Keep the first few reports (most recent) and key findings
    compressed_text = sections[0]  # Introduction/header
    
    for i, section in enumerate(sections[1:], 1):
        section_with_header = f'--- [Report{section}'
        
        # Try to fit full reports first, compress only when necessary
        if len(compressed_text) + len(section_with_header) < char_limit:
            # If there's room, include the full report
            compressed_text += section_with_header
        elif '[RECENT/HIGH PRIORITY]' in section:
            # For high priority reports, compress but try to keep more content
            compressed_section = compress_single_section(section_with_header, 
                                                       char_limit - len(compressed_text))
            if len(compressed_text) + len(compressed_section) < char_limit:
                compressed_text += compressed_section
            break
        else:
            # For lower priority reports, use key findings only when space is tight
            remaining_space = char_limit - len(compressed_text)
            if remaining_space > len(section_with_header) * 0.3:  # If we have at least 30% space
                # Try compressed version first
                compressed_section = compress_single_section(section_with_header, remaining_space)
                if len(compressed_section) > 0:
                    compressed_text += compressed_section
                break
            else:
                # Only use key findings if space is very limited
                key_findings = extract_key_findings(section_with_header)
                if len(compressed_text) + len(key_findings) < char_limit:
                    compressed_text += key_findings
                else:
                    break
    
    return compressed_text

def compress_single_section(section, max_chars):
    """Compress a single report section to fit within character limit"""
    if len(section) <= max_chars:
        return section
    
    lines = section.split('\n')
    compressed = []
    char_count = 0
    
    # Keep header and key sections
    for line in lines:
        line_lower = line.lower()
        # Prioritize lines with key audit terms
        is_important = any(keyword in line_lower for keyword in [
            'finding', 'recommendation', 'deficiency', 'violation', 
            'fraud', 'abuse', 'error', 'weakness', 'non-compliance',
            'significant', 'material', 'internal control', 'financial'
        ])
        
        if is_important or char_count < max_chars * 0.3:  # Keep first 30% regardless
            if char_count + len(line) + 1 <= max_chars:
                compressed.append(line)
                char_count += len(line) + 1
            else:
                break
        elif char_count < max_chars * 0.8:  # Be selective for middle portion
            if is_important and char_count + len(line) + 1 <= max_chars:
                compressed.append(line)
                char_count += len(line) + 1
    
    return '\n'.join(compressed)

def extract_key_findings(section):
    """Extract only key findings from a report section"""
    lines = section.split('\n')
    key_lines = []
    
    # Keep header
    if lines:
        key_lines.append(lines[0])
    
    # Extract lines with key audit findings
    for line in lines[1:]:
        line_lower = line.lower()
        if any(keyword in line_lower for keyword in [
            'finding', 'recommendation', 'deficiency', 'violation',
            'fraud', 'abuse', 'material weakness', 'significant',
            'non-compliance', 'internal control deficiency'
        ]):
            key_lines.append(line)
    
    # Add summary note
    if len(key_lines) > 1:
        key_lines.append("[Report content compressed - key findings only]")
    
    return '\n'.join(key_lines)

def format_citations(citation_references):
    """Format citation references as HTML footnotes"""
    if not citation_references:
        return ""
    
    citations_html = "\n\n<h3>Sources</h3>\n<ol>\n"
    
    # Sort by citation number
    sorted_citations = sorted(citation_references.items(), key=lambda x: int(x[0].strip('[]')))
    
    for citation_key, citation_info in sorted_citations:
        title = citation_info['title']
        date = citation_info['date']
        report_type = citation_info['type']
        url = citation_info['url']
        
        citations_html += f'<li><strong>{title}</strong> ({report_type}, {date})'
        if url:
            citations_html += f' - <a href="{url}" target="_blank">View Report</a>'
        citations_html += '</li>\n'
    
    citations_html += "</ol>"
    return citations_html

def clean_html_response(text):
    """Remove HTML code block markers and thinking tokens from response text"""
    import re
    
    original_length = len(text)
    
    # Remove ```html at the beginning and ``` at the end
    text = re.sub(r'^```html\s*\n?', '', text, flags=re.MULTILINE)
    text = re.sub(r'\n?```\s*$', '', text, flags=re.MULTILINE)
    
    # Remove Qwen thinking mode output patterns (very conservative)
    # Only remove complete <thinking>...</thinking> blocks that are clearly thinking mode
    before_thinking = len(text)
    text = re.sub(r'<thinking>.*?</thinking>\s*', '', text, flags=re.DOTALL)
    after_thinking = len(text)
    
    # Only remove complete <think>...</think> blocks  
    text = re.sub(r'<think>.*?</think>\s*', '', text, flags=re.DOTALL)
    
    # Only remove orphaned opening/closing thinking tags (not content between them)
    text = re.sub(r'</?thinking[^>]*>\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'</?think[^>]*>\s*', '', text, flags=re.IGNORECASE)
    
    final_length = len(text)
    
    # Debug output to see what's being removed
    if original_length != final_length:
        print(f"Text cleanup: {original_length} -> {final_length} chars")
        if before_thinking != after_thinking:
            print(f"Removed thinking blocks: {before_thinking - after_thinking} chars")
    
    return text.strip()

def configure_llm():
    """Configure LLM with available models"""
    # API keys should be set via environment variables or llm keys command
    available_models = []
    
    try:
        # Test Groq models
        models = llm.get_models()
        for model in models:
            if 'groq' in model.model_id or 'gemini' in model.model_id:
                available_models.append(model.model_id)
    except Exception as e:
        print(f"Error getting LLM models: {e}")
    
    return available_models

def get_prompt_template():
    """Return the standard prompt template"""
    return """You are analyzing multiple Maryland legislative audit reports spanning several years for {agency_name}. Create a comprehensive reporting resource that synthesizes findings across all available audits, with priority given to the most recent reports marked as [RECENT/HIGH PRIORITY].

Format your response using HTML tags for proper web display. Use <h3> for section headers, <p> for paragraphs, <ul> and <li> for lists, and <strong> for emphasis.

Write for a general audience. Briefly explain any complex government or financial terms in plain language. Do not assume reader expertise in government operations or audit procedures.

**IMPORTANT: When referencing specific findings, issues, or recommendations, include citation numbers (e.g., [1], [2]) that correspond to the source reports. Use these citations for any specific claims, dollar amounts, dates, or findings you mention.**

Provide:

<h3>Agency Overview</h3>
<p>What this agency does and its role in Maryland government, explained in everyday terms</p>

<h3>Audit Timeline</h3>
<p>Brief note on the time span and number of audits reviewed</p>

<h3>Key Findings Across Audits</h3>
<p>The most significant findings, especially from recent audits (explain any technical terms). If no major issues were found, state that clearly:</p>
<ul>
<li>Recurring issues that appear across multiple audit cycles</li>
<li>New problems identified in recent audits</li>
<li>Financial management concerns</li>
<li>Compliance and operational issues</li>
<li>Progress or lack of progress on previous recommendations</li>
<li>If audits consistently show clean operations, note this as a positive finding</li>
</ul>

<h3>Why This Matters</h3>
<p>Explain in direct, plain language how these audit findings could affect Maryland residents' daily lives, tax dollars, or public services. Be specific about real-world impacts. If no issues were found, explain what this means for taxpayers and service delivery.</p>

<h3>Story Ideas and Follow-Up</h3>
<p>Concrete reporting opportunities based on these findings. If this agency shows no significant issues, suggest looking at agencies with more problematic audit histories. Otherwise, provide specific, actionable steps:</p>
<ul>
<li>If no major issues found: Consider investigating agencies with recurring audit problems instead</li>
<li>Specific questions to ask agency officials: "How much was spent on [specific issue]?" "When will [specific recommendation] be implemented?"</li>
<li>Exact documents to request: Personnel files, contracts with specific vendors, budget line items, correspondence about audit findings</li>
<li>Named positions to contact: Former [specific job titles], current whistleblowers, affected clients/residents, legislative oversight committee members</li>
<li>Precise dollar amounts, dates, and metrics to verify through independent sources</li>
<li>Specific comparison points: How does this agency's [metric] compare to [similar agency] or national averages?</li>
<li>Follow-up story angles: Has the agency met deadlines for fixes? Are problems getting worse or better?</li>
</ul>

Focus on patterns and trends across the audit history, not just individual incidents. Be factual and objective. Prioritize recent findings while noting persistent issues. Limit response to 600 words.

Audit Materials (arranged chronologically, most recent first):
{combined_text}"""

def analyze_agency(agency_name, preferred_model=None):
    """Analyze an agency using LLM with fallback models"""
    # Load text content for the agency
    combined_text, citation_references = load_text_files_for_agency(agency_name)
    
    if not combined_text:
        return {
            'success': False,
            'error': f"No audit text found for {agency_name}",
            'content': ''
        }
    
    # Get the actual reports to extract date information
    from utils import get_reports_for_agency, format_date_readable
    reports = get_reports_for_agency(agency_name)
    
    # Extract and sort dates
    dates = [r.get('date', '') for r in reports if r.get('date')]
    dates.sort(reverse=True)  # Most recent first
    
    date_range_raw = f"{dates[-1]} to {dates[0]}" if len(dates) > 1 else dates[0] if dates else "Unknown dates"
    date_range = f"{format_date_readable(dates[-1])} to {format_date_readable(dates[0])}" if len(dates) > 1 else format_date_readable(dates[0]) if dates else "Unknown dates"
    most_recent_date = format_date_readable(dates[0]) if dates else "Unknown"
    
    print(f"Total text length for {agency_name}: {len(combined_text)} characters")
    print(f"Number of reports found: {len(reports)}")
    print(f"Date range: {date_range}")
    print(f"Most recent audit: {most_recent_date}")
    
    # Prepare prompt
    prompt_template = get_prompt_template()
    
    # Enhanced prompt with date information
    prompt = f"""IMPORTANT: The audits span from {date_range}, with the most recent audit from {most_recent_date}. 
Make sure to clearly state this timeline in your "Audit Timeline" section.

{prompt_template}"""
    
    # Get models from environment variables - prioritize Gemini models
    default_model = os.getenv('DEFAULT_MODEL', 'gemini-2.5-flash')
    fallback_models_str = os.getenv('FALLBACK_MODELS', 'gemini-2.5-pro,groq/meta-llama/llama-4-scout-17b-16e-instruct')
    fallback_models = [m.strip() for m in fallback_models_str.split(',')]
    
    # Use preferred model if provided, otherwise use default order
    if preferred_model:
        # Put preferred model first, then add others as fallbacks
        all_models = [default_model] + fallback_models
        if preferred_model in all_models:
            models = [preferred_model] + [m for m in all_models if m != preferred_model]
        else:
            # If preferred model is not in our list, try it first anyway
            models = [preferred_model] + [default_model] + fallback_models
    else:
        # Use default order
        models = [default_model] + fallback_models
    
    for model_name in models:
        try:
            print(f"Trying model: {model_name}")
            
            # Compress text based on model capabilities
            text_to_use = compress_text_for_model(combined_text, model_name)
            print(f"Text being sent to {model_name}: {len(text_to_use)} characters")
            
            # Format the final prompt with compressed text
            final_prompt = prompt.format(
                agency_name=agency_name,
                combined_text=text_to_use
            )
            
            model = llm.get_model(model_name)
            
            # Model-specific options to control output format
            options = {}
            if 'gemini-2.5-flash' in model_name:
                options['thinking_budget'] = 0
            elif 'qwen' in model_name.lower():
                # Don't use any special options for Qwen - they seem to break it
                pass
            elif 'kimi' in model_name.lower():
                # Kimi has a lower max_tokens limit
                options.update({
                    'stream': False,
                    'max_tokens': 2000,  # Kimi's limit is 2048
                })
            elif 'groq' in model_name.lower():
                # General Groq options that might help
                options.update({
                    'stream': False,
                    'max_tokens': 4000,  # Reasonable limit to avoid excessive output
                })
            
            if options:
                response = model.prompt(final_prompt, **options)
            else:
                response = model.prompt(final_prompt)
            
            # Clean up HTML code block markers from the response
            content = clean_html_response(response.text())
            
            # Add formatted citations to the content
            citations = format_citations(citation_references)
            content_with_citations = content + citations
                
            return {
                'success': True,
                'model_used': model_name,
                'content': content_with_citations,
                'text_length': len(combined_text),
                'reports_analyzed': len(reports),
                'date_range': date_range,  # Readable format for display
                'most_recent_audit': most_recent_date
            }
        except Exception as e:
            print(f"Model {model_name} failed: {e}")
            continue
    
    return {
        'success': False,
        'error': "All LLM models failed",
        'content': ''
    }
