import os
from openai import OpenAI
from typing import List, Optional, Dict, Tuple, Any, Union, Generator
import requests
from bs4 import BeautifulSoup
import json
import logging
import re
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import time
from threading import Lock
from datetime import datetime, timedelta
import asyncio
import aiohttp
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from cache_utils import cache_with_redis
from flask import Response, stream_with_context
import queue
import threading

# Configure logging with more detailed format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s - %(filename)s:%(lineno)d'
)
logger = logging.getLogger(__name__)

# OpenAI Configuration
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    logger.error("OpenAI API key is not configured")
    raise ValueError("OpenAI API key is required")

openai_client = OpenAI(api_key=OPENAI_API_KEY)

# Optimized token usage with shorter prompts
SYSTEM_PROMPT = """You are an Odoo module expert. Recommend modules based on business requirements.
Focus on essential features and direct benefits. Be concise and specific."""

# Image generation queue with size limit
image_queue = queue.Queue(maxsize=100)

def process_image_queue():
    """Background thread for processing image generation requests with improved error handling."""
    while True:
        try:
            task = image_queue.get(timeout=60)  # 1-minute timeout
            if task is None:
                break
                
            module_name, callback = task
            image_info = generate_module_image(module_name)
            if callback:
                callback(image_info)
                
        except queue.Empty:
            continue
        except Exception as e:
            logger.error(f"Error processing image queue: {str(e)}", exc_info=True)
        finally:
            image_queue.task_done()

# Start image processing thread
image_thread = threading.Thread(target=process_image_queue, daemon=True)
image_thread.start()

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type((TimeoutError, ConnectionError))
)
def generate_module_image(module_name: str) -> Dict[str, str]:
    """Generate module image using DALL-E with optimized prompt."""
    try:
        # Shorter, more focused prompt for token efficiency
        prompt = f"Minimal icon for Odoo {module_name} module. Modern business style, purple theme."
        
        response = openai_client.images.generate(
            prompt=prompt,
            size="256x256",
            quality="standard",
            n=1,
        )
        
        image_url = response.data[0].url
        module_url = f"https://apps.odoo.com/apps/modules/browse?search={module_name.lower().replace(' ', '-')}"
        
        return {
            'url': module_url,
            'image': image_url
        }
    except Exception as e:
        logger.error(f"Error generating image for {module_name}: {str(e)}", exc_info=True)
        return {
            'url': f"https://apps.odoo.com/apps/modules/browse?search={module_name.lower().replace(' ', '-')}",
            'image': "/static/images/default_module_icon.svg"
        }

def stream_openai_response(prompt: str) -> Generator[str, None, None]:
    """Stream OpenAI API response with improved error handling."""
    try:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ]
        
        response = openai_client.chat.completions.create(
            model="gpt-4",
            messages=messages,
            temperature=0.2,
            max_tokens=1000,  # Reduced for efficiency
            stream=True
        )
        
        for chunk in response:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
                
    except Exception as e:
        logger.error(f"Error streaming OpenAI response: {str(e)}", exc_info=True)
        yield json.dumps({"error": str(e)})

