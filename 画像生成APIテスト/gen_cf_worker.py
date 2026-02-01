import json
import time
import urllib.request
import urllib.error
from pathlib import Path

WORKER_URL = "https://black-smoke-a332.tgiid2gr5t.workers.dev/"  # ここだけ自分のURLに

def post_json(url: str, payload: dict, timeout_sec: int = 300) -> tuple[int, dict, bytes]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            status = resp.status
            headers = dict(resp.headers.items())
            body = resp.read()
            return status, headers, body
    except urllib.error.HTTPError as e:
        # Worker が JSON エラーを返している場合もここに来る
        err_body = e.read()
        raise RuntimeError(f"HTTPError {e.code}: {err_body.decode('utf-8', errors='replace')}")
    except Exception as e:
        raise RuntimeError(f"Request failed: {e}")

def save_image(out_path: Path, content_type: str, body: bytes):
    # content-type が image/png じゃなくて json/text だった場合に事故るのを防ぐ
    if not content_type.startswith("image/"):
        preview = body[:300].decode("utf-8", errors="replace")
        raise RuntimeError(f"Not an image. Content-Type={content_type}. Body head:\n{preview}")

    out_path.write_bytes(body)

def main():
    prompt = (
        "high-end automotive interior CGI render, Unreal Engine / KeyShot style, 1:1 square, "
        "camera at driver eye level, centered steering wheel, visible instrument cluster, center stack, and driver door trim, "
        "clean modern OEM cabin, accurate geometry and proportions, "
        "a continuous thin ambient light guide (light pipe) is embedded in the seam between dashboard upper and lower and "
        "continues seamlessly into the driver door trim, light guide is 6mm wide, uniform diffusion, no hotspots, "
        "warm white 3000K, subtle glow (not neon), "
        "premium stitched leather dashboard, matte soft-touch plastics, brushed aluminum trim, realistic vents/buttons/knobs, "
        "no screen UI text, no logos, no watermark, no vignette, studio lighting, sharp focus, ultra detailed"
    )

    payload_base = {
        "prompt": prompt,
        "width": 1024,
        "height": 1024,
        # Worker側が seed を受け取る作りなら有効
        # "seed": 12345,
        # Worker側が negative_prompt を受け取る作りなら有効
        # "negative_prompt": "logo, watermark, text, neon, distorted, lowres, blurry",
    }

    out_dir = Path("outputs")
    out_dir.mkdir(exist_ok=True)

    # 3枚生成（seedを変えたいなら payload_base["seed"]=... を入れる）
    for i in range(1, 4):
        payload = dict(payload_base)
        # seed を毎回変える例（Workerが対応している前提）
        payload["seed"] = int(time.time() * 1000) % 1_000_000_000 + i

        status, headers, body = post_json(WORKER_URL, payload)
        ctype = headers.get("Content-Type", "application/octet-stream")
        out_path = out_dir / f"out_{i}.png"
        save_image(out_path, ctype, body)
        print(f"[OK] {out_path}  status={status}  content-type={ctype}  bytes={len(body)}")

if __name__ == "__main__":
    main()
