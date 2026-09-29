"""Validate a dated exterior issue without changing source publication dates."""
from collections import Counter
from datetime import date


def _date(value):
    if not isinstance(value, str) or len(value) != 10:
        raise ValueError("Invalid exterior issue date")
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError("Invalid exterior issue date")
    return parsed


def validated_issue_context(receipt, items):
    """Legacy receipts keep their existing behavior; new receipts fail closed."""
    if receipt.get("edition_id") == "exterior" and receipt.get("completed") is not True:
        raise ValueError("Exterior collection is incomplete")
    if not receipt.get("issue_date"):
        return None
    issue = _date(receipt["issue_date"])
    start = _date(receipt.get("lookback_start"))
    targets = receipt.get("target_dates", [])
    source_dates = sorted({item["date"] for item in items})
    papers_enabled = receipt.get("papers_enabled") is True
    paper_start = _date(receipt.get("paper_lookback_start")) if papers_enabled else start
    paper_limit = receipt.get("maximum_papers", 0) if papers_enabled else 0
    if papers_enabled and (not 0 <= (issue - paper_start).days <= 29
                           or not isinstance(paper_limit, int) or not 1 <= paper_limit <= 10):
        raise ValueError("Invalid exterior paper window or limit")
    if (receipt.get("edition_id") != "exterior" or receipt.get("completed") is not True
            or receipt.get("selected_count") != len(items)
            or not targets or max(_date(value) for value in targets) != issue
            or not 0 <= (issue - start).days <= 6
            or any(not (paper_start if papers_enabled and item["country"] == "paper" else start)
                       <= _date(item["date"]) <= issue for item in items)
            or sorted(receipt.get("source_dates", [])) != source_dates
            or len({item["url"] for item in items}) != len(items)):
        raise ValueError("Exterior issue does not match its completed collection receipt")
    counts = Counter(item["country"] for item in items)
    if any((count > paper_limit if key == "paper" else key not in {"jp", "us", "eu", "cn", "in"} or count > 10)
           for key, count in counts.items()):
        raise ValueError("Exterior issue exceeds country limits")
    return {
        "issue_date": issue.isoformat(), "lookback_start": start.isoformat(),
        "source_dates": source_dates, "selected_by_country": dict(counts),
        "supplemental_count": sum(item["country"] != "paper" and item["date"] < issue.isoformat() for item in items),
        "selected_paper_count": counts.get("paper", 0),
        **({"papers_enabled": True, "paper_lookback_start": paper_start.isoformat(), "maximum_papers": paper_limit}
           if papers_enabled else {}),
    }


def selected_news_ids(items):
    ids = [item.get("newsId") for item in items]
    if any(not value for value in ids) or len(set(ids)) != len(ids):
        raise ValueError("Exterior issue requires unique published article IDs")
    return ids
