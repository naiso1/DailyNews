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

# 2026-01-16〜2026-01-18のアイデア画像リスト
IDEAS = [
    # 日本
    {
        "name": "jp_console_care_0118",
        "prompt": "Automotive interior concept: LED console with display protection film bundle pack. Japanese kei car N-BOX style center console with integrated LED ambient lighting in warm orange glow. Protective film being applied to infotainment touchscreen display. Package contents visible: LED console unit and screen protector film. Clean Japanese minimalist product design. 30-minute DIY installation concept. Photorealistic 3D render, accessory product visualization, studio lighting, 8k quality."
    },
    {
        "name": "jp_shift_touch_0118",
        "prompt": "Automotive interior concept: tactile-focused shift operation module for Honda S+Shift system. Ergonomic shift lever unit with enhanced click feedback mechanism and premium leather-wrapped tactile surface. Close-up of driver's hand operating the precision shifter with satisfying mechanical feel. Brushed aluminum accents. Modern Japanese automotive design emphasizing tactile quality and driving precision. Photorealistic 3D render, high-end product visualization, 8k quality."
    },
    # 中国
    {
        "name": "cn_streamshare_0118",
        "prompt": "Automotive interior concept: sound zone cockpit with Harman StreamShare audio technology. Chinese family SUV interior with front and rear seat independent audio zones visualized by colored sound wave graphics in blue and purple. Parents in front seats with navigation audio, children in rear with headrest speakers enjoying entertainment. Premium speaker system visible. Modern Chinese smart cockpit design. Photorealistic 3D render, lifestyle visualization, 8k quality."
    },
    {
        "name": "cn_recyclable_trim_0118",
        "prompt": "Automotive interior concept: recyclable resin door trim panel with material passport QR code display. Chinese EV interior showing eco-friendly recyclable epoxy material with visible sustainable texture pattern. Small digital display or QR code showing material composition and recycling information. Green accent lighting emphasizing eco design. Modern Chinese automotive sustainability concept. Photorealistic 3D render, eco-product visualization, 8k quality."
    },
    # インド
    {
        "name": "in_affordable_ui_0118",
        "prompt": "Automotive interior concept: simplified 10-inch touchscreen UI template for affordable Indian SUV. Clean intuitive interface with minimal hierarchy, large colorful icons for navigation, music, phone, and climate controls on bright 10-inch display. Easy one-touch operation demonstration with finger touching screen. Dashboard of modern Indian SUV. Practical design balancing simplicity and functionality for mass market. Photorealistic 3D render, UI visualization, 8k quality."
    },
    {
        "name": "in_trim_upgrade_0118",
        "prompt": "Automotive interior concept: interior upgrade kit package for Kia grade models in India. Package display showing premium brown leather seat covers, LED ambient lighting strips in blue, and enhanced storage compartments. Before and after transformation of Indian SUV interior from basic grey to premium leather look. Affordable luxury upgrade concept. Photorealistic 3D render, product kit visualization, 8k quality."
    },
    # 米国
    {
        "name": "us_performance_controls_0118",
        "prompt": "Automotive interior concept: dedicated performance control panel for BMW iX3 M electric vehicle. Premium tactile button panel with illuminated drive mode selector showing Sport, Efficient, and Personal modes. Regenerative braking control dial and M sport settings buttons. Brushed aluminum and carbon fiber materials with red accent lighting. German performance EV cockpit design. Photorealistic 3D render, premium sports car visualization, 8k quality."
    },
    {
        "name": "us_mirror_film_0118",
        "prompt": "Automotive interior concept: hydrophobic mirror film with rain-detection interior alert system. Split view showing side mirror with water-repelling film and water droplets beading off, and interior dashboard displaying rain alert icon with ambient lighting changing to blue for visibility warning. Safety-focused connected car feature. Modern American automotive design emphasizing safety technology. Photorealistic 3D render, safety feature visualization, 8k quality."
    },
    # 欧州
    {
        "name": "eu_paintless_surface_0118",
        "prompt": "Automotive interior concept: paintless high-quality surface interior trim panels. European luxury car interior with premium matte finish door panels achieved without traditional painting process. Close-up detail of scratch-resistant surface with elegant brushed texture. Environmentally friendly manufacturing with long-lasting beauty. Soft ambient lighting. Modern German automotive quality design. Photorealistic 3D render, premium material visualization, 8k quality."
    },
    {
        "name": "eu_resale_trim_0118",
        "prompt": "Automotive interior concept: resale value protection interior trim for European lease vehicles. Easily replaceable surface trim panels with scratch-resistant coating being demonstrated. Quick swap mechanism showing worn panel removal and fresh panel installation. Value retention concept for lease and rental markets with euro currency symbols. Modern European practical automotive design. Photorealistic 3D render, functional product visualization, 8k quality."
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
