import argparse
import json
import os
import re
import time
from pathlib import Path
import urllib.request
import urllib.error


ROOT = Path(__file__).resolve().parent
INSIGHTS_PATH = ROOT / "insights_data.js"
IMAGES_DIR = ROOT / "images"

DEFAULT_WORKER_URL = "https://black-smoke-a332.tgiid2gr5t.workers.dev/"


# ----------------------------
# HTTP helpers
# ----------------------------
def post_json(url: str, payload: dict, req_headers: dict, timeout_sec: int = 300):
    """
    POST JSON to Cloudflare Worker.
    Returns: (status:int, resp_headers:dict, body:bytes)
    Raises: RuntimeError with readable body if HTTPError.
    """
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers=req_headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            status = getattr(resp, "status", 200)
            resp_headers = dict(resp.headers.items())
            body = resp.read()
            return status, resp_headers, body
    except urllib.error.HTTPError as e:
        # Worker may return JSON error body; capture it for debugging
        err_body = e.read()
        text = err_body.decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTPError {e.code}: {text}") from None
    except Exception as e:
        raise RuntimeError(f"Request failed: {e}") from None


def get_content_type(headers: dict) -> str:
    # header key may vary
    return headers.get("Content-Type") or headers.get("content-type") or ""


def is_image_content(headers: dict) -> bool:
    return get_content_type(headers).startswith("image/")


def choose_ext_from_content_type(content_type: str) -> str:
    ct = (content_type or "").lower()
    if "png" in ct:
        return ".png"
    if "jpeg" in ct or "jpg" in ct:
        return ".jpg"
    if "webp" in ct:
        return ".webp"
    return ".img"


def request_image_with_backoff(url: str, payload: dict, req_headers: dict,
                               retries: int, base_delay: float, timeout_sec: int = 300):
    """
    Retry on 429 and 5xx. Returns (status, resp_headers, body).
    """
    last_err = None
    for attempt in range(retries + 1):
        try:
            status, resp_headers, body = post_json(url, payload, req_headers, timeout_sec=timeout_sec)

            # Retry conditions
            if status == 429 or status >= 500:
                delay = base_delay * (2 ** attempt)
                time.sleep(delay)
                continue

            return status, resp_headers, body
        except RuntimeError as e:
            msg = str(e)
            last_err = msg
            # Retry on typical transient errors
            if ("HTTPError 429" in msg) or ("HTTPError 500" in msg) or ("HTTPError 502" in msg) or ("HTTPError 503" in msg) or ("HTTPError 504" in msg):
                delay = base_delay * (2 ** attempt)
                time.sleep(delay)
                continue
            raise
    raise RuntimeError(f"Rate limit exceeded or server error after retries. last={last_err}")


# ----------------------------
# Parse insights_data.js
# ----------------------------
def extract_latest_block(text: str) -> str:
    """
    Extract the object assigned around `window.DAILY_INSIGHTS = {...}`
    """
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
                    return text[start:i + 1]
    return ""


def extract_date(block: str) -> str:
    m = re.search(r'date:\s*"([^"]+)"', block)
    return m.group(1) if m else ""


def extract_ideas(block: str):
    """
    Expect entries like:
    { id: 1, img: "images/xxx.png", title: "....", desc: "...." }
    """
    ideas = []
    pattern = re.compile(
        r"\{\s*id:\s*(\d+)\s*,\s*img:\s*\"([^\"]*)\"\s*,\s*title:\s*\"([^\"]*)\"\s*,\s*desc:\s*\"([^\"]*)\"\s*\}",
        re.DOTALL,
    )
    for m in pattern.finditer(block):
        ideas.append(
            {
                "id": int(m.group(1)),
                "img": m.group(2),
                "title": m.group(3),
                "desc": m.group(4),
            }
        )
    return ideas


def update_image_path(js_text: str, idea_id: int, new_path: str) -> str:
    pattern = rf'(id:\s*{idea_id}\s*,\s*img:\s*")([^"]*)(")'
    return re.sub(pattern, rf'\1{new_path}\3', js_text, count=1)


# ----------------------------
# Prompt building
# ----------------------------
def build_prompt(title: str, desc: str, style: str, extra: str = "") -> str:
    """
    style:
      - cgi: Unreal/KeyShot style (recommended for your goal)
      - photo: photorealistic (less CG)
    """
    base = f"{title}. {desc}".strip()

    if style == "photo":
        tail = (
            "Photorealistic OEM production car interior, realistic materials, "
            "stitched leather, matte soft-touch plastics, brushed aluminum, "
            "accurate vents/buttons/knobs, subtle ambient lighting strip (light guide) visible, "
            "no logos, no text, no watermark, sharp focus, ultra detailed."
        )
    else:
        # default: CG
        tail = (
            "High-end automotive interior CGI render (Unreal Engine / KeyShot style), 1:1 square composition, "
            "driver seat viewpoint looking forward, clean modern OEM cabin, accurate geometry and proportions, "
            "a continuous thin ambient light guide (light pipe) embedded along dashboard-to-door seam, "
            "uniform diffusion, no hotspots, warm white 3000K, subtle glow (not neon), "
            "premium stitched leather dashboard, matte soft-touch plastics, brushed aluminum trim, "
            "realistic vents/buttons/knobs, studio lighting, sharp focus, ultra detailed, "
            "no screen UI text, no logos, no watermark, no vignette."
        )

    if extra:
        tail = tail + " " + extra.strip()

    return base + "\n" + tail


