import os
from functools import lru_cache
from openai import OpenAI
from typing import List, Optional

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
openai_client = OpenAI(api_key=OPENAI_API_KEY)

def format_features(features: Optional[List[str]]) -> str:
    if not features:
        return "No specific features selected"
    return ", ".join(features)

@lru_cache(maxsize=100)
def get_module_recommendations(
    requirements: str,
    industry: str = "",
    company_size: str = "",
    budget: str = "",
    features: Optional[List[str]] = None
) -> str:
    # Create a detailed context from the filters
    context = f"""Industry: {industry}
Company Size: {company_size}
Budget Level: {budget}
Required Features: {format_features(features) if features else 'No specific features selected'}
Additional Requirements: {requirements}"""

    prompt = f"""Based on the following business context, recommend 4 most suitable Odoo modules.
Consider the company's industry, size, budget constraints, and specific feature requirements.
For each recommended module, provide:
- Module name (without any ## or **)
- One line description of core purpose (without any formatting)

Business Context:
{context}

Please ensure the recommendations are:
1. Suitable for the specified industry
2. Appropriate for the company size
3. Within the indicated budget range
4. Address the required features
5. Compatible with each other"""
    
    try:
        if not OPENAI_API_KEY:
            return "Error: OpenAI API key is not configured"
            
        response = openai_client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=1000
        )
        
        if not response.choices[0].message.content:
            return "Error: No recommendations generated"
            
        return response.choices[0].message.content
    except Exception as e:
        return f"Error occurred during processing: {str(e)}"
