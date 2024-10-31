import os
from openai import OpenAI
from typing import List, Optional, Dict, Tuple, Any
import requests
from bs4 import BeautifulSoup
import json
import logging
from typing import Union

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

def format_features(features: Optional[List[str]]) -> str:
    """Format features list into a readable string."""
    if not features:
        return "No specific features selected"
    return ", ".join(features)

def get_module_info(module_name: str) -> Tuple[str, str]:
    """
    Get module URL and image URL from Odoo apps store with improved error handling
    Returns tuple of (module_url, image_url)
    """
    if not module_name:
        logger.warning("Empty module name provided to get_module_info")
        return "", ""
        
    base_url = "https://apps.odoo.com"
    search_url = f"{base_url}/apps/search?search={module_name}"
    
    try:
        response = requests.get(search_url, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        first_result = soup.find('div', class_='o_app_item')
        
        if first_result:
            module_link = first_result.find('a')
            img_tag = first_result.find('img')
            
            module_url = f"{base_url}{module_link['href']}" if module_link and 'href' in module_link.attrs else ""
            image_url = img_tag['src'] if img_tag and 'src' in img_tag.attrs else ""
            
            logger.info(f"Successfully found module info for {module_name}")
            return module_url, image_url
            
        logger.warning(f"No results found for module: {module_name}")
        return "", ""
        
    except requests.RequestException as e:
        logger.error(f"Request failed for module {module_name}: {str(e)}")
        return "", ""
    except Exception as e:
        logger.error(f"Unexpected error fetching module info for {module_name}: {str(e)}")
        return "", ""

def parse_module_response(content: str) -> List[Dict[str, str]]:
    """Parse the OpenAI response content into structured module data."""
    if not content or not isinstance(content, str):
        logger.error("Invalid content provided for parsing")
        return []
        
    modules = []
    try:
        # Split into module sections and process each
        module_sections = [s.strip() for s in content.split('\n\n') if s.strip()]
        
        for section in module_sections:
            lines = [line.strip() for line in section.split('\n') if line.strip()]
            if len(lines) < 2:
                continue
                
            # Extract module name and clean it
            module_name = lines[0]
            for char in ['*', '#', '-', '•']:
                module_name = module_name.replace(char, '').strip()
                
            # Get description (everything after the name)
            description = lines[1].strip()
            if not module_name or not description:
                continue
                
            # Get additional info
            module_url, image_url = get_module_info(module_name)
            
            modules.append({
                'name': module_name,
                'description': description,
                'url': module_url,
                'image': image_url
            })
            
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
    """
    Get module recommendations using OpenAI API with improved error handling
    and response processing
    """
    try:
        if not OPENAI_API_KEY:
            logger.error("OpenAI API key is not configured")
            return {"error": "OpenAI API key is not configured"}

        # Create context from inputs
        context_parts = []
        if industry:
            context_parts.append(f"Industry: {industry}")
        if features:
            context_parts.append(f"Required Features: {format_features(features)}")
        if preferred_edition:
            context_parts.append(f"Preferred Edition: {preferred_edition.title()}")
        context_parts.append(f"Previous Odoo Experience: {'Yes' if has_experience == 'yes' else 'No'}")
        if requirements:
            context_parts.append(f"Additional Requirements: {requirements}")

        context = "\n".join(context_parts)
        logger.info("Generated context for recommendation request")

        prompt = f'''As an Odoo technical consultant with extensive experience, recommend 4 official Odoo modules that best address the following business requirements.

Business Context:
{context}

For each module provide:
1. Module Name (official Odoo module name)
2. One-line description highlighting the core business value and primary use case

Important considerations:
- Recommend only official Odoo modules from the Odoo Apps store
- Focus on modules that integrate well with each other
- Consider scalability and future business growth
- Prioritize modules based on the industry-specific needs
- Take into account the required features for the best fit
- Consider the user's Odoo experience level when suggesting modules
- Ensure recommendations align with the preferred Odoo edition (Community/Enterprise)
- For users new to Odoo, prioritize more user-friendly modules
- For experienced users, consider more advanced modules if appropriate

Present each recommendation in a clear, structured format:
Module Name
[Concise description focused on business value]'''

        logger.info("Making OpenAI API request")
        response = openai_client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=1000
        )

        if not response or not response.choices:
            logger.error("Empty or invalid response from OpenAI API")
            return {"error": "Failed to generate recommendations"}

        content = response.choices[0].message.content
        if not content:
            logger.error("Empty content in OpenAI API response")
            return {"error": "No recommendations generated"}

        # Parse modules with improved error handling
        modules = parse_module_response(content)
        if not modules:
            logger.error("No valid modules parsed from response")
            return {"error": "No valid recommendations found"}

        # Prepare the response
        urls = {module['name']: module['url'] for module in modules if module['url']}
        images = {module['name']: module['image'] for module in modules if module['image']}

        return {
            'text': content,
            'modules': modules,
            'urls': urls,
            'images': images
        }

    except Exception as e:
        logger.error(f"Error generating recommendations: {str(e)}")
        return {"error": f"Unable to generate recommendations: {str(e)}"}
