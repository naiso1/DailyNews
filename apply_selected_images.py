"""
Apply selected image URLs to news_data.js based on provided mapping.

Only updates entries with non-empty selected URLs. Leaves others untouched.
"""

from __future__ import annotations

import re
from pathlib import Path

NEWS_PATH = Path("news_data.js")

# Mapping from article id -> selected image URL (empty string = no change)
SELECTED = {
    "jp80": "https://img.bestcarweb.jp/wp-content/uploads/2025/12/17190359/1218-Serena-MC-5-150x150.jpg?v=1765965841",
    "jp81": "",
    "jp82": "https://motorcars.jp/wp-content/uploads/2025/12/nissan-upgrades-some-specifications-of-the-nv200-vanette-myroom20251219-2-1024x569.jpg",
    "jp83": "https://www.caranddriver.co.jp/wp-content/uploads/2025/12/e7b7a6ecbe9da4419257e2346f2ce5e9.jpg",
    "jp84": "https://webcg.ismcdn.jp/mwimgs/7/e/200/img_7e7e00b382e2964c774d35487455a0b3123999.jpg",
    "jp85": "",
    "jp87": "",
    "jp88": "https://kuruma-news.jp/wp-content/uploads/2026/11/20251110_suzuki_karry_003-650x433.jpg?v=1762743250",
    "cn51": "",
    "cn52": "http://www2.autoimg.cn/chejiahaodfs/g34/M08/19/C0/620x0_1_autohomecar__ChxpWGlFE4OAeBhVAAT6R1Nb9RQ506.jpg",
    "cn53": "",
    "cn54": "https://q9.itc.cn/q_70/images03/20251221/aa36e7165e6740ed9e714d7de0e34770.jpeg",
    "cn55": "https://img1.mydrivers.com/img/20251220/2ee53e6d-a70b-4be0-8e8f-3d4f2463d472.jpg",
    "cn56": "https://img6.donews.com/static/v3/images/full-logo.png",
    "cn57": "https://n.sinaimg.cn/spider20251221/102/w818h884/20251221/b03b-ef80ba98366c309579eabff5d4c1b642.jpg",
    "cn58": "",
    "cn59": "",
    "cn60": "https://www2.autoimg.cn/chejiahaodfs/g33/M06/2E/77/750x0_autohomecar__Chto52lGrPSAD8fmAAQ8boNKK-I152.jpg",
    "in71": "",
    "in72": "",
    "in73": "",
    "in74": "",
    "in75": "https://imgd.aeplcdn.com/642x336/n/cw/ec/214893/sierra-exterior-front-view.jpeg?isig=0&art=1&q=80",
    "in76": "",
    "in77": "",
    "in78": "https://imgd.aeplcdn.com/642x361/n/cw/ec/214233/hector-facelift-interior-dashboard-2.jpeg?isig=0&wm=1&q=75",
    "in79": "",
}


def replace_images(js_text: str) -> str:
    """Replace img values for ids present in SELECTED with non-empty URL."""
    for aid, url in SELECTED.items():
        if not url:
            continue
        pattern = re.compile(rf'(id:\s*"{re.escape(aid)}"[\s\S]*?img:\s*")[^"]*(")', re.MULTILINE)
        js_text, n = pattern.subn(rf'\1{url}\2', js_text, count=1)
        if n == 0:
            print(f"[WARN] id {aid} not found; no replacement")
        else:
            print(f"[OK] updated {aid}")
    return js_text


def main():
    original = NEWS_PATH.read_text(encoding="utf-8", errors="ignore")
    updated = replace_images(original)
    NEWS_PATH.write_text(updated, encoding="utf-8")
    print("Done.")


if __name__ == "__main__":
    main()
