"""Bounded event discovery; candidate review never guarantees publication."""
from dailynews.event_tags import LABELS, derive

SEARCH_START = "2026-09-15"
SEARCH_END = "2026-10-23"  # Include reporting for one week after the show.
REVIEW_SLOTS = 3
QUERIES = (
    "CEATEC 2026",
    '2026 (JMS OR "Japan Mobility Show" OR "ジャパンモビリティショー")',
)


def search_keywords(country, target_dates):
    if country == "日本" and any(SEARCH_START <= str(day) <= SEARCH_END for day in target_dates or []):
        return list(QUERIES)
    return []


def review_candidates(items, limit=REVIEW_SLOTS):
    """Reserve a few existing review slots, preserving input ranking."""
    if limit <= 0:
        return []
    result = []
    for item in items:
        if item.get("国") != "日本" or not SEARCH_START <= str(item.get("日付", "")) <= SEARCH_END:
            continue
        if LABELS[0] in derive({"title": item.get("タイトル"), "originalDesc": item.get("内容"),
                               "date": item.get("日付"), "url": item.get("URL")}):
            result.append(item)
            if len(result) >= limit:
                break
    return result
