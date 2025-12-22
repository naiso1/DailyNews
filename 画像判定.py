import base64, io, json, re
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
from PIL import Image
from tqdm import tqdm

# LM Studio (OpenAI互換)
from openai import OpenAI
client = OpenAI(base_url="http://127.0.0.1:1234/v1", api_key="lm-studio")  # keyはダミーでOK

MODEL = "qwen/qwen3-vl-8b"  # LM Studioで表示されるモデルIDに合わせて変更

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

# 画像抽出時のフィルタリング設定
MIN_IMAGE_SIZE = 200  # 最小サイズ（px）- アイコン除外用

# 記事セレクタ（優先順位順）- 各サイトに対応
ARTICLE_SELECTORS = [
    # Panasonic News
    ".p-hero img",
    ".BlockModule img",
    ".DownLoad img",
    # Autohome (中国)
    ".editor-image img",
    "article img",
    "[class*='Article'] img",  # 動的クラス名対応
    "[class*='article'] img",
    # 汎用
    ".article-body img",
    ".article-content img",
    ".news-content img",
    ".main-content img",
    ".post-content img",
    ".entry-content img",
    ".content img",
    "#content img",
]

# 遅延読み込み属性（優先順位順）
LAZY_LOAD_ATTRS = [
    "data-src",
    "data-lazy-src",
    "data-original",
    "lazy-src",
    "original",
    "data-url",
    "src",  # 最後にフォールバック
]

# 除外するパターン（アイコン、ロゴなど）
EXCLUDE_PATTERNS = [
    r'/icon[s]?/',
    r'/logo[s]?/',
    r'/sprite',
    r'/common/',
    r'/share/',
    r'/sns/',
    r'\.svg$',
    r'favicon',
    r'/arrow',
    r'/button',
    r'/bg[_-]',
    r'blank\.gif',
    r'spacer\.gif',
    r'1x1',
    r'placeholder',
    r'opg_400_400',  # autohome OGPプレースホルダ
]


def fetch_html(url: str) -> str:
    r = requests.get(url, headers=UA, timeout=30)
    r.raise_for_status()
    return r.text


def extract_og_image(url: str, html: str) -> str | None:
    """OGP画像を抽出"""
    soup = BeautifulSoup(html, "html.parser")
    tag = soup.find("meta", property="og:image") or soup.find("meta", attrs={"name": "og:image"})
    if tag and tag.get("content"):
        img_url = urljoin(url, tag["content"])
        if not is_excluded_url(img_url):
            return img_url
    tag = soup.find("meta", attrs={"name": "twitter:image"})
    if tag and tag.get("content"):
        img_url = urljoin(url, tag["content"])
        if not is_excluded_url(img_url):
            return img_url
    return None


def get_image_src(img_tag) -> str | None:
    """imgタグから最適なsrcを取得（遅延読み込み対応）"""
    for attr in LAZY_LOAD_ATTRS:
        src = img_tag.get(attr)
        if src and not src.startswith("data:") and len(src) > 10:
            return src
    return None


def is_excluded_url(img_url: str) -> bool:
    """除外パターンにマッチするかチェック"""
    if not img_url:
        return True
    for pattern in EXCLUDE_PATTERNS:
        if re.search(pattern, img_url, re.I):
            return True
    return False


def extract_article_images(url: str, html: str) -> list[str]:
    """記事本文から画像URLを抽出（フィルタリング付き）"""
    soup = BeautifulSoup(html, "html.parser")
    images = set()
    
    # 1. 記事セレクタで画像を取得
    for selector in ARTICLE_SELECTORS:
        try:
            for img in soup.select(selector):
                src = get_image_src(img)
                if src:
                    full_url = urljoin(url, src)
                    if not is_excluded_url(full_url):
                        images.add(full_url)
        except Exception:
            continue
    
    # 2. セレクタで見つからなかった場合、コンテナ内の画像を取得
    if not images:
        for container in soup.select("main, article, .content, #content, [class*='article'], [class*='Article']"):
            for img in container.find_all("img"):
                src = get_image_src(img)
                if src:
                    full_url = urljoin(url, src)
                    if not is_excluded_url(full_url):
                        images.add(full_url)
    
    # 3. それでも見つからなければ、全imgタグから取得
    if not images:
        for img in soup.find_all("img"):
            src = get_image_src(img)
            if src:
                full_url = urljoin(url, src)
                if not is_excluded_url(full_url):
                    images.add(full_url)
    
    return list(images)


def download_image(img_url: str) -> bytes:
    r = requests.get(img_url, headers=UA, timeout=30)
    r.raise_for_status()
    return r.content


