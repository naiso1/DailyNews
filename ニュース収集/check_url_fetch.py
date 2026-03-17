"""
直近のニュースアイテムのURL取得可否を確認するスクリプト。
使い方: python check_url_fetch.py [--days 3] [--country cn]
"""
import argparse
import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
NEWS_PATH = ROOT / "news_data.js"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122 Safari/537.36"
}
TIMEOUT = 15


def extract_str_field(block: str, key: str) -> str:
    """Extract a double-quoted string field from a JS object literal block."""
    m = re.search(rf'\b{key}\s*:\s*"((?:[^"\\]|\\.)*)"', block)
    return m.group(1) if m else ""


def load_news_items(days: int, country: str | None) -> list[dict]:
    text = NEWS_PATH.read_text(encoding="utf-8")

    # Split into individual object blocks by finding each { ... } at top level of array
    m = re.search(r"window\.LOADED_NEWS_DATA\s*=\s*\[", text)
    if not m:
        sys.exit("LOADED_NEWS_DATA not found in news_data.js")
    pos = m.end()

    items = []
    while pos < len(text):
        # Find next {
        obj_start = text.find("{", pos)
        if obj_start == -1:
            break
        # Find matching }
        depth, in_str, esc = 0, False, False
        obj_end = obj_start
        for i, ch in enumerate(text[obj_start:], obj_start):
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    obj_end = i + 1
                    break
        block = text[obj_start:obj_end]
        # Stop if we've gone past the array (e.g. hit another window.* assignment)
        if "window." in block and len(block) > 5000:
            break
        item = {
            "id": extract_str_field(block, "id"),
            "date": extract_str_field(block, "date"),
            "country": extract_str_field(block, "country"),
            "url": extract_str_field(block, "url"),
        }
        if item["id"] and item["date"]:
            items.append(item)
        pos = obj_end

    # Filter by days
    dates = sorted({it["date"] for it in items if it["date"]}, reverse=True)
    target_dates = set(dates[:days])

    result = [
        it for it in items
        if it["date"] in target_dates
        and (not country or it["country"] == country)
    ]
    return result


def check_url(url: str) -> tuple[str, int]:
    """Returns (status, char_count)."""
    if not url or not url.startswith("http"):
        return "NO_URL", 0
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if resp.status_code != 200:
            return f"FAIL_HTTP_{resp.status_code}", 0
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        main = soup.find("article") or soup.find("main") or soup.body or soup
        body_text = " ".join(main.stripped_strings) if main else ""
        n = len(body_text)
        return ("OK" if n >= 100 else "SHORT"), n
    except Exception as e:
        return f"FAIL_NET({type(e).__name__})", 0


def main():
    ap = argparse.ArgumentParser(description="Check URL fetchability for recent news items")
    ap.add_argument("--days", type=int, default=3, help="最新N日分を対象 (default: 3)")
    ap.add_argument("--country", default=None, help="国コードでフィルタ (例: cn, jp, us)")
    args = ap.parse_args()

    items = load_news_items(args.days, args.country)
    if not items:
        print("対象アイテムなし")
        return

    label = f"直近{args.days}日分" + (f" / {args.country}" if args.country else "")
    print(f"対象: {len(items)}件 ({label})\n")
    print(f"{'ID':<10} {'DATE':<12} {'CTR':<4} {'STATUS':<22} {'CHARS':<6} URL")
    print("-" * 110)

    ok = fail = short = 0
    for it in items:
        status, chars = check_url(it["url"])
        chars_str = str(chars) if chars else "-"
        print(f"{it['id']:<10} {it['date']:<12} {it['country']:<4} {status:<22} {chars_str:<6} {it['url']}")
        if status == "OK":
            ok += 1
        elif status == "SHORT":
            short += 1
        else:
            fail += 1

    print("-" * 110)
    print(f"結果: OK={ok}  SHORT={short}  FAIL={fail}  合計={len(items)}")


if __name__ == "__main__":
    main()
