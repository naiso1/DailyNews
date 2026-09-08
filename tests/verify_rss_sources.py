"""Opt-in RSS/article/image checks; never run collection, an LLM, or publishing.

Pass --feed NAME URL (repeatable) and --report PATH. At most five recent
entries per feed are checked with the collection script's actual helpers.
"""

import argparse
import ast
from datetime import datetime, timezone
from io import BytesIO
import json
from pathlib import Path
import re
import sys
from types import SimpleNamespace
from urllib.parse import urlparse
from urllib.request import getproxies

from bs4 import BeautifulSoup
import feedparser
from PIL import Image, ImageStat
import requests

ROOT = Path(__file__).resolve().parents[1]
COLLECTION = ROOT / "\u30cb\u30e5\u30fc\u30b9\u53ce\u96c6"
MAX_BYTES = 12 * 1024 * 1024


def collection_helpers(session):
    # Importing google_search_script would also run its top-level startup code.
    tree = ast.parse((COLLECTION / "google_search_script.py").read_text(encoding="utf-8-sig"))
    names = {"extract_image_from_rss", "rank_image_url", "is_suspicious_image_url",
             "normalize_text", "fetch_article_text", "parse_date"}
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    if len(nodes) != len(names):
        raise RuntimeError("Collection helpers changed; review the verifier before running.")
    from dateutil import parser
    env = {"re": re, "BeautifulSoup": BeautifulSoup, "parser": parser, "urlparse": urlparse,
           "requests": SimpleNamespace(get=lambda url, **kwargs: bounded_get(session, url)),
           "_article_text_cache": {}}
    constants = {"SUSPICIOUS_IMAGE_MARKERS", "HEADERS", "SUMMARY_HTML_CHARS"}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in constants:
                    env[target.id] = ast.literal_eval(node.value)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "collection-rss-helpers", "exec"), env)
    return env


def bounded_get(session, url):
    if urlparse(url).scheme not in {"http", "https"}:
        raise ValueError("Only HTTP(S) URLs can be tested.")
    with session.get(url, timeout=(8, 15), stream=True) as response:
        chunks = []
        size = 0
        for chunk in response.iter_content(65536):
            size += len(chunk)
            if size > MAX_BYTES:
                raise ValueError("Response exceeds the 12 MiB verification limit.")
            chunks.append(chunk)
        response._content = b"".join(chunks)
        response._content_consumed = True
        return response


def check_feed(name, url, count, session, helpers):
    result = {"name": name, "url": url, "passed": False, "samples": []}
    try:
        response = bounded_get(session, url)
        result.update(status=response.status_code, final_url=response.url)
        response.raise_for_status()
        feed = feedparser.parse(response.content)
        result.update(version=feed.version, entry_count=len(feed.entries), malformed=bool(feed.bozo))
        if not feed.version or len(feed.entries) < count or feed.bozo:
            raise ValueError("Feed must be valid RSS/Atom with enough sample entries.")
        for entry in feed.entries[:count]:
            sample = {"title": entry.get("title", ""), "article_url": entry.get("link", "")}
            result["samples"].append(sample)
            try:
                published = entry.get("published") or entry.get("updated")
                sample["date"] = helpers["parse_date"](published)
                image_url = helpers["extract_image_from_rss"](entry)
                sample["rss_image_url"] = image_url
                if not sample["date"] or not image_url:
                    raise ValueError("The production parser cannot extract a date or RSS image.")
                if helpers["is_suspicious_image_url"](image_url):
                    raise ValueError("The production parser flags the RSS image as suspicious.")
                article = helpers["fetch_article_text"](sample["article_url"])
                sample.update(article_chars=len(article), article_preview=article[:500])
                if len(article) < 500:
                    raise ValueError("Article text is missing or too short.")
                # No cookies or publisher Referer: the image must work outside its own site.
                image_response = bounded_get(session, image_url)
                sample["image_status"] = image_response.status_code
                image_response.raise_for_status()
                with Image.open(BytesIO(image_response.content)) as image:
                    image.load()
                    sample.update(image_size=list(image.size), image_format=image.format,
                                  image_bytes=len(image_response.content))
                    variation = max(ImageStat.Stat(image.convert("RGB").resize((64, 64))).stddev)
                    sample["image_variation"] = round(variation, 2)
                    if image.width < 600 or image.height < 300 or variation < 4:
                        raise ValueError("Image is too small or appears blank.")
                sample["passed"] = True
            except Exception as exc:
                sample.update(passed=False, error=f"{type(exc).__name__}: {exc}")
            print(f"  [{'OK' if sample['passed'] else 'FAIL'}] {sample['title']}", flush=True)
        result["passed"] = all(sample["passed"] for sample in result["samples"])
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feed", nargs=2, action="append", required=True, metavar=("NAME", "URL"))
    parser.add_argument("--samples", type=int, choices=range(1, 6), default=5)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--windows-proxy", action="store_true",
                        help="Use the saved Windows proxy instead of inherited proxy variables.")
    args = parser.parse_args()
    session = requests.Session()
    # Read the existing proxy configuration; do not modify system/env settings.
    session.trust_env = False
    proxies = getproxies()
    if args.windows_proxy:
        from urllib.request import getproxies_registry
        proxies = getproxies_registry()
    session.proxies = {k: v for k, v in proxies.items() if k in ("http", "https")}
    helpers = collection_helpers(session)
    session.headers.update(helpers["HEADERS"])
    report = {"checked_at": datetime.now(timezone.utc).isoformat(),
              "scope": "RSS parsing, sample article extraction and image decoding only",
              "samples_per_feed": args.samples, "feeds": []}
    for name, url in args.feed:
        print(f"[FEED] {name}", flush=True)
        result = check_feed(name, url, args.samples, session, helpers)
        report["feeds"].append(result)
        print(f"[{'PASS' if result['passed'] else 'FAIL'}] {name}", flush=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Report: {args.report}")
    return 0 if all(feed["passed"] for feed in report["feeds"]) else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