# ----------------------------
# Main
# ----------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="latest", help="Target date (YYYY-MM-DD) or latest")
    ap.add_argument("--limit", type=int, default=0, help="Limit number of images (0=all)")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--only-missing", action="store_true")
    ap.add_argument("--sleep", type=float, default=1.2)
    ap.add_argument("--retries", type=int, default=4)
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--width", type=int, default=1024)
    ap.add_argument("--height", type=int, default=1024)
    ap.add_argument("--negative", default="")
    ap.add_argument("--style", choices=["cgi", "photo"], default="cgi")
    ap.add_argument("--extra", default="", help="Extra prompt tail (optional)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    worker_url = os.getenv("CF_WORKER_URL", DEFAULT_WORKER_URL).strip()
    if not worker_url:
        raise RuntimeError("CF_WORKER_URL が未設定です。")

    # Request headers (DO NOT overwrite by response headers!)
    extra_headers = {}
    token = os.getenv("CF_WORKER_TOKEN", "").strip()
    if token:
        extra_headers["Authorization"] = f"Bearer {token}"

    header_json = os.getenv("CF_WORKER_HEADER_JSON", "").strip()
    if header_json:
        try:
            extra_headers.update(json.loads(header_json))
        except Exception:
            raise RuntimeError("CF_WORKER_HEADER_JSON がJSONとして不正です。")

    req_headers = {"Content-Type": "application/json", **extra_headers}

    # Load JS file
    text = INSIGHTS_PATH.read_text(encoding="utf-8")
    block = extract_latest_block(text)
    if not block:
        print("No insights block found.")
        return

    date = extract_date(block)
    if args.date != "latest" and args.date and date != args.date:
        print(f"Latest date is {date}, not target {args.date} (will continue).")

    ideas = extract_ideas(block)
    if not ideas:
        print("No ideas found in latest block.")
        return

    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    updated_text = text
    count = 0

    for idea in ideas:
        if args.limit and count >= args.limit:
            break

        current = idea.get("img") or ""

        # only-missing logic
        if args.only_missing and current and current != "images/idea_dummy.svg":
            continue

        # prompt
        prompt = build_prompt(idea["title"], idea["desc"], style=args.style, extra=args.extra)

        payload = {
            "prompt": prompt,
            "width": int(args.width),
            "height": int(args.height),
            "seed": int(time.time() * 1000) % 1_000_000_000 + int(idea["id"]),
        }
        if args.negative:
            payload["negative_prompt"] = args.negative

        # Generate output filename (temporary ext, will be replaced if needed)
        # We'll decide ext after receiving Content-Type
        tmp_path = IMAGES_DIR / f"idea_{idea['id']}.bin"

        # If exists and not overwrite: just update js path and skip generation
        # (NOTE: if you want to auto detect ext here, you can, but simple is fine)
        existing_png = IMAGES_DIR / f"idea_{idea['id']}.png"
        existing_jpg = IMAGES_DIR / f"idea_{idea['id']}.jpg"
        if not args.overwrite and (existing_png.exists() or existing_jpg.exists()):
            chosen = existing_png if existing_png.exists() else existing_jpg
            updated_text = update_image_path(updated_text, idea["id"], f"images/{chosen.name}")
            continue

        if args.dry_run:
            print(f"[DRY] {idea['id']} -> generate {args.width}x{args.height}")
            count += 1
            continue

        status, resp_headers, body = request_image_with_backoff(
            worker_url,
            payload,
            req_headers,
            retries=args.retries,
            base_delay=max(1.0, float(args.sleep)),
            timeout_sec=int(args.timeout),
        )

        if not is_image_content(resp_headers):
            preview = body[:500].decode("utf-8", errors="replace")
            raise RuntimeError(f"Not an image. status={status} content-type={get_content_type(resp_headers)} body={preview}")

        ctype = get_content_type(resp_headers)
        ext = choose_ext_from_content_type(ctype)
        out_path = IMAGES_DIR / f"idea_{idea['id']}{ext}"

        out_path.write_bytes(body)
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass

        updated_text = update_image_path(updated_text, idea["id"], f"images/{out_path.name}")
        print(f"Saved image: {out_path.name} status={status} type={ctype} bytes={len(body)}")

        count += 1
        time.sleep(float(args.sleep))

    if not args.dry_run:
        INSIGHTS_PATH.write_text(updated_text, encoding="utf-8")

    print("Done.")


if __name__ == "__main__":
    main()
