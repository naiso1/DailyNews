"""
Collect article images for manual review.

Reads `news_data.js`, filters articles dated 2025-12-18〜21,
fetches candidate image URLs from each article, and writes
`review_data.json` with current vs candidate images.

No in-place updates to `news_data.js` are performed.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

NEWS_PATH = Path("news_data.js")
OUT_PATH = Path("review_data.json")

# Exclude common non-content assets
EXCLUDE_PATTERNS = [
    r"/logo",
    r"/icon",
    r"avatar",
    r"sprite",
    r"blank",
    r"spacer",
    r"favicon",
    r"/common/",
    r"200200",
    r"_200x",
    r"_100x",
    r"40x40",
    r"50x50",
    r"100x100",
    r"opg_400_400",
]

ARTICLE_SELECTORS = [
    ".post_content img",
    ".article-content img",
    ".editor-image img",
    "article img",
    ".content img",
    "#content img",
    ".main img",
    "[class*='Article'] img",
    "[class*='article'] img",
    ".news-content img",
    ".paragraph img",
    ".text img",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def is_excluded(url: str) -> bool:
    return any(re.search(pat, url, re.I) for pat in EXCLUDE_PATTERNS)


def parse_news_data() -> List[Dict[str, str]]:
    """Parse news_data.js into a list of dicts with needed fields."""
    lines = NEWS_PATH.read_text(encoding="utf-8", errors="ignore").splitlines()
    entries = []
    current: Dict[str, str] = {}

    def maybe_flush():
        nonlocal current
        if current:
            entries.append(current)
            current = {}

    for raw in lines:
        line = raw.strip()
        if line.startswith("{"):
            current = {}
        for key in ["id", "title", "url", "source", "date", "img"]:
            if line.startswith(f"{key}:"):
                m = re.search(r'"([^"]+)"', line)
                if m:
                    current[key] = m.group(1)
        if line.startswith("},") or line == "}":
            maybe_flush()
    maybe_flush()
    return entries


def filter_by_date(entries: List[Dict[str, str]]) -> List[Dict[str, str]]:
    target_start = "2025-12-18"
    target_end = "2025-12-21"
    return [
        e
        for e in entries
        if "date" in e and target_start <= e["date"] <= target_end
    ]


def get_image_src(tag) -> str | None:
    for attr in ["data-original", "data-src", "data-lazy-src", "data-url", "src"]:
        src = tag.get(attr)
        if src and not src.startswith("data:") and len(src) > 10:
            return src
    return None


def extract_images(url: str, html: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    images = []

    def add(src: str | None):
        if not src or src.startswith("data:"):
            return
        full = urljoin(url, src.strip())
        if is_excluded(full):
            return
        if full not in images:
            images.append(full)

    # 1) og:image / twitter:image
    for meta_name in [
        ("property", "og:image"),
        ("name", "og:image"),
        ("name", "twitter:image"),
    ]:
        tag = soup.find("meta", attrs={meta_name[0]: meta_name[1]})
        if tag and tag.get("content"):
            add(tag["content"])

    # 2) Article-focused selectors
    for selector in ARTICLE_SELECTORS:
        try:
            for img in soup.select(selector):
                add(get_image_src(img))
        except Exception:
            continue

    # 3) Fallback: all images
    if len(images) < 12:
        for img in soup.find_all("img"):
            add(get_image_src(img))
            if len(images) >= 24:
                break

    return images


def fetch_candidates(url: str) -> Dict[str, object]:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        html = resp.text
        candidates = extract_images(url, html)
        return {"candidates": candidates[:20], "error": None}
    except Exception as e:
        return {"candidates": [], "error": str(e)}


def main():
    entries = parse_news_data()
    filtered = filter_by_date(entries)
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": str(NEWS_PATH),
        "articles": [],
    }

    for entry in filtered:
        data = {
            "id": entry.get("id"),
            "title": entry.get("title"),
            "source": entry.get("source"),
            "date": entry.get("date"),
            "url": entry.get("url"),
            "current_img": entry.get("img"),
        }
        fetched = fetch_candidates(entry.get("url", ""))
        data.update(fetched)
        result["articles"].append(data)
        print(f"[{data['id']}] found {len(data['candidates'])} candidates")

    OUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved {OUT_PATH} for {len(result['articles'])} articles.")


if __name__ == "__main__":
    main()
