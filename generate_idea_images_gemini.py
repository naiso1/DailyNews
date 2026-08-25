# -*- coding: utf-8 -*-
import argparse
import base64
import io
import os
import re
from pathlib import Path

import requests
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent
INSIGHTS_PATH = ROOT / "insights_data.js"
NEWS_PATH = ROOT / "news_data.js"
IMAGES_DIR = ROOT / "images"
IMAGES_DIR.mkdir(exist_ok=True)

DEFAULT_MODEL = "gemini-3.1-flash-image-preview"
DEFAULT_ASPECT_RATIO = "1:1"
DEFAULT_IMAGE_SIZE = "512px"  # 0.5K tier
DEFAULT_API_VERSION = "v1beta"
DEFAULT_PROXY = "http://202.15.64.202:8080"


def _windows_proxy_server() -> str:
    if os.name != "nt":
        return ""
    try:
        import winreg

        path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
            enabled = int(winreg.QueryValueEx(key, "ProxyEnable")[0])
            value = str(winreg.QueryValueEx(key, "ProxyServer")[0]).strip()
        if not enabled or not value:
            return ""
        if ";" in value or "=" in value:
            entries = {}
            for part in value.split(";"):
                if "=" in part:
                    name, server = part.split("=", 1)
                    entries[name.strip().lower()] = server.strip()
            value = entries.get("https") or entries.get("http") or ""
        if value and "://" not in value:
            value = f"http://{value}"
        return value
    except Exception:
        return ""


def configure_external_proxy() -> str:
    proxy = (
        os.environ.get("HTTPS_PROXY")
        or os.environ.get("HTTP_PROXY")
        or _windows_proxy_server()
        or DEFAULT_PROXY
    )
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        os.environ.setdefault(name, proxy)
    return proxy


def extract_latest_block(text: str) -> str:
    start = text.find("window.DAILY_INSIGHTS")
    if start == -1:
        return ""
    start = text.find("{", start)
    if start == -1:
        return ""
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]
    return ""


def extract_ideas(block: str):
    ideas = []
    pattern = re.compile(
        r"\{\s*id:\s*(\d+)\s*,\s*img:\s*\"([^\"]*)\"\s*,\s*title:\s*\"([^\"]*)\"\s*,\s*desc:\s*\"([^\"]*)\"(?:\s*,\s*imagePrompt:\s*\"([^\"]*)\")?(?:\s*,\s*sourceNewsIds:\s*\[([^\]]*)\])?\s*\}",
        re.DOTALL,
    )
    for m in pattern.finditer(block):
        ideas.append(
            {
                "id": int(m.group(1)),
                "img": m.group(2),
                "title": m.group(3),
                "desc": m.group(4),
                "imagePrompt": m.group(5) or "",
                "sourceNewsIds": re.findall(r"[a-z]{2,5}\d+", m.group(6) or "", flags=re.IGNORECASE),
            }
        )
    return ideas


def extract_date(block: str) -> str:
    m = re.search(r'date:\s*"([^"]+)"', block)
    return m.group(1) if m else ""


def extract_news_reference_map(text: str) -> dict[str, dict]:
    """Extract the fields needed to download an idea's source-news images."""
    result = {}
    object_pattern = re.compile(
        r'\{\s*id:\s*"(?P<id>[a-z]{2,5}\d+)"(?P<body>.*?)\n\s*\}',
        re.DOTALL | re.IGNORECASE,
    )
    for match in object_pattern.finditer(text):
        body = match.group("body")
        item = {"id": match.group("id").lower()}
        for field in ("title", "url", "img"):
            value = re.search(rf'{field}:\s*"((?:\\.|[^"\\])*)"', body, flags=re.DOTALL)
            item[field] = (value.group(1) if value else "").replace("\\/", "/").replace('\\"', '"')
        result[item["id"]] = item
    return result


