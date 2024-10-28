import os
from openai import OpenAI

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
openai_client = OpenAI(api_key=OPENAI_API_KEY)

def get_module_recommendations(requirements: str) -> str:
    prompt = f"""Based on these business requirements, suggest appropriate Odoo modules. 
    For each module suggestion, provide:
    - Module name
    - A brief description of its purpose and main functionality
    
    Requirements: {requirements}"""
    
    try:
        if not OPENAI_API_KEY:
            return "Error: OpenAI API key is not configured"
            
        response = openai_client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error occurred during processing: {str(e)}"
