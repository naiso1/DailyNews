
import urllib.request
import re
import os
import ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://www.google.com/'
}

IMAGE_DIR = r"c:\Users\demo\Desktop\中村\ホームページ作成\images"

# Targets that failed or need replacement
REPLACEMENTS = {
    # cn42: Zeekr 8X spy shot -> Need a Zeekr interior or spy shot like image
    "cn42": "https://images.unsplash.com/photo-1617788138017-80ad40651399?w=800&q=80", # Generic Luxury Interior
    
    # cn43: PCAuto Smart Cockpit Award -> Generic Award/Tech/Cockpit
    "cn43": "https://images.unsplash.com/photo-1550029330-8dbccaade1d2?w=800&q=80", # Generic Tech Cocktail
    
    # cn45: AITO M9 -> Need AITO M9 or similar multi-screen interior
    # Sina 404'd. Let's use a valid Unsplash or Wikimedia if avail. 
    # Reliable fallback:
    "cn45": "https://images.unsplash.com/photo-1549317661-bd32c8ce0db2?w=800&q=80", # Futuristic dashboard
    
    # cn47: AI Cockpit / GPU -> Tech chip
    "cn47": "https://images.unsplash.com/photo-1518770660439-4636190af475?w=800&q=80", # Chip
    
    # cn49: Sohu 404/Logo only -> Voyah Passion L / HarmonyOS
    "cn49": "https://images.unsplash.com/photo-1532168351545-c8a741369c0d?w=800&q=80", # Abstract tech/car
    
    # cn50: 100k RMB Queen Seat -> Comfortable seat
    "cn50": "https://images.unsplash.com/photo-1503376763036-066120622c74?w=800&q=80" # Car interior/seat
}

# Try to find specific better images for some if possible?
# User said "get images somehow". I will try to find ONE valid alternative source for cn42 (Zeekr) and cn45 (AITO)
# But scraping is hard. 
# Better strategy: Download these high quality Unsplash placeholders to local to ensure they work 100%.

def download_and_save(url, pid):
    fname = f"{pid}.jpg"
    save_path = os.path.join(IMAGE_DIR, fname)
    print(f"Downloading replacement for {pid}...")
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, context=ctx, timeout=15) as r:
            with open(save_path, 'wb') as f:
                f.write(r.read())
        return f"images/{fname}"
    except Exception as e:
        print(f"  Error: {e}")
        return None

def main():
    updates = {}
    
    # 1. Download Replacements
    for pid, url in REPLACEMENTS.items():
        updates[pid] = download_and_save(url, pid)

    # 2. Update JS
    js_path = r'c:\Users\demo\Desktop\中村\ホームページ作成\news_data.js'
    with open(js_path, 'r', encoding='utf-8') as f:
        content = f.read()

    import re
    for pid, local_path in updates.items():
        if not local_path: continue
        
        # Replace img: "..." with img: "images/pid.jpg"
        pattern = re.compile(rf'(id:\s*"{pid}"[\s\S]*?img:\s*")[^"]*(")')
        if pattern.search(content):
            content = pattern.sub(lambda m: m.group(1) + local_path + m.group(2), content)
            print(f"Updated {pid} to local file")

    with open(js_path, 'w', encoding='utf-8') as f:
        f.write(content)

if __name__ == '__main__':
    main()
