# -*- coding: utf-8 -*-
import json, time, requests, shutil, random, os, sys
from pathlib import Path

# Fix Windows console encoding
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# --- Configuration ---
COMFY_URL = "http://127.0.0.1:8188"
BASE_DIR = Path(__file__).resolve().parent
WORKFLOW_PATH = Path(r"C:\Users\demo\Desktop\中村\溢れ出す企画アイデア画像\workflow_api.json")

# ComfyUI output directory
COMFY_OUTPUT_DIR = Path(r"C:\ComfyUI\ComfyUI_windows_portable_nvidia\ComfyUI_windows_portable\ComfyUI\output")

IMAGES_DIR = BASE_DIR / "images"
IMAGES_DIR.mkdir(exist_ok=True)

# 2026-01-19のアイデア画像リスト
IDEAS = [
    # 日本
    {
        "name": "jp_led_console_0119",
        "prompt": "Automotive interior concept: LED console nighttime comfort kit for Japanese kei cars and minivans. Integrated LED console unit combining wireless charging pad, small items tray, and ambient footwell lighting in warm orange glow. Tool-free 30-minute installation demonstration. Interior of Honda N-BOX or Nissan Roox with the premium accessory kit installed, illuminating the cabin softly at night. Japanese family car interior upgrade concept. Photorealistic 3D render, accessory product visualization, 8k quality."
    },
    {
        "name": "jp_retro_hmi_0119",
        "prompt": "Automotive interior concept: classic retro display UI pack for modern vehicles. Digital instrument cluster showing nostalgic vintage analog gauge design with classic fonts and needle indicators. Split screen comparison showing modern minimal UI on weekday mode and warm retro wood-grain styled UI on weekend mode. VW ID. Polo inspired HMI customization. Switchable mood enhancement through display themes. Photorealistic 3D render, UI design visualization, 8k quality."
    },
    # 中国
    {
        "name": "cn_battery_hud_0119",
        "prompt": "Automotive interior concept: seat-linked smart screen UX for Chinese EVs. Large curved touchscreen display that automatically adjusts angle and brightness based on driver posture and eye position detected by sensors. Synchronized climate control visualization. Premium Chinese smart cockpit with intelligent seat and screen coordination. Long-distance comfort optimization system. Photorealistic 3D render, smart cabin technology visualization, 8k quality."
    },
    {
        "name": "cn_three_row_cabin_0119",
        "prompt": "Automotive interior concept: integrated card-based operation cockpit for Chinese smart vehicles. Unified service layer UI showing navigation, voice control, climate, and seat functions controlled through swipeable card interface on large central display. Minimalist Chinese smart cabin design with software-updatable features. Streamlined operation reducing user confusion. Modern Chinese EV interior. Photorealistic 3D render, UI/UX visualization, 8k quality."
    },
    # インド
    {
        "name": "in_ac_efficiency_0119",
        "prompt": "Automotive interior concept: eco air conditioning dashboard for Indian EVs. Digital display showing AC power consumption, range impact visualization with green efficiency meter, and smart temperature recommendations based on outside temperature and traffic conditions. Dashboard of Indian electric vehicle with energy-efficient climate control interface. Mandatory AC fuel efficiency testing compliance concept. Photorealistic 3D render, eco-friendly UI visualization, 8k quality."
    },
    {
        "name": "in_smart_grade_0119",
        "prompt": "Automotive interior concept: mini HMI template for affordable Indian EVs and electric scooters. Compact 4-6 inch TFT display with clear three-section layout showing speed, battery level, and simple navigation. Highly readable design for first-time EV users with multi-language support. Affordable electric two-wheeler dashboard. Clean and intuitive interface for mass market India. Photorealistic 3D render, compact display UI visualization, 8k quality."
    },
    # 米国
    {
        "name": "us_piano_black_0119",
        "prompt": "Automotive interior concept: clean trim design solving piano black fingerprint problem. Premium dark interior trim panel with micro-texture surface that resists fingerprints. HMI notification showing cleaning reminder on central display. Comparison view of regular glossy black trim with visible fingerprints versus new anti-fingerprint textured surface. Luxury American car interior maintaining elegance while staying clean. Photorealistic 3D render, material innovation visualization, 8k quality."
    },
    {
        "name": "us_window_safety_0119",
        "prompt": "Automotive interior concept: conversational in-car task assistant using cross-domain integration. Driver speaking naturally to AI assistant displayed on HUD and central screen simultaneously. Voice command controlling route, climate, and seat settings in one conversation. Volvo EX60 inspired natural dialogue AI cockpit. Hands-free operation for enhanced driving safety and focus. Modern American premium EV interior. Photorealistic 3D render, voice AI visualization, 8k quality."
    },
    # 欧州
    {
        "name": "eu_ai_ambient_0119",
        "prompt": "Automotive interior concept: proactive comfort suggestion UI with AI agent technology. European luxury car interior with ambient lighting and seat adjusting automatically based on traffic and weather predictions. Transparent AI recommendation popup on display with easy accept/modify/reject options. Pre-emptive comfort optimization for stress-free driving. BMW or Audi style premium cabin with intelligent anticipation features. Photorealistic 3D render, AI assistant visualization, 8k quality."
    },
    {
        "name": "eu_polyester_trim_0119",
        "prompt": "Automotive interior concept: material passport feature for sustainable interior trim. European car door panel with recycled polyester fiber trim showing digital QR code or small display indicating recycled content percentage and repair history. Eco-friendly interior materials with traceability. Green accent lighting highlighting sustainability features. Premium European automotive sustainability design. Photorealistic 3D render, eco-material visualization, 8k quality."
    }
]

