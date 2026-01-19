import requests

COMFY_URL = "http://127.0.0.1:8188"

print("ComfyUI connection test...")
try:
    resp = requests.get(f"{COMFY_URL}/system_stats", timeout=5)
    resp.raise_for_status()
    print("[OK] ComfyUI connected!")
    data = resp.json()
    print(f"System: {data.get('system', {})}")
except requests.exceptions.ConnectionError:
    print("[FAIL] Cannot connect to ComfyUI")
    print("Please make sure ComfyUI is running")
except Exception as e:
    print(f"[ERROR] {e}")
