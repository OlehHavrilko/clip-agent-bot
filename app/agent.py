import json
import httpx
from typing import Dict, Any
from .config import GROQ_API_KEY

# Verify GROQ_API_KEY is loaded
print(f"GROQ_API_KEY loaded: {'YES' if GROQ_API_KEY else 'NO'}", flush=True)


def analyze_prompt(user_prompt: str) -> Dict[str, Any]:
    """
    Analyze user prompt with Groq to extract scene information.
    
    Returns a dictionary with film details, search queries, and timestamps.
    Raises ValueError if analysis fails.
    """
    system_prompt = """You are a film expert. User describes a movie scene in any language.
Return ONLY a valid JSON object. No markdown, no backticks, no explanation, no additional text.
Start your response with { and end with }
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
    import re

    # Add detailed logging
    print("GROQ RAW RESPONSE:", response_text[:1000], flush=True)

    try:
        # Clean the raw response before parsing
        text = response_text.strip()
        text = re.sub(r'^```(?:json)?\n?', '', text)
        text = re.sub(r'\n?```$', '', text)
        text = text.strip()

        print("CLEANED TEXT:", text[:500], flush=True)

        data = json.loads(text)
        # Groq response format: {"choices": [{"message": {"content": "..."}}]}
        if "choices" in data and len(data["choices"]) > 0:
            content = data["choices"][0]["message"]["content"]

            # Clean markdown code blocks
            content = content.strip()
            content = re.sub(r'^(?:json)?\s*', '', content)
            content = re.sub(r'\s*$', '', content)
            content = content.strip()

            return json.loads(content)
        elif "error" in data:
            raise ValueError(f"Groq API error: {data['error']}")
        else:
            raise ValueError(f"Unexpected response format: {data}")
    except (json.JSONDecodeError, KeyError) as e:
        print(f"JSON PARSE ERROR: {e}", flush=True)
        print(f"RAW WAS: {response_text}", flush=True)
        raise ValueError(f"Failed to parse Groq response: {e}")


async def generate_tiktok_caption(scene_data: dict) -> str:
    """
    Generates a TikTok caption for a given scene using Groq API.
    """
    film = scene_data.get("film", "").strip()
    scene_description = scene_data.get("scene_description", "").strip()
    language_detected = scene_data.get("language_detected", "en").strip()

    system_prompt = """You are a TikTok content creator. Generate a caption for a TikTok video clip.
Return ONLY the caption text, no explanation.
Format:
[1-2 sentence hook about the scene's message]
[5-7 relevant hashtags]
Rules:
- Hook must be engaging, thought-provoking
- Language: match the user's language (Russian or English)
- Hashtags in English always
- Max 150 characters for the hook
- Example hashtags: #filmquotes #philosophy #mindset #cinema #motivation"""

    user_message = f"Film: {film}, Scene: {scene_description}"

    # Attempt to infer theme for better caption generation
    # This part can be expanded with more sophisticated theme extraction
    theme = ""
    if "control" in scene_description.lower():
        theme = ", Theme: stop controlling everything"
    elif "fight" in scene_description.lower():
        theme = ", Theme: inner struggle"

    user_message += theme

    try:
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        body = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            "temperature": 0.7, # Higher temperature for creativity
            "max_tokens": 200
        }

        response = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            json=body,
            headers=headers
        )
        response.raise_for_status()
        
        response_json = response.json()
        if "choices" in response_json and len(response_json["choices"]) > 0:
            caption = response_json["choices"][0]["message"]["content"].strip()
            return caption
        else:
            raise ValueError("No choices in Groq API response")

    except httpx.HTTPStatusError as e:
        print(f"Groq API HTTP error for caption generation: {e.response.status_code} - {e.response.text}", flush=True)
        return ""
    except httpx.RequestError as e:
        print(f"Groq API request error for caption generation: {e}", flush=True)
        return ""
    except Exception as e:
        print(f"Failed to generate TikTok caption: {e}", flush=True)
        return ""
