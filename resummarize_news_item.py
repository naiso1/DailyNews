"""Resummarize one news item using a local LLM and update files."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
from pathlib import Path

import requests

NEWS_JS = Path("news_data.js")
SEARCH_CSV = Path("ニュース収集") / "search_results.csv"

LLM_ENDPOINT = os.environ.get("LLM_ENDPOINT", "http://127.0.0.1:1234/v1/chat/completions")
LLM_MODEL = os.environ.get("LLM_MODEL", "qwen/qwen3-vl-8b")
LLM_TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "30"))

SUMMARY_TITLE_LIMIT = 50
SUMMARY_CONTENT_LIMIT = 150


def has_japanese(text: str) -> bool:
    return bool(re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", text or ""))


def extract_keywords(text: str) -> list[str]:
    if not text:
        return []
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9+\-./]{2,}", text)
    return sorted(set(tokens))


def parse_json_field(text: str, key: str) -> str:
    try:
        data = json.loads(text)
        return str(data.get(key, "")).strip()
    except Exception:
        m = re.search(rf'"{re.escape(key)}"\s*:\s*"(.*?)"', text)
        if m:
            return m.group(1).strip()
    return ""


def trim_to_limit(text: str, limit: int) -> str:
    if not text:
        return ""
    if len(text) <= limit:
        return text if text.endswith("。") else text + "。"
    cut = text[:limit]
    # try to end at a sentence boundary
    if "。" in cut:
        cut = cut.rsplit("。", 1)[0] + "。"
    else:
        cut = cut.rstrip("、, ") + "。"
    return cut


def call_llm(prompt: str) -> str:
    payload = {
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
    }
    resp = requests.post(LLM_ENDPOINT, json=payload, timeout=LLM_TIMEOUT)
    if resp.status_code != 200:
        return ""
    return resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")


def summarize_with_llm(title: str, content: str) -> tuple[str, str]:
    prompt = (
        "以下の情報を統合して、日本語で要約してください。\n"
        f"条件1: タイトルは{SUMMARY_TITLE_LIMIT}字以内（文を途中で切らない）。\n"
        f"条件2: 内容は{SUMMARY_CONTENT_LIMIT}字以内（文を途中で切らない）。\n"
        "条件3: 事実ベースで簡潔に。\n"
        "条件4: 可能なら固有名詞/製品名を1つ以上含める。\n"
        "条件5: 内容は必ず句点で終える。\n"
        "条件6: 出力はJSONのみ。形式: {\"title\":\"...\",\"summary\":\"...\"}\n\n"
        f"既存タイトル: {title}\n"
        f"既存内容: {content}\n"
    )
    output = call_llm(prompt)
    s_title = parse_json_field(output, "title")
    s_body = parse_json_field(output, "summary")
    return s_title, s_body


def summarize_with_fallback(title: str, content: str) -> tuple[str, str]:
    s_title, s_body = summarize_with_llm(title, content)
    keywords = extract_keywords(title + " " + content)

    def ok(text: str) -> bool:
        if not text:
            return False
        if not has_japanese(text):
            return False
        if keywords and not any(k in text for k in keywords):
            return False
        return True

    if not ok(s_title):
        s_title = trim_to_limit(title, SUMMARY_TITLE_LIMIT)
    if not ok(s_body):
        s_body = trim_to_limit(content, SUMMARY_CONTENT_LIMIT)

    # enforce limits
    if len(s_title) > SUMMARY_TITLE_LIMIT:
        s_title = trim_to_limit(s_title, SUMMARY_TITLE_LIMIT)
    if len(s_body) > SUMMARY_CONTENT_LIMIT:
        s_body = trim_to_limit(s_body, SUMMARY_CONTENT_LIMIT)

    return s_title, s_body


def find_in_news_data(news_id: str) -> tuple[str, str, str] | None:
    text = NEWS_JS.read_text(encoding="utf-8")
    m = re.search(
        rf'id:\s*"{re.escape(news_id)}"[\s\S]*?title:\s*"(.*?)"[\s\S]*?desc:\s*"(.*?)"[\s\S]*?url:\s*"(.*?)"',
        text,
        re.S,
    )
    if not m:
        return None
    return m.group(1), m.group(2), m.group(3)


def update_news_data(news_id: str, title: str, desc: str) -> bool:
    text = NEWS_JS.read_text(encoding="utf-8")
    pattern = re.compile(
        rf'(id:\s*"{re.escape(news_id)}"[\s\S]*?title:\s*")'
        r"(.*?)"
        r'("[\s\S]*?desc:\s*")'
        r"(.*?)"
        r'("[\s\S]*?url:\s*"[^"]+")',
        re.S,
    )
    match = pattern.search(text)
    if not match:
        return False
    new_block = match.group(1) + title + match.group(3) + desc + match.group(5)
    text = text[: match.start()] + new_block + text[match.end() :]
    NEWS_JS.write_text(text, encoding="utf-8")
    return True


def update_search_csv(url: str, title: str, desc: str) -> bool:
    if not SEARCH_CSV.exists():
        return False
    rows = []
    found = False
    with SEARCH_CSV.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.reader(f):
            if len(row) > 12 and row[12] == url:
                row[2] = title
                row[3] = title
                row[5] = desc
                row[6] = desc
                found = True
            rows.append(row)
    if not found:
        return False
    with SEARCH_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f).writerows(rows)
    return True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True, help="news_data.js id (e.g., jp453)")
    ap.add_argument("--url", help="source URL to summarize")
    ap.add_argument("--title", help="source title")
    ap.add_argument("--content", help="source content")
    args = ap.parse_args()

    title = args.title
    content = args.content
    url = args.url

    if not (title and content and url):
        found = find_in_news_data(args.id)
        if not found:
            raise SystemExit("news_data.js id not found")
        cur_title, cur_desc, cur_url = found
        title = title or cur_title
        content = content or cur_desc
        url = url or cur_url

    summary_title, summary_body = summarize_with_fallback(title, content)

    ok_js = update_news_data(args.id, summary_title, summary_body)
    ok_csv = update_search_csv(url, summary_title, summary_body)

    if not ok_js:
        raise SystemExit("news_data.js update failed (id not found)")
    if not ok_csv:
        raise SystemExit("search_results.csv update failed (url not found)")

    print("updated:", args.id)
    print("title:", summary_title)
    print("desc:", summary_body)


if __name__ == "__main__":
    main()
