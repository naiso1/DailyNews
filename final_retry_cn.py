
import urllib.request
import re
import os
import ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    'User-Agent': 'Mozilla/5.0'
}

IMAGE_DIR = r"c:\Users\demo\Desktop\中村\ホームページ作成\images"

# 404 Fixes with different Unsplash IDs
REPLACEMENTS = {
    "cn43": "https://images.unsplash.com/photo-1451187580459-43490279c0fa?w=800&q=80",
    "cn49": "https://images.unsplash.com/photo-1492144534655-ae79c964c9d7?w=800&q=80",
    "cn50": "https://images.unsplash.com/photo-1517153295259-38eb8b4806a3?w=800&q=80"
}

def main():
    updates = {}
    for pid, url in REPLACEMENTS.items():
        fname = f"{pid}.jpg"
        save_path = os.path.join(IMAGE_DIR, fname)
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, context=ctx) as r:
                with open(save_path, 'wb') as f:
                    f.write(r.read())
            updates[pid] = f"images/{fname}"
            print(f"Downloaded {pid}")
        except Exception as e:
            print(f"Failed {pid}: {e}")

    js_path = r'c:\Users\demo\Desktop\中村\ホームページ作成\news_data.js'
    with open(js_path, 'r', encoding='utf-8') as f:
        content = f.read()

    for pid, local_path in updates.items():
        pattern = re.compile(rf'(id:\s*"{pid}"[\s\S]*?img:\s*")[^"]*(")')
        if pattern.search(content):
            content = pattern.sub(lambda m: m.group(1) + local_path + m.group(2), content)

    with open(js_path, 'w', encoding='utf-8') as f:
        f.write(content)

if __name__ == '__main__':
    main()
