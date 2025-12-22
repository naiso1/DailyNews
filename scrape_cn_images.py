import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import json
import re

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

# 中国ニュースのURL一覧（cn51〜cn60）
NEWS_URLS = [
    ("cn51", "https://www.ithome.com/0/906/318.htm"),
    ("cn52", "https://www.autohome.com.cn/news/202512/1311291.html"),
    ("cn53", "https://news.qq.com/rain/a/20251218A05LDO00"),
    ("cn54", "https://m.sohu.com/a/967825312_119627"),
    ("cn55", "https://news.mydrivers.com/1/1093/1093659.htm"),
    ("cn56", "https://www.donews.com/news/detail/4/6317482.html"),
    ("cn57", "https://finance.sina.com.cn/roll/2025-12-21/doc-inhcnpxc9640792.shtml"),
    ("cn58", "https://chejiahao.m.autohome.com.cn/info/24555689"),
    ("cn59", "https://www.sohu.com/a/967580645_126686"),
    ("cn60", "https://chejiahao.autohome.com.cn/info/24563922"),
]

# 除外パターン
EXCLUDE_PATTERNS = [
    r'/logo', r'/icon', r'avatar', r'sprite', r'blank', r'spacer',
    r't\.png$', r'opg_400_400', r'sohu_logo', r'favicon', r'/common/',
    r'200200', r'_200x', r'_100x', r'40x40', r'50x50', r'100x100',
]

def fetch_html(url: str) -> str:
    r = requests.get(url, headers=UA, timeout=30)
    r.raise_for_status()
    return r.text

def is_excluded(url: str) -> bool:
    for pattern in EXCLUDE_PATTERNS:
        if re.search(pattern, url, re.I):
            return True
    return False

def extract_best_image(url: str, html: str) -> str | None:
    """記事から最も適切な画像URLを抽出"""
    soup = BeautifulSoup(html, "html.parser")
    candidates = []
    
    # 1. og:image (サイズが大きいもの)
    tag = soup.find("meta", property="og:image") or soup.find("meta", attrs={"name": "og:image"})
    if tag and tag.get("content"):
        img_url = urljoin(url, tag["content"])
        if not is_excluded(img_url):
            candidates.append(("og", img_url))
    
    # 2. 記事本文内の画像
    selectors = [
        ".post_content img", ".article-content img", ".editor-image img",
        "article img", ".content img", "#content img", ".main img",
        "[class*='Article'] img", "[class*='article'] img", ".news-content img",
        ".paragraph img", ".text img",
    ]
    
    for selector in selectors:
        try:
            for img in soup.select(selector):
                src = img.get("data-original") or img.get("data-src") or img.get("src")
                if src and not src.startswith("data:") and len(src) > 30:
                    full_url = urljoin(url, src)
                    if not is_excluded(full_url):
                        candidates.append(("article", full_url))
        except:
            continue
    
    # 3. 全ての画像から良さそうなものを選択
    for img in soup.find_all("img"):
        src = img.get("data-original") or img.get("data-src") or img.get("src")
        if src and not src.startswith("data:") and len(src) > 30:
            full_url = urljoin(url, src)
            if not is_excluded(full_url):
                # 大きな画像を優先（URLにサイズ情報があるもの）
                if any(x in src for x in ["800", "600", "auto", "origin", "large", "big"]):
                    candidates.append(("large", full_url))
                else:
                    candidates.append(("other", full_url))
    
    # 優先順位でソート
    priority = {"og": 1, "article": 2, "large": 3, "other": 4}
    candidates.sort(key=lambda x: priority.get(x[0], 99))
    
    if candidates:
        return candidates[0][1]
    return None

def main():
    results = {}
    
    for news_id, url in NEWS_URLS:
        print(f"Processing {news_id}: {url}")
        try:
            html = fetch_html(url)
            img_url = extract_best_image(url, html)
            results[news_id] = img_url or "NOT_FOUND"
            print(f"  -> {img_url[:100] if img_url else 'NOT FOUND'}...")
        except Exception as e:
            print(f"  -> Error: {e}")
            results[news_id] = f"ERROR: {e}"
    
    print("\n=== Final Results (for news_data.js) ===")
    for news_id, img_url in results.items():
        print(f'        img: "{img_url}",  // {news_id}')

if __name__ == "__main__":
    main()
