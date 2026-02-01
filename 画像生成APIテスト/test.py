import os
import json
import base64
import re
from pathlib import Path
import requests


def load_api_key():
    env_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if env_key:
        return env_key
    key_path = Path(__file__).with_name("OpenRouter_API.md")
    if key_path.exists():
        return key_path.read_text(encoding="utf-8").strip()
    return ""


OPENROUTER_API_KEY = load_api_key()
if not OPENROUTER_API_KEY:
    raise RuntimeError("OPENROUTER_API_KEY が未設定です。環境変数または OpenRouter_API.md に設定してください。")

response = requests.post(
    url="https://openrouter.ai/api/v1/chat/completions",
    headers={
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://your-app.com",
        "X-Title": "My Image Generator",
    },
    data=json.dumps({
        "model": "google/gemini-2-5-flash-image-preview:free",
        "messages": [
            {
                "role": "user",
                "content": "Generate a beautiful sunset over mountains"
            }
        ],
        "modalities": ["image", "text"],
        "max_tokens": 512
    }),
    timeout=120
)

print("status:", response.status_code)
if response.status_code != 200:
    print(response.text)
    raise SystemExit(1)

result = response.json()


def save_data_url_image(data_url: str, out_dir: Path = Path(".")) -> str:
    if not data_url.startswith("data:image"):
        return ""
    header, b64 = data_url.split(",", 1)
    match = re.search(r"data:image/([^;]+);base64", header)
    ext = match.group(1) if match else "png"
    filename = out_dir / f"generated_image.{ext}"
    filename.write_bytes(base64.b64decode(b64))
    return str(filename)


# The generated image will be in the assistant message
if result.get("choices"):
    message = result["choices"][0].get("message", {})
    if message.get("images"):
        for image in message["images"]:
            image_url = image["image_url"]["url"]  # Base64 data URL
            saved = save_data_url_image(image_url)
            if saved:
                print("Saved image:", saved)
            else:
                print(f"Generated image: {image_url[:80]}...")
    else:
        print("No images returned. Message content:", message.get("content"))
else:
    print("No choices in response:", result)
