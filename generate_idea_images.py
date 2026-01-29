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
    # 日本 (2026-01-28)
    {
        "name": "jp_ambient_shadow_0128",
        "prompt": "Automotive interior concept: shadow ambient lighting with thermal insulation panel. Car door panel showing soft indirect lighting casting artistic shadows on textured insulation material. Nighttime scene in a Japanese camping car or minivan. Comfort and atmosphere integration. Photorealistic 3D render, interior lighting visualization, 8k quality."
    },
    {
        "name": "jp_vegan_seatcover_0128",
        "prompt": "Automotive interior concept: high-quality vegan leather seat cover kit. Custom-fit seat covers installed on a standard car seat, transforming it into a premium leather-like finish. Split view showing before and after installation. Sustainable and stylish upgrade for Japanese compact cars. Photorealistic 3D render, product visualization, 8k quality."
    },
    # 中国 (2026-01-28)
    {
        "name": "cn_aeb_lcv_ui_0128",
        "prompt": "Automotive interior concept: AEB guide UI for commercial vehicles. Dashboard of a Chinese light commercial van showing clear, simple graphics explaining Automatic Emergency Braking activation and warning zones. Safety feature education for professional drivers. Practical and high-visibility interface. Photorealistic 3D render, UI design visualization, 8k quality."
    },
    {
        "name": "cn_ev_infra_panel_0128",
        "prompt": "Automotive interior concept: EV charging infrastructure visualization panel. Large central screen displaying a density map of available charging stations and real-time vacancy status. Route planning interface minimizing charging anxiety. Modern Chinese EV smart cockpit. Photorealistic 3D render, infotainment UI visualization, 8k quality."
    },
    # インド (2026-01-28)
    {
        "name": "in_big_screen_pack_0128",
        "prompt": "Automotive interior concept: affordable big screen operational package for Indian SUVs. 10-inch touchscreen integrated combined with large, easy-to-use physical buttons and dials for climate and volume. Robust design for mass-market Indian SUVs. Durability and usability focus. Photorealistic 3D render, interior design visualization, 8k quality."
    },
    {
        "name": "in_smart_cockpit_ai_0128",
        "prompt": "Automotive interior concept: AI cockpit experience mode selector. Dashboard UI showing \"Experience Modes\" powered by NVIDIA AI, coordinating ADAS, climate, and audio settings for specific scenes like \"City Drive\" or \"Highway Relax\". Advanced technology perception for Indian market. Photorealistic 3D render, digital cockpit visualization, 8k quality."
    },
    # 米国 (2026-01-28)
    {
        "name": "us_button_return_0128",
        "prompt": "Automotive interior concept: dedicated physical button add-on kit. Aftermarket control panel fitting over a section of the touchscreen or console, adding tactile buttons for volume, AC, and shortcuts. \"Tactile Return\" concept for drivers who prefer physical feedback. High-quality metal and rubber finish. Photorealistic 3D render, accessory visualization, 8k quality."
    },
    {
        "name": "us_bio_leather_trim_0128",
        "prompt": "Automotive interior concept: bio-leather interior trim proposal. Close-up of car dashboard and door trim made from spider silk or mushroom-based leather. Natural texture and premium finish. Sustainable luxury material for American market. Photorealistic 3D render, material texture visualization, 8k quality."
    },
    # 欧州 (2026-01-28)
    {
        "name": "eu_robotaxi_ui_0128",
        "prompt": "Automotive interior concept: robotaxi passenger guidance UI. Interior screen in an autonomous shuttle showing clear welcome message, route progress, and emergency contact button. Reassuring and simple interface for first-time robotaxi users in Europe. Clean and friendly design. Photorealistic 3D render, UX design visualization, 8k quality."
    },
    {
        "name": "eu_sustainable_interior_0128",
        "prompt": "Automotive interior concept: sustainable material digital label. Interior trim piece with an embedded digital tag or QR code displaying the plant-based origin and recycling info of the material. \"Eco-Passport\" concept for European vehicles. Green driving value visualization. Photorealistic 3D render, detail visualization, 8k quality."
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

        dest_filename = f"{name}.png"
        dest_path = IMAGES_DIR / dest_filename
        
        if dest_path.exists():
            print(f" [SKIP] File exists: {dest_path}")
            success_count += 1
            continue

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
