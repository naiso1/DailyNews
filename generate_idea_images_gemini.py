# -*- coding: utf-8 -*-
import argparse
import base64
import os
import re
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
INSIGHTS_PATH = ROOT / "insights_data.js"
IMAGES_DIR = ROOT / "images"
IMAGES_DIR.mkdir(exist_ok=True)

DEFAULT_MODEL = "gemini-3.1-flash-image-preview"
DEFAULT_ASPECT_RATIO = "1:1"
DEFAULT_IMAGE_SIZE = "512px"  # 0.5K tier
DEFAULT_API_VERSION = "v1beta"


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
                    return text[start : i + 1]
    return ""


def extract_ideas(block: str):
    ideas = []
    pattern = re.compile(
        r"\{\s*id:\s*(\d+)\s*,\s*img:\s*\"([^\"]*)\"\s*,\s*title:\s*\"([^\"]*)\"\s*,\s*desc:\s*\"([^\"]*)\"(?:\s*,\s*imagePrompt:\s*\"([^\"]*)\")?\s*\}",
        re.DOTALL,
    )
    for m in pattern.finditer(block):
        ideas.append(
            {
                "id": int(m.group(1)),
                "img": m.group(2),
                "title": m.group(3),
                "desc": m.group(4),
                "imagePrompt": m.group(5) or "",
            }
        )
    return ideas


def extract_date(block: str) -> str:
    m = re.search(r'date:\s*"([^"]+)"', block)
    return m.group(1) if m else ""


def build_prompt(title: str, desc: str, image_prompt: str = "") -> str:
    if image_prompt:
        return image_prompt
    return (
        f"{title}. {desc}\n"
        "Automotive interior design concept, premium materials, "
        "photorealistic 3D render, cinematic lighting, high detail."
    )


def update_image_path(js_text: str, idea_id: int, new_path: str) -> str:
    pattern = rf'(id:\s*{idea_id}\s*,\s*img:\s*")([^"]*)(")'
    return re.sub(pattern, rf"\1{new_path}\3", js_text, count=1)


def parse_first_image_bytes(resp_json: dict) -> bytes | None:
    for cand in resp_json.get("candidates", []) or []:
        content = cand.get("content", {}) or {}
        for part in content.get("parts", []) or []:
            inline = part.get("inlineData") or part.get("inline_data")
            if not inline:
                continue
            data = inline.get("data")
            if data:
                return base64.b64decode(data)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="latest", help="Target date (YYYY-MM-DD) or latest")
    ap.add_argument("--only-missing", action="store_true")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--ids", default="", help="Comma/range list like 201,202 or 201-210")
    ap.add_argument("--model", default=os.environ.get("GEMINI_IMAGE_MODEL", DEFAULT_MODEL))
    ap.add_argument("--aspect-ratio", default=os.environ.get("GEMINI_IMAGE_ASPECT_RATIO", DEFAULT_ASPECT_RATIO))
    ap.add_argument("--image-size", default=os.environ.get("GEMINI_IMAGE_SIZE", DEFAULT_IMAGE_SIZE))
    ap.add_argument("--api-version", default=os.environ.get("GEMINI_API_VERSION", DEFAULT_API_VERSION))
    args = ap.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[FAIL] GEMINI_API_KEY not set")
        return

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

    updated = text
    count = 0
    id_filter = set()
    if args.ids:
        parts = [p.strip() for p in args.ids.split(",") if p.strip()]
        for p in parts:
            if "-" in p:
                a, b = p.split("-", 1)
                if a.isdigit() and b.isdigit():
                    for i in range(int(a), int(b) + 1):
                        id_filter.add(i)
            elif p.isdigit():
                id_filter.add(int(p))

    url = f"https://generativelanguage.googleapis.com/{args.api_version}/models/{args.model}:generateContent"
    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}

    for idea in ideas:
        if id_filter and idea["id"] not in id_filter:
            continue
        if args.limit and count >= args.limit:
            break
        current = idea["img"] or ""
        if args.only_missing and current and current != "images/idea_dummy.svg":
            continue
        dest_path = IMAGES_DIR / f"idea_{idea['id']}.png"
        if dest_path.exists() and not args.overwrite:
            updated = update_image_path(updated, idea["id"], f"images/{dest_path.name}")
            continue

        prompt_text = build_prompt(idea["title"], idea["desc"], idea.get("imagePrompt", ""))
        payload = {
            "contents": [{"parts": [{"text": prompt_text}]}],
            "generationConfig": {
                "responseModalities": ["IMAGE"],
                "imageConfig": {
                    "aspectRatio": args.aspect_ratio,
                    "imageSize": args.image_size,
                },
            },
        }
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=300)
            if resp.status_code >= 400:
                print(f"[FAIL] {idea['id']}: {resp.status_code} {resp.text[:400]}")
                continue
            image_bytes = parse_first_image_bytes(resp.json())
            if not image_bytes:
                print(f"[FAIL] {idea['id']}: no image payload")
                continue
            dest_path.write_bytes(image_bytes)
            updated = update_image_path(updated, idea["id"], f"images/{dest_path.name}")
            print(f"[OK] Saved {dest_path.name}")
            count += 1
        except Exception as e:
            print(f"[FAIL] {idea['id']}: {e}")

    INSIGHTS_PATH.write_text(updated, encoding="utf-8")
    print("Done.")


if __name__ == "__main__":
    main()
