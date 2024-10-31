import os
from openai import OpenAI
from typing import List, Optional, Dict, Tuple, Any
import requests
from bs4 import BeautifulSoup
import json
import logging
from typing import Union
import re

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
    """Get module URL and generate an image for the module."""
    base_url = "https://apps.odoo.com/apps/modules"
    search_query = module_name.lower().replace(" ", "-")
    url = f"{base_url}/browse?search={search_query}"
    
    try:
        # Generate DALL-E image for the module with improved prompt
        prompt = f"""Create a professional, minimalist icon for an Odoo {module_name} module.
        Style: Modern, corporate, clean design
        Colors: Use purple and white as primary colors
        Layout: Simple, recognizable business software interface elements
        Theme: Professional enterprise software
        No text or words in the image"""
        
        response = openai_client.images.generate(
            prompt=prompt,
            size="256x256",
            quality="standard",
            n=1,
        )
        image_url = response.data[0].url
        return url, image_url
    except Exception as e:
        logger.error(f"Error generating image for {module_name}: {str(e)}")
        return url, "/static/images/default_module_icon.svg"

def parse_module_response(content: str) -> List[Dict[str, str]]:
    """Parse the OpenAI response content into structured module data with improved parsing."""
    if not content or not isinstance(content, str):
        logger.error("Invalid content provided for parsing")
        return []
        
    modules = []
    try:
        # Split content into module sections
        pattern = r'(?:^|\n\n)(?:\d+\.|Module:)\s*(.*?)(?=(?:\n\n(?:\d+\.|Module:)|$))'
        sections = re.finditer(pattern, content, re.DOTALL)
        
        for section in sections:
            section_text = section.group(1).strip()
            lines = [line.strip() for line in section_text.split('\n') if line.strip()]
            
            if len(lines) < 2:
                continue
            
            # Extract module name and clean it
            module_name = re.sub(r'^(Module(?: Name)?:?\s*)', '', lines[0], flags=re.IGNORECASE)
            module_name = module_name.strip()
            
            # Extract description
            description_lines = []
            for line in lines[1:]:
                if line.lower().startswith(('description:', 'features:', 'benefits:')):
                    line = re.sub(r'^(Description|Features|Benefits):?\s*', '', line, flags=re.IGNORECASE)
                description_lines.append(line)
            
            description = ' '.join(description_lines)
            
            if module_name and description:
                url, image = get_module_info(module_name)
                modules.append({
                    'name': module_name,
                    'description': description,
                    'url': url,
                    'image': image
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
    """Get module recommendations using OpenAI API with enhanced context and improved response handling."""
    try:
        if not OPENAI_API_KEY:
            logger.error("OpenAI API key is not configured")
            return {"error": "OpenAI API key is not configured"}

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

        prompt = f'''As an experienced Odoo technical consultant, recommend 4 specific Odoo modules that best address the following business requirements. Focus on practical implementation and value delivery.

For each module provide:
1. Module Name (exact name as shown in Odoo Apps store)
2. Brief description including:
   - Core purpose and main functionality
   - Key benefits for the business
   - Integration capabilities
   - Ease of implementation considering the user's experience level

Business Context:
{context}

Guidelines:
- Recommend official Odoo modules when possible
- Consider the user's experience level when suggesting complex modules
- Focus on modules that integrate well with each other
- Prioritize stable, well-maintained modules
- Suggest modules that align with the preferred edition (Community/Enterprise)

Format each recommendation as:
Module: [Exact Module Name]
Description: [Core functionality and benefits]
Features: [Key features and integration points]
Benefits: [Business value and implementation considerations]'''

        logger.info("Making OpenAI API request with enhanced prompt")
        response = openai_client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,  # Reduced for more consistent responses
            max_tokens=1500   # Increased for more detailed responses
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

        # Prepare the response with module details
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
