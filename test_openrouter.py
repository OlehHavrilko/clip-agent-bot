import httpx
from app.config import OPENROUTER_API_KEY

def test_openrouter_api():
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://clip-agent-bot.onrender.com"
    }
    body = {
        "model": "minimax/minimax-m2.5:free",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello, how are you?"}
        ],
        "temperature": 0.3,
        "max_tokens": 100
    }

    try:
        response = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            json=body,
            headers=headers
        )
        response.raise_for_status()
        print("OpenRouter API test successful!")
        print("Response:", response.json())
        return True
    except Exception as e:
        print("OpenRouter API test failed:", e)
        return False

if __name__ == "__main__":
    if OPENROUTER_API_KEY:
        test_openrouter_api()
    else:
        print("OPENROUTER_API_KEY not found in environment")