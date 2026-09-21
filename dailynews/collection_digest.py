"""Issue dates and published-URL history for exterior collection."""
from datetime import date, timedelta
import json
import re


def collection_window(target_dates, days=7):
    if not target_dates:
        raise ValueError("An exterior digest requires an explicit issue date")
    issue = max(date.fromisoformat(str(value)) for value in target_dates)
    days = int(days)
    if not 1 <= days <= 7:
        raise ValueError("Exterior lookback must be between one and seven days")
    dates = [(issue - timedelta(days=offset)).isoformat() for offset in range(days - 1, -1, -1)]
    return {"issue_date": issue.isoformat(), "lookback_start": dates[0], "collection_dates": dates}


def published_news(path):
    """Read generated JS data as literals; do not execute it or import updater."""
    if not path.exists():
        return []
    return parse_published_news(path.read_text(encoding="utf-8-sig"))


def parse_published_news(text):
    """Read flat article literals, including source aliases and legacy TABs."""
    marker = re.search(r"window\.LOADED_NEWS_DATA\s*=\s*\[", text)
    if not marker:
        raise ValueError("Cannot verify exterior publication history")
    token = re.compile(r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"|[{}\[\]]')
    field = re.compile(r'"?\b([A-Za-z][A-Za-z0-9_]*)"?\s*:\s*("(?:\\.|[^"\\])*"|-?\d+(?:\.\d+)?|true|false|null)')
    depth = 0
    start = None
    entries = []
    for match in token.finditer(text, marker.end()):
        value = match.group()
        if value == "{":
            if depth == 0:
                start = match.start()
            depth += 1
        elif value == "}":
            depth -= 1
            if depth == 0:
                block = text[start:match.end()]
                fields = {key: json.loads(raw, strict=False) for key, raw in field.findall(block)}
                related = re.search(r'\brelatedUrls"?\s*:\s*(\[(?:\s*"(?:\\.|[^"\\])*"\s*,?)*\s*\])', block)
                if related:
                    fields["relatedUrls"] = json.loads(related.group(1), strict=False)
                if not fields.get("id") or not fields.get("url") or not fields.get("date"):
                    raise ValueError("Exterior published article is missing its identity/date")
                entries.append(fields)
        elif value == "]" and depth == 0:
            return entries
    raise ValueError("Exterior publication history is incomplete")


def published_issue(item):
    return item.get("digestDate") or item.get("date")


def published_row(item):
    countries = {"jp": "日本", "us": "米国", "eu": "欧州", "cn": "中国", "in": "インド"}
    return {
        "国": countries.get(item.get("country"), item.get("country", "")),
        "日付": item["date"], "URL": item["url"],
        "タイトル": item.get("title", ""), "タイトル（日本語）": item.get("title", ""),
        "内容": item.get("desc", ""), "内容（日本語）": item.get("desc", ""),
        "出展サイト": item.get("source", ""), "画像URL": item.get("img", ""),
        "LLM判定": "対象", "LLM後処理": "実施",
        "内装関連度": item.get("exteriorScore", item.get("interiorScore", item.get("productScore", 0))),
        "内装判定理由": item.get("exteriorReason", item.get("interiorReason", "既公開記事を同じ号に保持")),
        "記事区分": item.get("contentCategory", "product"), "トレンド分類": item.get("trendTopic", ""),
        "関連URL": json.dumps(item.get("relatedUrls", []), ensure_ascii=False),
    }
