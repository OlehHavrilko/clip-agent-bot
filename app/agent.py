import json
import httpx
from typing import Dict, Any
from .config import GROQ_API_KEY


def analyze_prompt(user_prompt: str) -> Dict[str, Any]:
    """
    Analyze user prompt with Groq to extract scene information.
    
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
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        body = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 1000
        }
        
        response = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            json=body,
            headers=headers
        )
        
        # Try to parse JSON response
        result = parse_groq_response(response.text)
        return result
        
    except Exception as e:
        # Second attempt with stricter instruction
        try:
            strict_prompt = f"""{system_prompt}

IMPORTANT: Return ONLY the JSON object. No explanations, no markdown, no backticks, no additional text.

User input: {user_prompt}"""
            
            body = {
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {"role": "system", "content": strict_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.3,
                "max_tokens": 1000
            }
            
            response = httpx.post(
                "https://api.groq.com/openai/v1/chat/completions",
                json=body,
                headers=headers
            )
            result = parse_groq_response(response.text)
            return result
            
        except Exception as e2:
            raise ValueError(f"Failed to analyze prompt: {str(e2)}")


def parse_groq_response(response_text: str) -> Dict[str, Any]:
    """
    Parse Groq response to extract JSON object.
    Handles various response formats that might include markdown or extra text.
    """
    import json
    
    try:
        data = json.loads(response_text)
        # Groq response format: {"choices": [{"message": {"content": "..."}}]}
        if "choices" in data and len(data["choices"]) > 0:
            content = data["choices"][0]["message"]["content"]
            return json.loads(content)
        elif "error" in data:
            raise ValueError(f"Groq API error: {data['error']}")
        else:
            raise ValueError(f"Unexpected response format: {data}")
    except (json.JSONDecodeError, KeyError) as e:
        raise ValueError(f"Invalid JSON response from Groq: {str(e)}")
    except (json.JSONDecodeError, KeyError) as e:
        raise ValueError(f"Invalid JSON response from Groq: {str(e)}")
