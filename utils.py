import os
from openai import OpenAI
from typing import List, Optional, Dict, Tuple
import requests
from bs4 import BeautifulSoup
import json

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
openai_client = OpenAI(api_key=OPENAI_API_KEY)

def format_features(features: Optional[List[str]]) -> str:
    if not features:
        return "No specific features selected"
    return ", ".join(features)

def get_module_info(module_name: str) -> Tuple[str, str]:
    """
    Get module URL and image URL from Odoo apps store
    Returns tuple of (module_url, image_url)
    """
    base_url = "https://apps.odoo.com"
    search_url = f"{base_url}/apps/search?search={module_name}"
    
    try:
        response = requests.get(search_url)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            first_result = soup.find('div', class_='o_app_item')
            if first_result:
                module_link = first_result.find('a')
                if module_link:
                    module_url = base_url + module_link['href']
                    img_tag = first_result.find('img')
                    image_url = img_tag['src'] if img_tag else ""
                    return module_url, image_url
    except Exception as e:
        print(f"Error fetching module info: {str(e)}")
    
    return "", ""

def get_module_recommendations(requirements: str = "",
                             industry: str = "",
                             features: Optional[List[str]] = None,
                             preferred_edition: str = "community",
                             has_experience: str = "no") -> Dict:
    try:
        # Create a detailed context from the filters
        context_parts = []
        if industry:
            context_parts.append(f"Industry: {industry}")
        if features:
            context_parts.append(f"Required Features: {format_features(features)}")
        
        # Add edition preference and experience level to context
        context_parts.append(f"Preferred Edition: {preferred_edition.title()}")
        context_parts.append(f"Previous Odoo Experience: {'Yes' if has_experience == 'yes' else 'No'}")
        
        if requirements:
            context_parts.append(f"Additional Requirements: {requirements}")

        context = "\n".join(context_parts)

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

        if not OPENAI_API_KEY:
            return {"error": "OpenAI API key is not configured"}

        response = openai_client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=1000
        )

        if not response.choices[0].message.content:
            return {"error": "No recommendations generated"}

        recommendations = response.choices[0].message.content
        modules = []
        urls = {}
        images = {}

        for module in recommendations.split('\n\n'):
            if module.strip():
                lines = module.strip().split('\n')
                if lines:
                    module_name = lines[0].strip().replace('*', '').replace('#', '').replace('-', '').strip()
                    url, image = get_module_info(module_name)
                    if url:
                        urls[module_name] = url
                        images[module_name] = image
                    modules.append({
                        'name': module_name,
                        'description': lines[1].strip() if len(lines) > 1 else '',
                        'url': url,
                        'image': image
                    })

        return {
            'text': recommendations,
            'modules': modules,
            'urls': urls,
            'images': images
        }

    except Exception as e:
        return {"error": f"Unable to generate recommendations. Please try again later. Details: {str(e)}"}
