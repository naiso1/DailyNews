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
    # 日本 (2026-01-27)
    {
        "name": "jp_digital_mirror_0127",
        "prompt": "Automotive interior concept: digital inner mirror vision assist UI. Rearview mirror display showing 3-camera split view for blind spots, with safety overlays highlighting pedestrians or vehicles in rainy night conditions. Advanced safety feature for Japanese minivans. High-tech visibility assistance. Photorealistic 3D render, UI visualization, 8k quality."
    },
    {
        "name": "jp_smart_console_0127",
        "prompt": "Automotive interior concept: large center console organizer booster. Aftermarket module fitting into existing console, adding adjustable dividers, wireless charging pad, and LED lighting. Tidy and organized car interior. Practical accessory for family cars. Photorealistic 3D render, product visualization, 8k quality."
    },
    # 中国 (2026-01-27)
    {
        "name": "cn_waveguide_hud_0127",
        "prompt": "Automotive interior concept: waveguide HUD navigation UI. Large clear holographic display on windshield showing AR navigation arrows and ADAS warnings directly on the road view. Seamless integration of information and reality. Driver's perspective in a premium Chinese EV. Photorealistic 3D render, HUD technology visualization, 8k quality."
    },
    {
        "name": "cn_material_trace_0127",
        "prompt": "Automotive interior concept: interior material traceability display panel. Dashboard screen showing the origin, sustainability score, and supply chain info of the leather and fabric used in the cabin. Quality assurance visualization for premium Chinese market. Transparent luxury. Photorealistic 3D render, UI design visualization, 8k quality."
    },
    # インド (2026-01-27)
    {
        "name": "in_suv_upgrade_0127",
        "prompt": "Automotive interior concept: unified SUV tech package UI. Central touchscreen interface controlling ADAS settings, climate, and ambient lighting in one simple menu. Tech upgrade for Indian SUVs like Hyryder. User-friendly digital cockpit. Photorealistic 3D render, UI visualization, 8k quality."
    },
    {
        "name": "in_family_cabin_0127",
        "prompt": "Automotive interior concept: 3-row SUV rear seat comfort kit. Third-row seating area equipped with extra USB ports, reading lights, and cup holders. Enhanced comfort for large Indian families in cars like Scorpio N. Practical interior upgrade. Photorealistic 3D render, interior feature visualization, 8k quality."
    },
    # 米国 (2026-01-27)
    {
        "name": "us_screen_balance_0127",
        "prompt": "Automotive interior concept: balanced screen size proposal for American trucks. Interior featuring a medium-sized functional touchscreen flanked by large physical knobs and buttons for easy operation with gloves. Hybrid interface design prioritizing usability over screen size. Rugged American pick-up truck dashboard. Photorealistic 3D render, interior design visualization, 8k quality."
    },
    {
        "name": "us_biobased_trim_0127",
        "prompt": "Automotive interior concept: bio-based sustainable interior trim. Door panel and dashboard featuring textured plant-based materials and recycled fabrics. Natural aesthetic with premium feel. Eco-friendly American luxury car interior. Photorealistic 3D render, material texture visualization, 8k quality."
    },
    # 欧州 (2026-01-27)
    {
        "name": "eu_reliability_ui_0127",
        "prompt": "Automotive interior concept: vehicle health and reliability notification UI. Dashboard display alerting early signs of key battery low or system anomalies before failure. Peace of mind interface for European drivers. Proactive maintenance visualization. Photorealistic 3D render, UI design visualization, 8k quality."
    },
    {
        "name": "eu_lease_value_0127",
        "prompt": "Automotive interior concept: lease value protection interior care guide. Infotainment screen showing guide for maintaining seat leather and trim to preserve resale value. Smart maintenance reminders for leaseholders. Practical European car ownership feature. Photorealistic 3D render, UI visualization, 8k quality."
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