@cache_with_redis(expiration=3600)  # Cache for 1 hour
def get_module_recommendations(
    requirements: str = "",
    industry: str = "",
    features: Optional[List[str]] = None,
    preferred_edition: str = "community",
    has_experience: str = "no",
    stream: bool = False
) -> Union[Dict[str, Any], Response]:
    """Get module recommendations with streaming support and optimizations."""
    try:
        if not OPENAI_API_KEY:
            logger.error("OpenAI API key is not configured")
            return {"error": "OpenAI API key is not configured"}

        # Optimize context generation with list comprehension
        context_parts = [
            f"Industry: {industry}" if industry else None,
            f"Features: {', '.join(features)}" if features else None,
            f"Edition: {preferred_edition.title()}" if preferred_edition else None,
            f"Experience: {'Yes' if has_experience == 'yes' else 'No'}",
            f"Requirements: {requirements}" if requirements else None
        ]
        
        # Filter out None values and join
        context = "\n".join(filter(None, context_parts))

        # Optimized prompt for reduced token usage
        prompt = f'''Recommend 4 Odoo modules for:\n{context}\n\nFormat:\nModule: [Name]\nDescription: [Core functionality]\nFeatures: [Key features]\nBenefits: [Value]'''

        if stream:
            return Response(
                stream_with_context(stream_openai_response(prompt)),
                content_type='text/event-stream'
            )

        # Non-streaming response with retry
        response = openai_client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=1000
        )

        content = response.choices[0].message.content
        if not content:
            return {"error": "No recommendations generated"}

        # Parse modules with improved error handling
        modules = parse_module_response(content)
        if not modules:
            return {"error": "No valid recommendations found"}

        # Queue image generation with timeout handling
        module_info = {}
        for module in modules:
            try:
                image_queue.put(
                    (module['name'], lambda info, name=module['name']: module_info.update({name: info})),
                    timeout=5
                )
            except queue.Full:
                logger.warning(f"Image generation queue full, skipping image for {module['name']}")

        result = {
            'text': content,
            'modules': modules,
            'urls': {name: info['url'] for name, info in module_info.items()},
            'images': {name: info['image'] for name, info in module_info.items()}
        }

        return result

    except Exception as e:
        logger.error(f"Error generating recommendations: {str(e)}", exc_info=True)
        return {"error": f"Unable to generate recommendations: {str(e)}"}

def parse_module_response(content: str) -> List[Dict[str, str]]:
    """Parse the OpenAI response content into structured module data with improved error handling."""
    if not content or not isinstance(content, str):
        logger.error("Invalid content provided for parsing")
        return []
        
    modules = []
    try:
        pattern = r'(?:^|\n\n)(?:\d+\.|Module:)\s*(.*?)(?=(?:\n\n(?:\d+\.|Module:)|$))'
        sections = list(re.finditer(pattern, content, re.DOTALL))
        
        if not sections:
            return []
            
        # Process sections with optimized thread pool
        with ThreadPoolExecutor(max_workers=min(4, len(sections))) as executor:
            futures = []
            for section in sections:
                futures.append(executor.submit(parse_section, section.group(1).strip()))
            
            for future in futures:
                try:
                    result = future.result(timeout=5)
                    if result:
                        modules.append(result)
                except TimeoutError:
                    logger.error("Timeout processing module section")
                    continue
                    
        return modules
        
    except Exception as e:
        logger.error(f"Error parsing module response: {str(e)}", exc_info=True)
        return []

def parse_section(section_text: str) -> Optional[Dict[str, str]]:
    """Parse a single module section with improved error handling."""
    try:
        lines = [line.strip() for line in section_text.split('\n') if line.strip()]
        if len(lines) < 2:
            return None
            
        module_name = re.sub(r'^(Module(?: Name)?:?\s*)', '', lines[0], flags=re.IGNORECASE)
        module_name = module_name.strip()
        
        description_lines = []
        features_lines = []
        benefits_lines = []
        current_section = description_lines
        
        for line in lines[1:]:
            lower_line = line.lower()
            if lower_line.startswith('features:'):
                current_section = features_lines
                line = re.sub(r'^Features:?\s*', '', line, flags=re.IGNORECASE)
            elif lower_line.startswith('benefits:'):
                current_section = benefits_lines
                line = re.sub(r'^Benefits:?\s*', '', line, flags=re.IGNORECASE)
            elif lower_line.startswith('description:'):
                current_section = description_lines
                line = re.sub(r'^Description:?\s*', '', line, flags=re.IGNORECASE)
            current_section.append(line)
        
        if module_name:
            return {
                'name': module_name,
                'description': ' '.join(description_lines),
                'features': features_lines,
                'benefits': benefits_lines
            }
        return None
    except Exception as e:
        logger.error(f"Error processing module section: {str(e)}", exc_info=True)
        return None