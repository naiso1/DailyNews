import argparse
import base64
import os
import re
import time
from pathlib import Path
from urllib.parse import urlparse
import json
import requests


ROOT = Path(__file__).resolve().parent
INSIGHTS_PATH = ROOT / "insights_data.js"
IMAGES_DIR = ROOT / "images"
DEFAULT_KEY_FILE = ROOT / "画像生成APIテスト" / "OpenRouter_API.md"
DEFAULT_MODEL = "google/gemini-3-pro-image-preview"


def load_api_key(key_file: Path | None = None) -> str:
    env_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if env_key:
        return env_key
    key_path = key_file or DEFAULT_KEY_FILE
    if key_path and key_path.exists():
        return key_path.read_text(encoding="utf-8").strip()
    return ""


def extract_latest_block(text: str) -> str:
    start = text.find("window.DAILY_INSIGHTS")
    if start == -1:
        return ""
    start = text.find("{", start)
    if start == -1:
        return ""
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
    return ""


def extract_ideas(block: str):
    ideas = []
    pattern = re.compile(
        r"\{\s*id:\s*(\d+)\s*,\s*img:\s*\"([^\"]*)\"\s*,\s*title:\s*\"([^\"]*)\"\s*,\s*desc:\s*\"([^\"]*)\"\s*\}",
        re.DOTALL,
    )
    for m in pattern.finditer(block):
        idea_id = int(m.group(1))
        img = m.group(2)
        title = m.group(3)
        desc = m.group(4)
        ideas.append({"id": idea_id, "img": img, "title": title, "desc": desc})
    return ideas


def extract_date(block: str) -> str:
    m = re.search(r'date:\s*"([^"]+)"', block)
    return m.group(1) if m else ""


def build_prompt(title: str, desc: str) -> str:
    return (
        f"{title}. {desc}\n"
        "Automotive interior design concept, premium materials, "
        "photorealistic 3D render, cinematic lighting, high detail, 4K quality."
    )


def save_data_url(data_url: str, out_path: Path) -> bool:
    if not data_url.startswith("data:image"):
        return False
    header, b64 = data_url.split(",", 1)
    out_path.write_bytes(base64.b64decode(b64))
    return True


def request_image(api_key: str, model: str, prompt: str, timeout: int = 180, retries: int = 4, base_delay: float = 1.2) -> str:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "modalities": ["image", "text"],
        "max_tokens": 512,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://local",
        "X-Title": "DailyNews Image Generator",
    }
    for attempt in range(retries + 1):
        resp = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            data=json.dumps(payload),
            timeout=timeout,
        )
        if resp.status_code == 429 or "rate limit" in resp.text.lower():
            delay = base_delay * (2 ** attempt)
            time.sleep(delay)
            continue
        if resp.status_code >= 400:
            resp.raise_for_status()
        result = resp.json()
        if result.get("choices"):
            message = result["choices"][0].get("message", {})
            images = message.get("images", [])
            if images:
                return images[0]["image_url"]["url"]
            content = message.get("content", "")
            if isinstance(content, str) and content.startswith("data:image"):
                return content
        return ""
    return ""


def update_image_path(js_text: str, idea_id: int, new_path: str) -> str:
    pattern = rf'(id:\s*{idea_id}\s*,\s*img:\s*")([^"]*)(")'
    return re.sub(pattern, rf'\1{new_path}\3', js_text, count=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="latest", help="Target date (YYYY-MM-DD) or latest")
    ap.add_argument("--limit", type=int, default=0, help="Limit number of images (0=all)")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--only-missing", action="store_true")
    ap.add_argument("--model", default=os.getenv("OPENROUTER_MODEL", DEFAULT_MODEL))
    ap.add_argument("--key-file", default="")
    ap.add_argument("--sleep", type=float, default=1.2)
    ap.add_argument("--retries", type=int, default=4)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    api_key = load_api_key(Path(args.key_file) if args.key_file else None)
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY が未設定です。環境変数または OpenRouter_API.md に設定してください。")

    text = INSIGHTS_PATH.read_text(encoding="utf-8")
    block = extract_latest_block(text)
    if not block:
        print("No insights block found.")
        return
    date = extract_date(block)
    if args.date != "latest" and args.date and date != args.date:
        print(f"Latest date is {date}, not target {args.date}.")
    ideas = extract_ideas(block)
    if not ideas:
        print("No ideas found in latest block.")
        return

    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    updated = text
    count = 0
    for idea in ideas:
        if args.limit and count >= args.limit:
            break
        current = idea["img"] or ""
        if args.only_missing and current and current != "images/idea_dummy.svg":
            continue
        out_path = IMAGES_DIR / f"idea_{idea['id']}.png"
        if out_path.exists() and not args.overwrite:
            updated = update_image_path(updated, idea["id"], f"images/{out_path.name}")
            continue
        prompt = build_prompt(idea["title"], idea["desc"])
        if args.dry_run:
            print(f"[DRY] {idea['id']} -> {out_path.name}")
            count += 1
            continue
        try:
            data_url = request_image(api_key, args.model, prompt, retries=args.retries, base_delay=max(1.0, args.sleep))
            if data_url:
                saved = save_data_url(data_url, out_path)
                if saved:
                    updated = update_image_path(updated, idea["id"], f"images/{out_path.name}")
                    print(f"Saved image: {out_path.name}")
                    count += 1
            time.sleep(args.sleep)
        except Exception as e:
            print(f"Failed {idea['id']}: {e}")

    if not args.dry_run:
        INSIGHTS_PATH.write_text(updated, encoding="utf-8")
    print("Done.")


if __name__ == "__main__":
    main()
