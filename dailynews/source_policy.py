"""Explicit edition source exclusions, independent of temporary HTTP failures."""
from urllib.parse import parse_qs, urlsplit


# 2026-10-28: readers confirmed MOTA's ad-permission wall; use the original
# publisher for both editions. Historical independent reports retain their IDs.
# A bot challenge or a single connection failure never adds a host to this list.
EXCLUDED_HOSTS = {"interior": ("autoc-one.jp",), "exterior": ("autoc-one.jp",)}


def is_excluded_source(url, edition_id):
    hosts = EXCLUDED_HOSTS.get(edition_id, ())
    value = str(url or "").strip()
    for _ in range(4):
        try:
            parts = urlsplit(value)
            host = (parts.hostname or "").lower().rstrip(".")
            if any(host == blocked or host.endswith("." + blocked) for blocked in hosts):
                return True
            # Recognise explicit search redirects without fetching the source.
            wrapper = any(host == domain or host.endswith("." + domain)
                          for domain in ("bing.com", "news.google.com", "duckduckgo.com"))
            if not wrapper:
                break
            query = parse_qs(parts.query)
            targets = query.get("url") or query.get("uddg") or []
            if not targets or targets[0] == value:
                break
            value = targets[0]
        except ValueError:
            break
    return False


def filter_sources(items, edition_id, url_key="URL"):
    return [item for item in items if not is_excluded_source(item.get(url_key), edition_id)]