def _prepare_inline_image(raw: bytes) -> tuple[str, bytes]:
    """Normalize a downloaded image so Gemini receives a compact supported file."""
    with Image.open(io.BytesIO(raw)) as source:
        image = ImageOps.exif_transpose(source)
        image.thumbnail((1280, 1280), Image.Resampling.LANCZOS)
        has_alpha = image.mode in ("RGBA", "LA") or "transparency" in image.info
        output = io.BytesIO()
        if has_alpha:
            image.convert("RGBA").save(output, format="PNG", optimize=True)
            return "image/png", output.getvalue()
        image.convert("RGB").save(output, format="JPEG", quality=86, optimize=True)
        return "image/jpeg", output.getvalue()


def download_reference_image(item: dict, timeout: int = 60) -> tuple[str, bytes]:
    image_url = (item.get("img") or "").strip()
    if not image_url:
        raise ValueError("news item has no image URL")
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
        ),
        # Request formats Pillow can normalize. Some CDNs return AVIF even for
        # .jpg URLs when AVIF is advertised, and the local Pillow build does
        # not include an AVIF decoder.
        "Accept": "image/webp,image/jpeg,image/png,image/*;q=0.8,*/*;q=0.5",
    }
    if item.get("url"):
        headers["Referer"] = item["url"]
    response = requests.get(image_url, headers=headers, timeout=timeout)
    response.raise_for_status()
    if not response.content:
        raise ValueError("empty image response")
    return _prepare_inline_image(response.content)


def build_reference_parts(idea: dict, news_map: dict[str, dict], max_images: int = 2) -> list[dict]:
    parts = []
    seen_urls = set()
    for news_id in idea.get("sourceNewsIds", []):
        if len(parts) // 2 >= max_images:
            break
        item = news_map.get(str(news_id).lower())
        if not item:
            print(f"[REF_SKIP] {idea['id']}: {news_id} not found in news_data.js")
            continue
        image_url = (item.get("img") or "").strip()
        if not image_url or image_url in seen_urls:
            continue
        try:
            mime_type, image_bytes = download_reference_image(item)
        except Exception as exc:
            print(f"[REF_FAIL] {idea['id']}: {news_id}: {exc}")
            continue
        seen_urls.add(image_url)
        parts.append({"text": f"Reference news image ({news_id})."})
        parts.append(
            {
                "inline_data": {
                    "mime_type": mime_type,
                    "data": base64.b64encode(image_bytes).decode("ascii"),
                }
            }
        )
        print(f"[REF] {idea['id']}: {news_id} ({len(image_bytes) // 1024} KB)")
    return parts


def build_prompt(title: str, desc: str, image_prompt: str = "", has_references: bool = False) -> str:
    """Build an image brief and explain how any attached news photos should be used."""
    import re as _re
    clean_title = _re.sub(r'\*+', '', title).strip()
    clean_desc = _re.sub(r'\*+', '', desc).strip()
    clean_desc = _re.sub(r'\[[a-z]{2,5}\d+\]', '', clean_desc)
    clean_desc = _re.sub(r'\s+', ' ', clean_desc)[:700]
    concept_visual = image_prompt.strip() if image_prompt else clean_desc
    reference_instruction = (
        "The following image or images are source-news references. Use only their relevant physical design, "
        "material, packaging, and cabin-context cues. Do not copy their composition, branding, logos, text, "
        "people, or the complete vehicle. Transform the cues into the distinct concept described below."
        if has_references
        else ""
    )
    return (
        "Create one square photorealistic concept render of an automotive interior product. "
        "Do not include any text, labels, logos, captions, UI words, watermarks, or people. "
        "Do not design a seat, seat cushion, seat frame, seat cover, headrest, or seating product. "
        "Show the physical product clearly in a modern passenger-vehicle cabin with premium materials, "
        "realistic lighting, detailed surfaces, and production-feasible industrial design.\n"
        f"{reference_instruction}\n\n"
        f"Concept name: {clean_title}\n"
        f"Design brief: {clean_desc}\n"
        f"Requested visual direction: {concept_visual}"
    )


def update_image_path(js_text: str, idea_id: int, new_path: str) -> str:
    pattern = rf'(id:\s*{idea_id}\s*,\s*img:\s*")([^"]*)(")'
    return re.sub(pattern, rf"\1{new_path}\3", js_text, count=1)


