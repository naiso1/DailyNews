
import urllib.request
import os
import ssl
import shutil

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) width=device-width, initial-scale=1.0'
}

IMAGE_DIR = r"c:\Users\demo\Desktop\中村\ホームページ作成\images"

# 1. Definitive Image Sources for the requested items
FIX_TARGETS = {
    # cn42: Voyah Zhuiguang / Huawei Cockpit
    # Need a screen-heavy shot or exterior of Voyah
    "cn42": "https://upload.wikimedia.org/wikipedia/commons/thumb/6/6d/Voyah_Zhuiguang_PHEV_004.jpg/1200px-Voyah_Zhuiguang_PHEV_004.jpg",
    
    # cn43: MediaTek Dimensity Auto
    # Official marketing image
    "cn43": "https://www.mediatek.com/uploads/photos/products/dimensity-auto/dimensity-auto-cockpit-1.jpg",
    
    # cn46: Weekly New Car Roundup (Generic Collage or multiple cars)
    # Using a representative image of a chinese auto show or lineup
    "cn46": "https://upload.wikimedia.org/wikipedia/commons/thumb/2/25/Auto_China_2024_Day_1_114.jpg/1200px-Auto_China_2024_Day_1_114.jpg",
    
    # cn50: Auto Driving UX / ZOL Topic
    # Concept car interior or UX diagram
    "cn50": "https://images.unsplash.com/photo-1550029330-8dbccaade1d2?w=800"
}

def download_image(url, filename):
    print(f"Downloading {filename}...")
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, context=ctx, timeout=15) as r:
            with open(filename, 'wb') as f:
                f.write(r.read())
        return True
    except Exception as e:
        print(f"  DL Error: {e}")
        return False

def main():
    # 1. Download Images
    for pid, url in FIX_TARGETS.items():
        fname = f"{pid}.jpg"
        if '.png' in url.lower(): fname = f"{pid}.png"
        save_path = os.path.join(IMAGE_DIR, fname)
        
        if download_image(url, save_path):
            print(f"  Saved {fname}")

    # 2. Update cn48 Link and all image references in JS
    js_path = r'c:\Users\demo\Desktop\中村\ホームページ作成\news_data.js'
    with open(js_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Fix cn48 Link (to a reliable Sina or Autohome link found in search)
    # Found search result: https://www.voyah.com.cn/ (Official) or Sina: https://finance.sina.com.cn/stock/wbstock/2025-12-14/doc-inhauqtc2778705.shtml (Wait, that's cn45)
    # Let's use a generic reliable Voyah link since the specific Shanghai one is dead
    # Or specifically the one from the search: Sina has articles about it.
    # Replacement ID: cn48
    new_cn48_url = "https://www.voyah.com.cn/voyah-phev" # Official product page is safest fallback
    # Or finding a news article:
    
    # Search result [7] ifeng.com seems good: https://auto.ifeng.com/
    # Let's use the official site or a major portal.
    
    # Actually, I will search and replace the broken URL string specifically.
    old_cn48_url = "https://auto.online.sh.cn/content/2025-12/11/content_10465228.htm"
    if old_cn48_url in content:
        content = content.replace(old_cn48_url, "https://www.voyah.com.cn/") # Safe fallback
        print("Updated cn48 URL")

    # Update Images for correct extension/path
    for pid, url in FIX_TARGETS.items():
        fname = f"{pid}.jpg"
        if '.png' in url.lower(): fname = f"{pid}.png"
        local_path = f"images/{fname}"
        
        # Regex replace img for this ID
        import re
        # Find id: "pid" ... img: "..."
        # We need to match exactly the pid
        
        # Clean way:
        # 1. Find the chunk
        pattern = re.compile(rf'(id:\s*"{pid}"[\s\S]*?img:\s*")[^"]*(")')
        if pattern.search(content):
            content = pattern.sub(lambda m: m.group(1) + local_path + m.group(2), content)
            print(f"Updated JS image path for {pid}")

    with open(js_path, 'w', encoding='utf-8') as f:
        f.write(content)

if __name__ == '__main__':
    main()
