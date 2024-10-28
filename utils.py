import os
from openai import OpenAI

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
openai_client = OpenAI(api_key=OPENAI_API_KEY)

def get_module_recommendations(requirements: str) -> dict:
    prompt = f"""Based on these requirements, suggest appropriate Odoo modules. For each module, provide:
    - Module name
    - Short description
    - Key features (as bullet points)
    - Category
    Format the response in a clear, structured way with section headers.
    Requirements: {requirements}"""
    
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}]
        )
        content = response.choices[0].message.content
        
        # Process the response into sections
        modules = []
        current_module = {}
        lines = content.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                if current_module:
                    modules.append(current_module)
                    current_module = {}
                continue
            
            if ':' in line:
                key, value = line.split(':', 1)
                key = key.strip().lower()
                value = value.strip()
                
                if 'module' in key.lower() or key.lower() == 'name':
                    if current_module:
                        modules.append(current_module)
                    current_module = {'name': value, 'features': []}
                elif 'description' in key.lower():
                    current_module['description'] = value
                elif 'category' in key.lower():
                    current_module['category'] = value
            elif line.startswith('-') or line.startswith('*'):
                if 'features' in current_module:
                    current_module['features'].append(line.lstrip('- *').strip())
        
        if current_module:
            modules.append(current_module)
            
        return {'modules': modules}
    except Exception as e:
        return {'error': f"Error occurred during processing: {str(e)}"}
