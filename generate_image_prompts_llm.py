# -*- coding: utf-8 -*-
import argparse
import os
import re
import json
import requests
from pathlib import Path


ROOT = Path(__file__).resolve().parent
INSIGHTS_PATH = ROOT / "insights_data.js"


def call_llm(endpoint: str, model: str, prompt: str) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.6,
        "max_tokens": 200,
    }
    resp = requests.post(endpoint, json=payload, timeout=120)
    if resp.status_code >= 400:
        raise RuntimeError(f"LLM error {resp.status_code}: {resp.text}")
    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


def parse_ids(ids_text: str):
    ids = set()
    for part in [p.strip() for p in ids_text.split(",") if p.strip()]:
        if "-" in part:
            a, b = part.split("-", 1)
            if a.isdigit() and b.isdigit():
                for i in range(int(a), int(b) + 1):
                    ids.add(i)
        elif part.isdigit():
            ids.add(int(part))
    return ids


def update_image_prompt(js_text: str, idea_id: int, prompt: str) -> str:
    # Replace existing imagePrompt
    pattern = rf"(id:\s*{idea_id}\s*,[\s\S]*?)(?:,\s*imagePrompt:\s*\"[^\"]*\")?(\s*\}})"
    def repl(m):
        head = m.group(1)
        tail = m.group(2)
        safe = prompt.replace("\\", "\\\\").replace("\"", "\\\"")
        if "imagePrompt:" in head:
            return m.group(0)
        return f"{head}, imagePrompt: \"{safe}\"{tail}"
    updated = re.sub(pattern, repl, js_text, count=1)
    # If there was existing imagePrompt, replace it explicitly
    if updated == js_text:
        rep = rf"(id:\s*{idea_id}\s*,[\s\S]*?imagePrompt:\s*\")([^\"]*)(\")"
        safe = prompt.replace("\\", "\\\\").replace("\"", "\\\"")
        updated = re.sub(rep, rf"\1{safe}\3", js_text, count=1)
    return updated


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", required=True, help="IDs list like 201-210 or 201,202")
    ap.add_argument("--endpoint", default=os.getenv("LLM_ENDPOINT", "http://127.0.0.1:1234/v1/chat/completions"))
    ap.add_argument("--model", default=os.getenv("LLM_MODEL", "qwen/qwen3-vl-8b"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    ids = parse_ids(args.ids)
    if not ids:
        print("No ids parsed.")
        return

    text = INSIGHTS_PATH.read_text(encoding="utf-8")
    updated = text

    for idea_id in sorted(ids):
        # extract title/desc
        m = re.search(
            rf"id:\s*{idea_id}\s*,\s*img:\s*\"[^\"]*\"\s*,\s*title:\s*\"([^\"]*)\"\s*,\s*desc:\s*\"([^\"]*)\"",
            text,
        )
        if not m:
            print(f"[SKIP] id {idea_id} not found")
            continue
        title = m.group(1)
        desc = m.group(2)
        prompt = (
            "Create a concise English image-generation prompt for an automotive interior concept. "
            "Must include: camera angle, focus area, materials, lighting, scene/vehicle type, and mood. "
            "No brand names, no logos, no text in image. Output only the prompt.\n\n"
            "Format guidance (single paragraph):\n"
            "- camera angle: (driver eye level / 3-4 front / close-up)\n"
            "- focus area: (dashboard / center console / seat / door trim)\n"
            "- materials: (leather / brushed aluminum / soft-touch plastic / fabric)\n"
            "- lighting: (warm ambient / daylight / studio)\n"
            "- scene: (premium sedan interior / compact SUV cabin / minivan)\n"
            "- mood: (calm / high-tech / cozy)\n\n"
            f"Title: {title}\nDescription: {desc}"
        )
        try:
            image_prompt = call_llm(args.endpoint, args.model, prompt)
        except Exception as e:
            print(f"[FAIL] id {idea_id}: {e}")
            continue
        updated = update_image_prompt(updated, idea_id, image_prompt)
        print(f"[OK] id {idea_id}")

    if not args.dry_run:
        INSIGHTS_PATH.write_text(updated, encoding="utf-8")
    print("Done.")


if __name__ == "__main__":
    main()
