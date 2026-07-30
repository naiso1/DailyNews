import argparse
import datetime as dt
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTENT_FILE = ROOT / "content" / "posts.json"
IMAGE_DIR = ROOT / "content" / "images"
DEPLOY_SCRIPT = ROOT / "deploy.ps1"
ALLOWED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def normalize_list(value):
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        text = str(item).strip()
        if text and text not in result:
            result.append(text)
    return result


def make_post_id():
    return "ig" + dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def validate_text(value, field, maximum, required=True):
    text = str(value or "").strip()
    if required and not text:
        raise ValueError(f"{field} is required.")
    if len(text) > maximum:
        raise ValueError(f"{field} must be {maximum} characters or fewer.")
    return text


def normalize_post(source, post_id):
    if not isinstance(source, dict):
        raise ValueError("The manifest must contain one JSON object.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{2,79}", post_id):
        raise ValueError("id may contain only letters, numbers, underscores, and hyphens.")
    return {
        "id": post_id,
        "title": validate_text(source.get("title"), "title", 120),
        "summary": validate_text(source.get("summary"), "summary", 500),
        "body": validate_text(source.get("body"), "body", 10000),
        "category": validate_text(source.get("category", "アイデア"), "category", 40),
        "region": validate_text(source.get("region", "グローバル"), "region", 40),
        "tags": normalize_list(source.get("tags"))[:20],
        "image": validate_text(source.get("image", ""), "image", 300, required=False),
        "imageAlt": validate_text(
            source.get("imageAlt", ""), "imageAlt", 240, required=False
        ),
        "author": validate_text(
            source.get("author", "Antigravity"), "author", 80
        ),
        "sourceIds": normalize_list(source.get("sourceIds"))[:20],
        "publishedAt": validate_text(
            source.get("publishedAt", dt.date.today().isoformat()),
            "publishedAt",
            40,
        ),
        "status": "draft" if source.get("status") == "draft" else "published",
        "featured": bool(source.get("featured", False)),
    }


def write_posts(posts):
    CONTENT_FILE.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(posts, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=CONTENT_FILE.parent,
        delete=False,
        newline="\n",
    ) as temporary:
        temporary.write(text)
        temporary_path = Path(temporary.name)
    temporary_path.replace(CONTENT_FILE)


def deploy():
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(DEPLOY_SCRIPT),
        ],
        cwd=ROOT,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(f"Interiorgram deployment failed: exit {result.returncode}")


def main():
    parser = argparse.ArgumentParser(
        description="Add one Antigravity-generated post and publish Interiorgram."
    )
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--image", type=Path)
    parser.add_argument("--id", dest="post_id")
    parser.add_argument("--replace", action="store_true")
    parser.add_argument(
        "--no-publish",
        action="store_true",
        help="Update local content only; do not deploy to IEWEB01.",
    )
    args = parser.parse_args()

    manifest = load_json(args.manifest)
    post_id = args.post_id or str(manifest.get("id") or "").strip() or make_post_id()
    post = normalize_post(manifest, post_id)

    if args.image:
        image_path = args.image.resolve()
        if not image_path.is_file():
            raise FileNotFoundError(f"Image was not found: {image_path}")
        suffix = image_path.suffix.lower()
        if suffix not in ALLOWED_IMAGE_SUFFIXES:
            raise ValueError(f"Unsupported image format: {suffix}")
        IMAGE_DIR.mkdir(parents=True, exist_ok=True)
        destination = IMAGE_DIR / f"{post_id}{suffix}"
        shutil.copy2(image_path, destination)
        post["image"] = f"media/{destination.name}"
        if not post["imageAlt"]:
            raise ValueError("imageAlt is required when an image is supplied.")

    posts = load_json(CONTENT_FILE) if CONTENT_FILE.exists() else []
    if not isinstance(posts, list):
        raise ValueError("posts.json must contain a JSON array.")
    existing_index = next(
        (index for index, item in enumerate(posts) if item.get("id") == post_id),
        None,
    )
    if existing_index is not None:
        if not args.replace:
            raise ValueError(f"Post already exists: {post_id} (use --replace)")
        posts[existing_index] = post
    else:
        posts.append(post)

    posts.sort(
        key=lambda item: (str(item.get("publishedAt", "")), str(item.get("id", ""))),
        reverse=True,
    )
    write_posts(posts)
    print(f"[OK] Added Interiorgram post: {post_id}")

    if not args.no_publish:
        deploy()
        print("[OK] Published to http://IEWEB01/interiorgram/")
    else:
        print("[INFO] Local content updated; server deployment skipped.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
