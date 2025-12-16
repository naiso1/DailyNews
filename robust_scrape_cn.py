
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

# New Link for cn48 from search results
CN48_NEW_URL = "https://auto.online.sh.cn/content/2025-12/11/content_10465228.htm" # Wait, the user said this was broken.
# From search I got: [1] online.sh.cn
# Let's try to scrape the one from the search result if possible
# Search Source [1] was: https://auto.online.sh.cn/content/2024-05/24/content_10206680.htm (Maybe? Date 2024...)
# User wants 2025 news.
# Actually, the user's provided link was 404.
# I will use a generic Voyah product page as "Source" or find a working article.
# For now I will focus on scraping IMAGES for the others.

# Special scraper for Sohu (cn46) and Yiche (cn42)
TARGETS = {
    "cn42": "https://hao.yiche.com/wenzhang/105857715/",
    "cn46": "https://m.sohu.com/a/965056763_313745",
    "cn50": "https://www.ithome.com/0/904/692.htm"
}

def get_html(url):
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, context=ctx, timeout=15) as r:
            return r.read().decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"Failed to load {url}: {e}")
        return None

def find_best_image_url(html, base_url):
    # 1. OG Image
    og = re.search(r'<meta\s+(?:property|name)=["\']og:image["\']\s+content=["\']([^"\']+)["\']', html, re.IGNORECASE)
    if og: return og.group(1)
    
    # 2. First large image in bady
    # Filter for known CDN domains if possible or just size
    imgs = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE)
    
    valid_imgs = []
    for i in imgs:
        if i.startswith('//'): i = 'https:' + i
        if not i.startswith('http'): i = urllib.parse.urljoin(base_url, i)
        
        # Filter junk
        if any(x in i.lower() for x in ['icon', 'logo', 'avatar', 'gif', 'spacer', 'qr', 'ad']): continue
        
        valid_imgs.append(i)
        
    if valid_imgs:
        return valid_imgs[0] # Return first one
        
    return None

def download_and_save(url, pid):
    fname = f"{pid}.jpg"
    if '.png' in url.lower(): fname = f"{pid}.png"
    save_path = os.path.join(IMAGE_DIR, fname)
    
    print(f"Downloading {pid} from {url}")
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, context=ctx, timeout=15) as r:
            with open(save_path, 'wb') as f:
                f.write(r.read())
        return f"images/{fname}"
    except Exception as e:
        print(f"Download error: {e}")
        return None

def main():
    updates = {}
    
    for pid, url in TARGETS.items():
        print(f"Processing {pid}...")
        html = get_html(url)
        if html:
            img_url = find_best_image_url(html, url)
            if img_url:
                local_path = download_and_save(img_url, pid)
                if local_path:
                    updates[pid] = local_path
            else:
                print(f"No image found in {pid}")
        else:
            print(f"Could not load HTML for {pid}")

    # Manual override for cn48 if we didn't scrape it (link broken)
    # I'll download a placeholder Voyah image I know works for cn48
    voyah_url = "https://upload.wikimedia.org/wikipedia/commons/thumb/6/6d/Voyah_Zhuiguang_PHEV_004.jpg/800px-Voyah_Zhuiguang_PHEV_004.jpg"
    updates["cn48"] = download_and_save(voyah_url, "cn48")

    # Apply updates to JS
    if updates:
        js_path = r'c:\Users\demo\Desktop\中村\ホームページ作成\news_data.js'
        with open(js_path, 'r', encoding='utf-8') as f:
            content = f.read()

        for pid, img_path in updates.items():
            if not img_path: continue
            
            # Find the ID block
            # regex: id: "pid" ... img: "OLD_VALUE"
            # We want to replace OLD_VALUE with img_path
            
            pattern = re.compile(rf'(id:\s*"{pid}"[\s\S]*?img:\s*")[^"]*(")')
            content = pattern.sub(lambda m: m.group(1) + img_path + m.group(2), content)

        with open(js_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print("Updated news_data.js")

if __name__ == '__main__':
    main()
