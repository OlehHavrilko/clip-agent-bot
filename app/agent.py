import json
from google import genai
from typing import Dict, Any
from .config import GEMINI_API_KEY


# Create the client with API key
client = genai.Client(api_key=GEMINI_API_KEY)


def analyze_prompt(user_prompt: str) -> Dict[str, Any]:
    """
    Analyze user prompt with Gemini to extract scene information.
    
    Returns a dictionary with film details, search queries, and timestamps.
    Raises ValueError if analysis fails.
    """
    system_prompt = """You are a film expert. User describes a movie scene in any language.
Return ONLY a valid JSON object. No markdown, no explanation, no backticks.

{
  "film": "film title in English",
  "year": "release year",
  "scene_description": "short description in English",
  "search_queries": [
    "best youtube search query",
    "alternative query 1", 
    "alternative query 2"
  ],
  "timestamp_start": "HH:MM:SS",
  "timestamp_end": "HH:MM:SS",
  "confidence": "high/medium/low",
  "language_detected": "language of user input",
  "notes": "tips for finding this scene"
}

Rules:
- search_queries must be English, specific, include film title and scene keywords
- Add 30 second buffer on each side of timestamps
- If confidence is low, widen timestamp range by 2 minutes each side
- scene_description always in English regardless of input language"""

    try:
        # First attempt
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=f"{system_prompt}\n\nUser input: {user_prompt}"
        )
        
        # Try to parse JSON response
        result = parse_gemini_response(response.text)
        return result
        
    except Exception as e:
        # Second attempt with stricter instruction
        try:
            strict_prompt = f"""{system_prompt}

IMPORTANT: Return ONLY the JSON object. No explanations, no markdown, no backticks, no additional text.

User input: {user_prompt}"""
            
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=strict_prompt
            )
            result = parse_gemini_response(response.text)
            return result
            
        except Exception as e2:
            raise ValueError(f"Failed to analyze prompt: {str(e2)}")


def parse_gemini_response(response_text: str) -> Dict[str, Any]:
    """
    Parse Gemini response to extract JSON object.
    Handles various response formats that might include markdown or extra text.
    """
    import re
    
    # Try to find JSON object in the response
    json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
    if json_match:
        json_str = json_match.group(0)
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass
    
    # If direct JSON parsing fails, try to clean the response
    # Remove markdown code blocks if present
    cleaned = re.sub(r'```json\s*', '', response_text)
    cleaned = re.sub(r'\s*```', '', cleaned)
    
    try:
        return json.loads(cleaned.strip())
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON response from Gemini: {str(e)}")