def get_image_size(img_bytes: bytes) -> tuple[int, int]:
    """画像サイズを取得"""
    im = Image.open(io.BytesIO(img_bytes))
    return im.size


def resize_for_vlm(img_bytes: bytes, max_side: int = 768) -> bytes:
    im = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    w, h = im.size
    scale = max(w, h) / max_side
    if scale > 1:
        im = im.resize((int(w/scale), int(h/scale)))
    out = io.BytesIO()
    im.save(out, format="JPEG", quality=85)
    return out.getvalue()


def to_data_url_jpeg(img_bytes: bytes) -> str:
    b64 = base64.b64encode(img_bytes).decode("utf-8")
    return f"data:image/jpeg;base64,{b64}"


def is_car_interior(img_bytes: bytes) -> dict:
    data_url = to_data_url_jpeg(img_bytes)
    prompt = """あなたは画像判定器です。
この画像が「車室内（インテリア）」の写真なら interior=true。
例: コクピット、ダッシュボード、ステアリング、シート、室内照明、車内空間。
外観、人物集合、ロゴ、製品単体、展示会のブース、グラフ/スライドは interior=false。

必ずJSONのみで返答:
{"interior": true/false, "confidence": 0.0-1.0, "reason": "短い理由"}"""

    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role":"user","content":[
                {"type":"text","text":prompt},
                {"type":"image_url","image_url":{"url":data_url}}
            ]}
        ],
        temperature=0
    )
    txt = resp.choices[0].message.content.strip()
    # 返答がJSON以外の余計な文字を含む場合に備えて雑に抽出
    m = re.search(r"\{.*\}", txt, re.S)
    if not m:
        return {"interior": False, "confidence": 0.0, "reason": "No JSON returned", "raw": txt}
    return json.loads(m.group(0))


def process_article(url: str) -> list[dict]:
    """1つの記事を処理し、全画像の判定結果を返す"""
    results = []
    
    try:
        html = fetch_html(url)
        
        # OGP画像と記事内画像を収集
        all_images = set()
        
        og_image = extract_og_image(url, html)
        if og_image:
            all_images.add(og_image)
        
        article_images = extract_article_images(url, html)
        all_images.update(article_images)
        
        if not all_images:
            return [{"article_url": url, "image_url": None, "interior": False, 
                     "confidence": 0.0, "reason": "No images found"}]
        
        print(f"  Found {len(all_images)} candidate images", flush=True)
        
        # 各画像を処理
        for img_url in all_images:
            try:
                raw = download_image(img_url)
                w, h = get_image_size(raw)
                
                # サイズフィルタ：小さすぎる画像はスキップ
                if w < MIN_IMAGE_SIZE and h < MIN_IMAGE_SIZE:
                    print(f"    Skipped (too small: {w}x{h}): {img_url[:60]}...", flush=True)
                    continue
                
                small = resize_for_vlm(raw, max_side=768)
                verdict = is_car_interior(small)
                
                result = {
                    "article_url": url,
                    "image_url": img_url,
                    "image_size": f"{w}x{h}",
                    **verdict
                }
                results.append(result)
                
                status = "[INTERIOR]" if verdict.get("interior") else "[Not interior]"
                print(f"    {status}: {img_url[:70]}...", flush=True)
                
            except Exception as e:
                print(f"    Error processing image: {str(e)[:50]}", flush=True)
                continue
        
    except Exception as e:
        results.append({
            "article_url": url, 
            "image_url": None, 
            "interior": False, 
            "confidence": 0.0, 
            "reason": f"Error: {e}"
        })
    
    return results


def main():
    with open("urls.txt", "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip()]

    all_results = []
    interior_images = []
    
    for url in tqdm(urls, desc="Processing articles"):
        print(f"\nProcessing: {url}", flush=True)
        results = process_article(url)
        all_results.extend(results)
        
        # 内装画像のみを抽出
        for r in results:
            if r.get("interior"):
                interior_images.append(r)

    # 全結果を保存
    with open("result.json", "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    
    # 内装画像のみを別ファイルに保存
    with open("interior_images.json", "w", encoding="utf-8") as f:
        json.dump(interior_images, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*50}", flush=True)
    print(f"Total images processed: {len(all_results)}", flush=True)
    print(f"Interior images found: {len(interior_images)}", flush=True)
    print(f"Saved: result.json (all results)", flush=True)
    print(f"Saved: interior_images.json (interior only)", flush=True)


if __name__ == "__main__":
    main()
