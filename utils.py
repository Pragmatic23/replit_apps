import os
from functools import lru_cache
from openai import OpenAI

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
openai_client = OpenAI(api_key=OPENAI_API_KEY)

@lru_cache(maxsize=100)
def get_module_recommendations(requirements: str) -> str:
    prompt = f'''For these business requirements, recommend 4 Odoo modules.
For each module provide:
1. Module Name
2. Core Purpose (1-2 sentences about the main value proposition)
3. Key Features (3-4 bullet points of main functionalities)
4. Use Cases (2-3 examples of businesses that would benefit from this module)
5. Integration Benefits (How it works with other Odoo modules)

Requirements: {requirements}

Format each module's information in a clear, structured way using markdown.'''
    
    try:
        if not OPENAI_API_KEY:
            return "Error: OpenAI API key is not configured"
            
        response = openai_client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=1000  # Increased token limit for detailed responses
        )
        
        if not response.choices[0].message.content:
            return "Error: No recommendations generated"
            
        return response.choices[0].message.content
    except Exception as e:
        return f"Error occurred during processing: {str(e)}"
