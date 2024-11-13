import os
from openai import OpenAI
from typing import List, Optional, Dict, Union, Generator, Any
import logging
import re
from datetime import datetime
from tenacity import retry, stop_after_attempt, wait_exponential
from cache_utils import cache_recommendation
from flask import Response, stream_with_context
import json
import threading
from openai.types.chat import ChatCompletionSystemMessageParam, ChatCompletionUserMessageParam

# Configure logging with more detailed format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
)
logger = logging.getLogger(__name__)

# OpenAI Configuration with validation
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    logger.error("OpenAI API key is not configured")
    raise ValueError("OpenAI API key is required")

# Initialize OpenAI client with optimization settings
openai_client = OpenAI(
    api_key=OPENAI_API_KEY,
    timeout=15.0,  # 15 seconds timeout
    max_retries=2
)

# Optimized system prompt for better token usage
SYSTEM_PROMPT = """You are an Odoo module expert. Recommend modules based on business requirements.
Focus on essential features and direct benefits. Be concise and specific."""

def get_module_icon(module_name: str) -> Dict[str, str]:
    """Get static module icon path with fallback to default."""
    module_slug = module_name.lower().replace(' ', '_')
    icon_path = f"/static/images/modules/{module_slug}.svg"
    default_icon = "/static/images/modules/default_module_icon.svg"
    
    if os.path.exists(f".{icon_path}"):
        return {
            'url': f"https://apps.odoo.com/apps/modules/browse?search={module_name.lower().replace(' ', '-')}",
            'image': icon_path
        }
    return {
        'url': f"https://apps.odoo.com/apps/modules/browse?search={module_name.lower().replace(' ', '-')}",
        'image': default_icon
    }

@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=2, max=10)
)
def stream_openai_response(prompt: str) -> Generator[str, None, None]:
    """Stream OpenAI API response with improved error handling and optimization."""
    try:
        messages = [
            ChatCompletionSystemMessageParam(role="system", content=SYSTEM_PROMPT),
            ChatCompletionUserMessageParam(role="user", content=prompt)
        ]
        
        response = openai_client.chat.completions.create(
            model="gpt-4",
            messages=messages,
            temperature=0.1,  # Reduced for more consistent responses
            max_tokens=500,  # Optimized token limit
            stream=True
        )
        
        for chunk in response:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
                
    except Exception as e:
        logger.error(f"Error streaming OpenAI response: {str(e)}", exc_info=True)
        yield json.dumps({"error": str(e)})

@cache_recommendation(expiration=3600)
def get_module_recommendations(
    requirements: str = "",
    industry: str = "",
    features: Optional[List[str]] = None,
    preferred_edition: str = "community",
    has_experience: str = "no",
    stream: bool = False
) -> Union[Dict[str, Any], Response]:
    """Get module recommendations with optimized processing and caching."""
    try:
        # Input validation
        if not requirements.strip():
            return {"error": "Requirements cannot be empty"}
        
        # Optimize context generation with list comprehension
        context_parts = [
            f"Industry: {industry}" if industry else None,
            f"Features needed: {', '.join(features) if features else ''}" if features else None,
            f"Edition: {preferred_edition.title()}" if preferred_edition else None,
            f"Odoo Experience: {'Yes' if has_experience == 'yes' else 'No'}",
            f"Requirements: {requirements}" if requirements else None
        ]
        
        context = "\n".join(filter(None, context_parts))
        
        # Optimized prompt for faster processing
        prompt = f'''Recommend 3-4 most relevant Odoo modules for:\n{context}\n
Format each module as:
Module: [Name]
Description: [Core functionality]
Features: [Key features]
Benefits: [Business value]'''

        if stream:
            return Response(
                stream_with_context(stream_openai_response(prompt)),
                content_type='text/event-stream'
            )

        messages = [
            ChatCompletionSystemMessageParam(role="system", content=SYSTEM_PROMPT),
            ChatCompletionUserMessageParam(role="user", content=prompt)
        ]

        response = openai_client.chat.completions.create(
            model="gpt-4",
            messages=messages,
            temperature=0.1,
            max_tokens=500
        )

        content = response.choices[0].message.content
        if not content:
            return {"error": "No recommendations generated"}

        modules = parse_module_response(content)
        if not modules:
            return {"error": "No valid recommendations found"}

        # Optimize module info collection with dictionary comprehension
        module_info = {module['name']: get_module_icon(module['name']) for module in modules}

        return {
            'text': content,
            'modules': modules,
            'urls': {name: info['url'] for name, info in module_info.items()},
            'images': {name: info['image'] for name, info in module_info.items()}
        }

    except Exception as e:
        logger.error(f"Error generating recommendations: {str(e)}", exc_info=True)
        return {"error": f"Unable to generate recommendations: {str(e)}"}

def parse_module_response(content: str) -> List[Dict[str, str]]:
    """Parse the OpenAI response with optimized processing."""
    if not content or not isinstance(content, str):
        return []
        
    modules = []
    pattern = r'(?:^|\n\n)(?:\d+\.|Module:)\s*(.*?)(?=(?:\n\n(?:\d+\.|Module:)|$))'
    
    try:
        sections = list(re.finditer(pattern, content, re.DOTALL))
        if not sections:
            return []
            
        # Process sections directly without thread pool
        modules = [
            result for section in sections
            if (result := parse_section(section.group(1).strip())) is not None
        ]
        
        return modules
        
    except Exception as e:
        logger.error(f"Error parsing module response: {str(e)}", exc_info=True)
        return []

def parse_section(section_text: str) -> Optional[Dict[str, str]]:
    """Parse individual module section with optimized processing."""
    try:
        lines = [line.strip() for line in section_text.split('\n') if line.strip()]
        if len(lines) < 2:
            return None
            
        module_name = re.sub(r'^(Module(?: Name)?:?\s*)', '', lines[0], flags=re.IGNORECASE)
        sections = {'description': [], 'features': [], 'benefits': []}
        current_key = 'description'
        
        for line in lines[1:]:
            lower_line = line.lower()
            if 'features:' in lower_line:
                current_key = 'features'
                line = re.sub(r'^Features:?\s*', '', line, flags=re.IGNORECASE)
            elif 'benefits:' in lower_line:
                current_key = 'benefits'
                line = re.sub(r'^Benefits:?\s*', '', line, flags=re.IGNORECASE)
            elif 'description:' in lower_line:
                current_key = 'description'
                line = re.sub(r'^Description:?\s*', '', line, flags=re.IGNORECASE)
            
            if line:
                sections[current_key].append(line)
        
        if module_name:
            return {
                'name': module_name,
                'description': ' '.join(sections['description']),
                'features': sections['features'],
                'benefits': sections['benefits']
            }
        return None
        
    except Exception as e:
        logger.error(f"Error processing module section: {str(e)}", exc_info=True)
        return None
