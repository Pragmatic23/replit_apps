import os
from functools import lru_cache
from openai import OpenAI

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
openai_client = OpenAI(api_key=OPENAI_API_KEY)

@lru_cache(maxsize=100)
def get_module_recommendations(requirements: str) -> str:
    prompt = f'''For these business requirements, recommend 4 Odoo modules.
Format each recommendation as:

Module Name
Brief one-line description that explains the core value.

Requirements: {requirements}'''
    
    try:
        if not OPENAI_API_KEY:
            return "Error: OpenAI API key is not configured"
            
        response = openai_client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=250
        )
        
        if not response.choices[0].message.content:
            return "Error: No recommendations generated"
            
        return response.choices[0].message.content
    except Exception as e:
        return f"Error occurred during processing: {str(e)}"
