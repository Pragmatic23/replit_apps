import os
from openai import OpenAI
from typing import List, Optional

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
openai_client = OpenAI(api_key=OPENAI_API_KEY)

def format_features(features: Optional[List[str]]) -> str:
    if not features:
        return "No specific features selected"
    return ", ".join(features)

def get_module_recommendations(
    requirements: str = "",
    industry: str = "",
    features: Optional[List[str]] = None
) -> str:
    try:
        # Create a detailed context from the filters
        context_parts = []
        if industry:
            context_parts.append(f"Industry: {industry}")
        context_parts.append(f"Required Features: {format_features(features)}")
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

Present each recommendation in a clear, structured format:
[Module Name]
[Concise description focused on business value]'''
    
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
        return f"Error: Unable to generate recommendations. Please try again later. Details: {str(e)}"
