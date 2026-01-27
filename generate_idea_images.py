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
    # 日本 (2026-01-26)
    {
        "name": "jp_arene_update_0126",
        "prompt": "Automotive interior concept: vehicle OS update navigation UI for Arene OS. Dashboard display showing \"Arene OS Updated\" notification with a \"Try New Features\" button. Split screen demonstrating old vs. new functions clearly. Interactive visualization of software-defined vehicle evolution. Modern Japanese car interior with advanced digital cockpit. Photorealistic 3D render, UI/UX visualization, 8k quality."
    },
    {
        "name": "jp_color_trim_pack_0126",
        "prompt": "Automotive interior concept: special exterior color matched interior accent package. Japanese compact SUV interior showing dashboard trim and seat stitching perfectly matching the special edition exterior body color (e.g., metallic copper or deep blue). Coordinated aesthetic design. Aftermarket style quick installation accessory. Photorealistic 3D render, interior design visualization, 8k quality."
    },
    # 中国 (2026-01-26)
    {
        "name": "cn_ai_hud_0126",
        "prompt": "Automotive interior concept: AI-powered HUD as the primary screen for Chinese EVs. Augmented Reality Head-Up Display projected on the windshield, consolidating all essential driving information, ADAS warnings, and navigation. Minimalist instrument cluster with focus on the large immersive HUD. Driver's POV in a futuristic Chinese smart vehicle. Photorealistic 3D render, technology visualization, 8k quality."
    },
    {
        "name": "cn_modular_seat_0126",
        "prompt": "Automotive interior concept: intuitive rail-based switch UI for modular seats. Side of a premium car seat featuring a sleek linear touch rail control for adjusting seat position, heating, and massage intensity. Clean and logical interface design replacing multiple scattered buttons. Modern Chinese luxury interior detail. Photorealistic 3D render, product design visualization, 8k quality."
    },
    # インド (2026-01-26)
    {
        "name": "in_5g_telematics_0126",
        "prompt": "Automotive interior concept: 5G connected family safety UI for Indian market. Dashboard display showing \"Family Connect\" hub with integrated tracking for school pickup, in-car Wi-Fi hotspot management, and remote monitoring of vehicle interior. Peace of mind features for Indian families. Connected car interface. Photorealistic 3D render, UI visualization, 8k quality."
    },
    {
        "name": "in_custom_pack_0126",
        "prompt": "Automotive interior concept: aftermarket interior starter pack for Indian cars. DIY kit components laid out on a car seat: scratch-resistant door trim panels, custom accessory organizers, and stylish seat covers. \"My First Upgrade\" concept for personalizing a basic vehicle. Affordable modification visualization. Photorealistic 3D render, product package visualization, 8k quality."
    },
    # 米国 (2026-01-26)
    {
        "name": "us_physical_zone_0126",
        "prompt": "Automotive interior concept: tactile physical switch zone for essential controls in American SUVs. Center stack featuring high-quality machined metal toggle switches and knobs for climate, volume, and drive modes, distinct from the touchscreen. \"Digital Detox\" zone for critical functions. Rugged yet premium American interior design. Photorealistic 3D render, interior detail visualization, 8k quality."
    },
    {
        "name": "us_family_cabin_0126",
        "prompt": "Automotive interior concept: 3-row SUV family comfort pack for the US market. Interior view of the second and third rows featuring integrated ambient lighting, multiple USB-C ports, and smart storage pockets for tablets and snacks. \"Happy Travel\" atmosphere for family road trips. Spacious American SUV cabin. Photorealistic 3D render, lifestyle interior visualization, 8k quality."
    },
    # 欧州 (2026-01-26)
    {
        "name": "eu_cell_body_0126",
        "prompt": "Automotive interior concept: cell-to-body integrated acoustic interior. Cross-section view of a European EV door panel showing structural battery integration with advanced sound-deadening materials and thermal insulation built directly into the trim. High-tech quiet cabin engineering. Minimalist European design aesthetic. Photorealistic 3D render, technical feature visualization, 8k quality."
    },
    {
        "name": "eu_lightweight_box_0126",
        "prompt": "Automotive interior concept: lightweight expanded glovebox module for European cars. Dashboard open showing a spacious, reconfigurable glovebox storage system made of advanced lightweight sustainable materials. Smart dividers for organizing essentials. Efficient use of space in a compact European vehicle. Photorealistic 3D render, interior utility visualization, 8k quality."
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
