import os
from openai import OpenAI
from typing import List, Optional, Dict, Tuple, Any, Union
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
from tenacity import retry, stop_after_attempt, wait_exponential

# Configure logging with more detailed format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    logger.error("OpenAI API key is not configured in environment variables")
    raise ValueError("OpenAI API key is required")

openai_client = OpenAI(api_key=OPENAI_API_KEY)

# Enhanced cache configuration
class CacheEntry:
    def __init__(self, data: Any, expiry: datetime):
        self.data = data
        self.expiry = expiry
        self.last_accessed = datetime.now()
        self.access_count = 0

class Cache:
    def __init__(self, max_size: int = 1000):
        self.data = {}
        self.max_size = max_size
        self.lock = Lock()
        
    def get(self, key: str) -> Optional[Any]:
        with self.lock:
            if key in self.data:
                entry = self.data[key]
                if datetime.now() < entry.expiry:
                    entry.last_accessed = datetime.now()
                    entry.access_count += 1
                    return entry.data
                else:
                    del self.data[key]
            return None
            
    def set(self, key: str, value: Any, expiry_minutes: int = 60):
        with self.lock:
            if len(self.data) >= self.max_size:
                # Remove least recently used items
                sorted_items = sorted(
                    self.data.items(),
                    key=lambda x: (x[1].last_accessed, -x[1].access_count)
                )
                for old_key, _ in sorted_items[:int(self.max_size * 0.2)]:
                    del self.data[old_key]
                    
            self.data[key] = CacheEntry(
                value,
                datetime.now() + timedelta(minutes=expiry_minutes)
            )

# Initialize caches with different expiration times
module_cache = Cache(max_size=1000)  # Cache for module information
recommendation_cache = Cache(max_size=500)  # Cache for recommendations

def format_features(features: Optional[List[str]]) -> str:
    """Format features list into a readable string."""
    if not features:
        return "No specific features selected"
    return ", ".join(features)

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10)
)
async def fetch_module_info(session: aiohttp.ClientSession, module_name: str) -> Dict[str, str]:
    """Asynchronously fetch module information."""
    try:
        # Generate DALL-E image with improved prompt
        prompt = f"""Create a professional, minimalist icon for an Odoo {module_name} module.
        Style: Modern, corporate, clean design
        Colors: Use purple and white as primary colors
        Layout: Simple, recognizable business software interface elements
        Theme: Professional enterprise software
        No text or words in the image"""
        
        response = await openai_client.images.generate(
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
        logger.error(f"Error fetching module info for {module_name}: {str(e)}")
        return {
            'url': f"https://apps.odoo.com/apps/modules/browse?search={module_name.lower().replace(' ', '-')}",
            'image': "/static/images/default_module_icon.svg"
        }

async def get_modules_info_batch(modules: List[str]) -> Dict[str, Dict[str, str]]:
    """Fetch module information in parallel using asyncio."""
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_module_info(session, module) for module in modules]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        return {
            module: result if not isinstance(result, Exception) else {
                'url': f"https://apps.odoo.com/apps/modules/browse?search={module.lower().replace(' ', '-')}",
                'image': "/static/images/default_module_icon.svg"
            }
            for module, result in zip(modules, results)
        }

def parse_module_response(content: str) -> List[Dict[str, str]]:
    """Parse the OpenAI response content into structured module data with improved parsing."""
    if not content or not isinstance(content, str):
        logger.error("Invalid content provided for parsing")
        return []
        
    modules = []
    try:
        pattern = r'(?:^|\n\n)(?:\d+\.|Module:)\s*(.*?)(?=(?:\n\n(?:\d+\.|Module:)|$))'
        sections = list(re.finditer(pattern, content, re.DOTALL))
        
        if not sections:
            return []
            
        # Process all sections in parallel
        with ThreadPoolExecutor(max_workers=min(4, len(sections))) as executor:
            def process_section(section_text: str) -> Optional[Dict[str, str]]:
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
                    logger.error(f"Error processing module section: {str(e)}")
                    return None
            
            futures = [executor.submit(process_section, section.group(1).strip()) 
                      for section in sections]
            
            for future in futures:
                try:
                    result = future.result(timeout=5)  # 5 second timeout for processing
                    if result:
                        modules.append(result)
                except TimeoutError:
                    logger.error("Timeout processing module section")
                    continue
                    
        return modules
        
    except Exception as e:
        logger.error(f"Error parsing module response: {str(e)}")
        return []