# FLUX settings
CFG = 1.0
STEPS = 20
WIDTH = 832
HEIGHT = 544
NEGATIVE_PROMPT = ""

def test_connection():
    try:
        resp = requests.get(f"{COMFY_URL}/system_stats", timeout=5)
        resp.raise_for_status()
        print("[OK] ComfyUI connected!")
        return True
    except requests.exceptions.ConnectionError:
        print("[FAIL] Cannot connect to ComfyUI")
        return False
    except Exception as e:
        print(f"[ERROR] Connection test: {e}")
        return False

def queue_prompt(prompt_workflow):
    p = {"prompt": prompt_workflow}
    data = json.dumps(p).encode('utf-8')
    resp = requests.post(f"{COMFY_URL}/prompt", data=data, timeout=30)
    resp.raise_for_status()
    return resp.json()

def get_history(prompt_id):
    resp = requests.get(f"{COMFY_URL}/history/{prompt_id}", timeout=10)
    resp.raise_for_status()
    return resp.json()

def main():
    print("=" * 60)
    print("Idea Image Generator (ComfyUI)")
    print("=" * 60)
    print(f"Total: {len(IDEAS)} images")
    print(f"Output: {IMAGES_DIR}")
    print()
    
    # Connection test
    print("Testing ComfyUI connection...")
    if not test_connection():
        print("\n[!] Cannot connect to ComfyUI.")
        print("1. Start ComfyUI")
        print("2. Make sure http://127.0.0.1:8188 is accessible")
        return

    print("\nLoading workflow...")
    try:
        with open(WORKFLOW_PATH, "r", encoding="utf-8") as f:
            workflow_api = json.load(f)
        print("[OK] Workflow loaded")
    except FileNotFoundError:
        print(f"[FAIL] workflow_api.json not found: {WORKFLOW_PATH}")
        return

    base_prompt = workflow_api["prompt"] if "prompt" in workflow_api else workflow_api

    success_count = 0
    failed_list = []

    for idx, idea in enumerate(IDEAS, 1):
        name = idea["name"]
        prompt_text = idea["prompt"]
        print(f"\n[{idx}/{len(IDEAS)}] {name}")
        print(f"Prompt: {prompt_text[:60]}...")

        # Deep copy
        current_workflow = json.loads(json.dumps(base_prompt))

        # Modify nodes
        if "6" in current_workflow:
            current_workflow["6"]["inputs"]["text"] = prompt_text
        else:
            print("[FAIL] Node 6 not found")
            failed_list.append(name)
            continue

        if "7" in current_workflow:
            current_workflow["7"]["inputs"]["text"] = NEGATIVE_PROMPT

        if "3" in current_workflow:
            current_workflow["3"]["inputs"]["seed"] = random.randint(1, 9999999999)
            current_workflow["3"]["inputs"]["steps"] = STEPS
            current_workflow["3"]["inputs"]["cfg"] = CFG
        
        if "5" in current_workflow:
            current_workflow["5"]["inputs"]["width"] = WIDTH
            current_workflow["5"]["inputs"]["height"] = HEIGHT

        # Queue
        try:
            resp = queue_prompt(current_workflow)
            prompt_id = resp['prompt_id']
            print(f"Queued: {prompt_id}")
        except Exception as e:
            print(f"[FAIL] Queue error: {e}")
            failed_list.append(name)
            continue

        # Wait for completion
        print("Generating", end="", flush=True)
        wait_count = 0
        history = {}
        while True:
            try:
                history = get_history(prompt_id)
                if prompt_id in history:
                    break
                print(".", end="", flush=True)
                time.sleep(2)
                wait_count += 1
                if wait_count > 90:  # 3 min timeout
                    print(" [TIMEOUT]")
                    break
            except Exception as e:
                print(f" [Poll error: {e}]")
                time.sleep(2)
        
        if prompt_id not in history:
            print(" [FAIL] Not in history")
            failed_list.append(name)
            continue
        
        print(" Done!")

        # Retrieve and copy image
        outputs = history[prompt_id].get('outputs', {})
        image_found = False
        for node_id in outputs:
            node_output = outputs[node_id]
            if 'images' in node_output:
                for image in node_output['images']:
                    filename = image['filename']
                    subfolder = image.get('subfolder', '')
                    
                    src_path = COMFY_OUTPUT_DIR
                    if subfolder:
                        src_path = src_path / subfolder
                    src_path = src_path / filename

                    dest_filename = f"{name}.png"
                    dest_path = IMAGES_DIR / dest_filename

                    print(f"  Source: {src_path}")
                    if src_path.exists():
                        try:
                            shutil.copy2(src_path, dest_path)
                            print(f"  [OK] Saved: {dest_path}")
                            image_found = True
                            success_count += 1
                        except Exception as e:
                            print(f"  [FAIL] Copy error: {e}")
                    else:
                        print(f"  [FAIL] Source not found")
        
        if not image_found:
            print("  [WARN] No image in outputs")
            failed_list.append(name)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Success: {success_count}/{len(IDEAS)}")
    if failed_list:
        print(f"Failed: {len(failed_list)}")
        for name in failed_list:
            print(f"  - {name}")
    print("\n--- Done ---")

if __name__ == "__main__":
    main()