def parse_first_image_bytes(resp_json: dict) -> bytes | None:
    for cand in resp_json.get("candidates", []) or []:
        content = cand.get("content", {}) or {}
        for part in content.get("parts", []) or []:
            inline = part.get("inlineData") or part.get("inline_data")
            if not inline:
                continue
            data = inline.get("data")
            if data:
                return base64.b64decode(data)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="latest", help="Target date (YYYY-MM-DD) or latest")
    ap.add_argument("--only-missing", action="store_true")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--ids", default="", help="Comma/range list like 201,202 or 201-210")
    ap.add_argument("--model", default=os.environ.get("GEMINI_IMAGE_MODEL", DEFAULT_MODEL))
    ap.add_argument("--aspect-ratio", default=os.environ.get("GEMINI_IMAGE_ASPECT_RATIO", DEFAULT_ASPECT_RATIO))
    ap.add_argument("--image-size", default=os.environ.get("GEMINI_IMAGE_SIZE", DEFAULT_IMAGE_SIZE))
    ap.add_argument("--api-version", default=os.environ.get("GEMINI_API_VERSION", DEFAULT_API_VERSION))
    ap.add_argument("--no-reference-images", action="store_true", help="Do not attach source-news images")
    ap.add_argument("--max-reference-images", type=int, default=2)
    args = ap.parse_args()
    configure_external_proxy()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[FAIL] GEMINI_API_KEY not set")
        return

    text = INSIGHTS_PATH.read_text(encoding="utf-8")
    block = extract_latest_block(text)
    if not block:
        print("No insights block found.")
        return
    date = extract_date(block)
    if args.date != "latest" and args.date and date != args.date:
        print(f"Latest date is {date}, not target {args.date}.")
    ideas = extract_ideas(block)
    if not ideas:
        print("No ideas found in latest block.")
        return

    news_map = {}
    if not args.no_reference_images:
        news_map = extract_news_reference_map(NEWS_PATH.read_text(encoding="utf-8"))

    updated = text
    count = 0
    id_filter = set()
    if args.ids:
        parts = [p.strip() for p in args.ids.split(",") if p.strip()]
        for p in parts:
            if "-" in p:
                a, b = p.split("-", 1)
                if a.isdigit() and b.isdigit():
                    for i in range(int(a), int(b) + 1):
                        id_filter.add(i)
            elif p.isdigit():
                id_filter.add(int(p))

    url = f"https://generativelanguage.googleapis.com/{args.api_version}/models/{args.model}:generateContent"
    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}

    for idea in ideas:
        if id_filter and idea["id"] not in id_filter:
            continue
        if args.limit and count >= args.limit:
            break
        current = idea["img"] or ""
        if args.only_missing and current and current != "images/idea_dummy.svg":
            continue
        dest_path = IMAGES_DIR / f"idea_{idea['id']}.png"
        if dest_path.exists() and not args.overwrite:
            updated = update_image_path(updated, idea["id"], f"images/{dest_path.name}")
            continue

        reference_parts = build_reference_parts(
            idea,
            news_map,
            max_images=max(0, args.max_reference_images),
        ) if news_map else []
        prompt_text = build_prompt(
            idea["title"],
            idea["desc"],
            idea.get("imagePrompt", ""),
            has_references=bool(reference_parts),
        )
        request_parts = [{"text": prompt_text}, *reference_parts]
        payload = {
            "contents": [{"parts": request_parts}],
            "generationConfig": {
                "responseModalities": ["IMAGE"],
                "imageConfig": {
                    "aspectRatio": args.aspect_ratio,
                    "imageSize": args.image_size,
                },
            },
        }
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=300)
            if resp.status_code >= 400:
                print(f"[FAIL] {idea['id']}: {resp.status_code} {resp.text[:400]}")
                continue
            image_bytes = parse_first_image_bytes(resp.json())
            if not image_bytes:
                print(f"[FAIL] {idea['id']}: no image payload")
                continue
            dest_path.write_bytes(image_bytes)
            updated = update_image_path(updated, idea["id"], f"images/{dest_path.name}")
            print(f"[OK] Saved {dest_path.name}")
            count += 1
        except Exception as e:
            print(f"[FAIL] {idea['id']}: {e}")

    INSIGHTS_PATH.write_text(updated, encoding="utf-8")
    print("Done.")


if __name__ == "__main__":
    main()