def get_module_recommendations(
    requirements: str = "",
    industry: str = "",
    features: Optional[List[str]] = None,
    preferred_edition: str = "community",
    has_experience: str = "no"
) -> Dict[str, Any]:
    """Get module recommendations using OpenAI API with enhanced caching and optimization."""
    try:
        if not OPENAI_API_KEY:
            logger.error("OpenAI API key is not configured")
            return {"error": "OpenAI API key is not configured"}

        # Generate cache key based on input parameters
        cache_key = f"rec_{hash((requirements, industry, str(features), preferred_edition, has_experience))}"
        
        # Check cache first
        cached_result = recommendation_cache.get(cache_key)
        if cached_result:
            logger.info("Returning cached recommendations")
            return cached_result

        # Create detailed context from inputs
        context_parts = []
        if industry:
            context_parts.append(f"Industry: {industry}")
            context_parts.append("Industry-specific requirements and best practices will be considered.")
        
        if features:
            context_parts.append(f"Required Features: {format_features(features)}")
            context_parts.append("These features are essential for the business operations.")
        
        if preferred_edition:
            edition_context = f"Preferred Edition: {preferred_edition.title()}"
            if preferred_edition.lower() == "community":
                edition_context += " (Focus on core features available in the free edition)"
            else:
                edition_context += " (Include advanced enterprise features)"
            context_parts.append(edition_context)
        
        experience_level = "Yes" if has_experience == "yes" else "No"
        context_parts.append(f"Previous Odoo Experience: {experience_level}")
        if experience_level == "No":
            context_parts.append("Recommendations should focus on user-friendly modules with good documentation and support.")
        
        if requirements:
            context_parts.append("Additional Requirements:")
            context_parts.append(requirements)

        context = "\n".join(context_parts)
        logger.info("Generated enhanced context for recommendation request")

        # Optimized prompt for faster and more focused responses
        prompt = f'''As an Odoo technical consultant, recommend 4 specific modules that best address these requirements:

Business Context:
{context}

Format each recommendation as:
Module: [Name]
Description: [Core functionality and benefits]
Features: [Key features]
Benefits: [Business value]'''

        logger.info("Making OpenAI API request with optimized prompt")
        response = openai_client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=1500,
            timeout=30  # Add timeout for API requests
        )

        if not response or not response.choices:
            logger.error("Empty or invalid response from OpenAI API")
            return {"error": "Failed to generate recommendations"}

        content = response.choices[0].message.content
        if not content:
            logger.error("Empty content in OpenAI API response")
            return {"error": "No recommendations generated"}

        # Parse modules with improved handling
        modules = parse_module_response(content)
        if not modules:
            logger.error("No valid modules parsed from response")
            return {"error": "No valid recommendations found"}

        # Fetch module information in parallel
        module_names = [module['name'] for module in modules]
        module_info = asyncio.run(get_modules_info_batch(module_names))

        # Prepare the response with module details
        result = {
            'text': content,
            'modules': modules,
            'urls': {name: info['url'] for name, info in module_info.items()},
            'images': {name: info['image'] for name, info in module_info.items()}
        }

        # Cache the result
        recommendation_cache.set(cache_key, result, expiry_minutes=60)

        return result

    except Exception as e:
        logger.error(f"Error generating recommendations: {str(e)}")
        return {"error": f"Unable to generate recommendations: {str(e)}"}
