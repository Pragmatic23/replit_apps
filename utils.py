import os
from functools import lru_cache
from openai import OpenAI

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
openai_client = OpenAI(api_key=OPENAI_API_KEY)

@lru_cache(maxsize=100)
def get_module_recommendations(requirements: str) -> str:
    prompt = f"""Based on the customer's requirements, suggest relevant Odoo applications from the         Odoo Apps Store that best meet their needs. The recommendations should be clear, specific,         and include the name of the application,Suggest 4 most relevant Odoo modules for these             business requirements.
    For each module, provide:
    - Module name (1 line)
    - Brief, engaging description highlighting its core value (2-3 sentences)
    
    Keep descriptions concise and focus on business benefits.
    Requirements: {requirements}"""
    
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
