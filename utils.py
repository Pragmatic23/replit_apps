import json
from openai import OpenAI
import os

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
openai_client = OpenAI(api_key=OPENAI_API_KEY)

def get_module_recommendations(requirements: str) -> dict:
    prompt = f"""
    Given the following business requirements for an Odoo ERP system:
    {requirements}
    
    Please provide recommendations for Odoo modules that would best fulfill these requirements.
    Format your response as a JSON object with the following structure:
    {{
        "modules": [
            {{
                "name": "module_name",
                "description": "brief description",
                "key_features": ["feature1", "feature2"],
                "category": "module category"
            }}
        ],
        "summary": "brief summary of why these modules were chosen"
    }}
    """
    
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        return {
            "error": f"Failed to generate recommendations: {str(e)}",
            "modules": [],
            "summary": "Error occurred during processing"
        }
