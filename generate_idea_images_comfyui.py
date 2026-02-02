# -*- coding: utf-8 -*-
import argparse
import json
import os
import random
import re
import time
from pathlib import Path
import requests


ROOT = Path(__file__).resolve().parent
INSIGHTS_PATH = ROOT / "insights_data.js"
IMAGES_DIR = ROOT / "images"
IMAGES_DIR.mkdir(exist_ok=True)

COMFY_URL = os.getenv("COMFY_URL", "http://127.0.0.1:8188")


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
        "photorealistic 3D render, cinematic lighting, high detail, 4K quality."
    )


def update_image_path(js_text: str, idea_id: int, new_path: str) -> str:
    pattern = rf'(id:\s*{idea_id}\s*,\s*img:\s*")([^"]*)(")'
    return re.sub(pattern, rf'\1{new_path}\3', js_text, count=1)


def test_connection():
    try:
        resp = requests.get(f"{COMFY_URL}/system_stats", timeout=5)
        resp.raise_for_status()
        return True
    except Exception:
        return False


def queue_prompt(prompt_workflow):
    p = {"prompt": prompt_workflow}
    resp = requests.post(f"{COMFY_URL}/prompt", json=p, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_history(prompt_id):
    resp = requests.get(f"{COMFY_URL}/history/{prompt_id}", timeout=10)
    resp.raise_for_status()
    return resp.json()


def fetch_image(filename: str, subfolder: str = "", image_type: str = "output") -> bytes:
    params = {
        "filename": filename,
        "type": image_type,
    }
    if subfolder:
        params["subfolder"] = subfolder
    resp = requests.get(f"{COMFY_URL}/view", params=params, timeout=30)
    resp.raise_for_status()
    return resp.content


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workflow", required=True, help="ComfyUI workflow_api.json path")
    ap.add_argument("--date", default="latest", help="Target date (YYYY-MM-DD) or latest")
    ap.add_argument("--only-missing", action="store_true")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--sleep", type=float, default=1.0)
    ap.add_argument("--poll-interval", type=float, default=2.0)
    ap.add_argument("--max-wait", type=int, default=240, help="Max wait seconds per image")
    ap.add_argument("--ids", default="", help="Comma/range list like 201,202 or 201-210")
    ap.add_argument("--prompt-node", default="auto")
    ap.add_argument("--negative-node", default="")
    ap.add_argument("--sampler-node", default="3")
    ap.add_argument("--size-node", default="5")
    ap.add_argument("--seed-node", default="")
    ap.add_argument("--steps-node", default="")
    ap.add_argument("--cfg-node", default="")
    ap.add_argument("--width-node", default="")
    ap.add_argument("--height-node", default="")
    ap.add_argument("--steps", type=int, default=20)
    ap.add_argument("--cfg", type=float, default=1.0)
    ap.add_argument("--width", type=int, default=832)
    ap.add_argument("--height", type=int, default=544)
    ap.add_argument("--negative", default="")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not test_connection():
        print("[FAIL] Cannot connect to ComfyUI:", COMFY_URL)
        return

    workflow_path = Path(args.workflow)
    if not workflow_path.exists():
        print("Workflow not found:", workflow_path)
        return

    base_workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    base_prompt = base_workflow["prompt"] if "prompt" in base_workflow else base_workflow

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
        workflow = json.loads(json.dumps(base_prompt))

        prompt_node = args.prompt_node
        if prompt_node == "auto":
            # Prefer a direct text holder (PrimitiveStringMultiline), fallback to CLIPTextEncode
            for k, v in workflow.items():
                if isinstance(v, dict) and v.get("class_type") in ("PrimitiveStringMultiline", "PrimitiveString"):
                    prompt_node = k
                    break
            if prompt_node == "auto":
                for k, v in workflow.items():
                    if isinstance(v, dict) and v.get("class_type") == "CLIPTextEncode":
                        prompt_node = k
                        break

        if prompt_node in workflow:
            prompt_inputs = workflow[prompt_node].get("inputs", {})
            if "text" in prompt_inputs:
                prompt_inputs["text"] = prompt_text
            elif "value" in prompt_inputs:
                prompt_inputs["value"] = prompt_text
            else:
                print(f"[FAIL] prompt node {prompt_node} has no text/value")
        else:
            print(f"[FAIL] prompt node {prompt_node} not found")
            continue

        if args.negative_node and args.negative_node in workflow:
            neg_inputs = workflow[args.negative_node]["inputs"]
            if "text" in neg_inputs:
                neg_inputs["text"] = args.negative
            elif "value" in neg_inputs:
                neg_inputs["value"] = args.negative

        if args.sampler_node in workflow:
            workflow[args.sampler_node]["inputs"]["seed"] = random.randint(1, 9999999999)
            workflow[args.sampler_node]["inputs"]["steps"] = args.steps
            workflow[args.sampler_node]["inputs"]["cfg"] = args.cfg
        if args.seed_node in workflow:
            workflow[args.seed_node]["inputs"]["noise_seed"] = random.randint(1, 9999999999)
        if args.steps_node in workflow:
            workflow[args.steps_node]["inputs"]["steps"] = args.steps
        if args.cfg_node in workflow:
            workflow[args.cfg_node]["inputs"]["cfg"] = args.cfg

        if args.size_node in workflow:
            workflow[args.size_node]["inputs"]["width"] = args.width
            workflow[args.size_node]["inputs"]["height"] = args.height
        if args.width_node in workflow:
            workflow[args.width_node]["inputs"]["value"] = args.width
        if args.height_node in workflow:
            workflow[args.height_node]["inputs"]["value"] = args.height

        if args.dry_run:
            print(f"[DRY] {idea['id']} -> {dest_path.name}")
            count += 1
            continue

        try:
            resp = queue_prompt(workflow)
            prompt_id = resp["prompt_id"]
        except Exception as e:
            print(f"[FAIL] Queue error: {e}")
            continue

        history = {}
        max_polls = max(1, int(args.max_wait / args.poll_interval))
        for _ in range(max_polls):
            try:
                history = get_history(prompt_id)
                if prompt_id in history:
                    break
            except Exception:
                pass
            time.sleep(args.poll_interval)

        if prompt_id not in history:
            print(f"[FAIL] Timeout {idea['id']}")
            continue

        outputs = history[prompt_id].get("outputs", {})
        saved = False
        for node_id, node_output in outputs.items():
            for image in node_output.get("images", []):
                filename = image["filename"]
                subfolder = image.get("subfolder", "")
                img_bytes = fetch_image(filename, subfolder, "output")
                dest_path.write_bytes(img_bytes)
                updated = update_image_path(updated, idea["id"], f"images/{dest_path.name}")
                saved = True
                break
            if saved:
                break
        if saved:
            print(f"[OK] Saved {dest_path.name}")
            count += 1
        else:
            print(f"[WARN] No image output for {idea['id']}")
        time.sleep(args.sleep)

    if not args.dry_run:
        INSIGHTS_PATH.write_text(updated, encoding="utf-8")
    print("Done.")


if __name__ == "__main__":
    main()
