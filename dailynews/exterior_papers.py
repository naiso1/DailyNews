"""J-STAGE papers: verify article metadata; never summarize feed notifications."""
from datetime import date, timedelta
import re
from html import unescape
from urllib.parse import urlparse
from bs4 import BeautifulSoup

PAPER_COLUMNS = ["論文DOI", "論文発行日", "論文公開日", "論文取得日", "論文要約根拠"]
PAPER_FIELDS = dict(zip(("doi", "paperPublicationDate", "paperOnlineDate", "paperCollectedDate", "summaryBasis"), PAPER_COLUMNS))


def is_paper(country):
    return str(country or "").strip().lower() in {"論文", "paper", "papers"}


def paper_window(issue_date, days=30):
    if not 1 <= int(days) <= 30:
        raise ValueError("Paper lookback must be 1-30 days")
    issue = date.fromisoformat(issue_date)
    return [(issue - timedelta(days=n)).isoformat() for n in range(int(days) - 1, -1, -1)]


def iso_date(value):
    match = re.match(r"^(\d{4})[/-](\d{1,2})[/-](\d{1,2})(?:$|[T\s])", str(value or "").strip())
    if not match:
        return ""
    try:
        return date(*map(int, match.groups())).isoformat()
    except ValueError:
        return ""


def feed_identity(entry):
    raw = str(entry.get("summary", ""))
    text = BeautifulSoup(raw, "html.parser").get_text(" ", strip=True) if "<" in raw else unescape(raw)
    match = re.search(r"(?:https?://(?:dx\.)?doi\.org/|\[\s*DOI\s*\]\s*)(10\.\d{4,9}/[^\s<>]+)", text, re.I)
    if not match:
        return None
    doi = match.group(1).rstrip(".,;").lower()
    # Only the verified publisher's DOI prefixes are in this source adapter.
    if not doi.startswith(("10.1299/", "10.4325/", "10.20485/")):
        return None
    published = iso_date(entry.get("published", ""))  # NOT feed updated / indexed date
    return {"doi": doi, "url": "https://doi.org/" + doi, "feed_publication_date": published}


def parse_article(html, identity, allowed_dates, collected_date):
    soup = BeautifulSoup(html, "html.parser")
    def meta(name):
        node = soup.find("meta", attrs={"name": name})
        return str(node.get("content", "")).strip() if node else ""
    doi = meta("citation_doi").lower()
    if doi != identity["doi"]:
        return None
    title = meta("citation_title")
    abstract_node = soup.select_one("#article-overiew-abstract-wrap")
    if abstract_node is None:
        return None
    # Exclude headings/buttons without ever using the reference list or related articles.
    for node in abstract_node.select("h2, h3, h4, button, script, style"):
        node.decompose()
    abstract = abstract_node.get_text(" ", strip=True)
    abstract = re.sub(r"^(?:Abstract|抄録)\s*", "", abstract, flags=re.I)
    if len(abstract) < 80 or not title:
        return None
    publication = iso_date(meta("citation_publication_date"))
    online = iso_date(meta("citation_online_date"))
    # Preserve earliest verified availability. A new feed notification or issue
    # assignment must not make an old advance publication look new again.
    known_dates = [value for value in (publication, online) if value]
    if not known_dates:
        return None
    source_date = min(known_dates)
    if source_date not in allowed_dates:
        return None
    return {"国": "論文", "タイトル": title, "日付": source_date, "内容": abstract,
            "URL": identity["url"], "画像URL": "", "検索ワード": "論文RSS",
            "論文DOI": doi, "論文発行日": publication, "論文公開日": online,
            "論文取得日": collected_date, "論文要約根拠": "要旨に基づく要約"}


def collect_entries(entries, feed_name, issue_date, get, headers, days=30):
    """Network failures omit a paper, never stop valid daily news publication."""
    allowed = set(paper_window(issue_date, days))
    rows, seen, outcomes = [], set(), {}
    for entry in entries:
        identity = feed_identity(entry)
        if not identity or identity["doi"] in seen:
            continue
        seen.add(identity["doi"])
        if identity["feed_publication_date"] not in allowed:
            outcomes["outside_feed_window"] = outcomes.get("outside_feed_window", 0) + 1
            continue
        try:
            response = get(identity["url"], headers=headers, timeout=20)
            parsed = urlparse(response.url)
            if response.status_code != 200 or parsed.hostname != "www.jstage.jst.go.jp" or "/article/" not in parsed.path:
                raise ValueError("Paper DOI did not resolve to its publisher article")
            row = parse_article(response.content, identity, allowed, date.today().isoformat())
            if row:
                row.update({"出展サイト": feed_name, "ソース": feed_name})
                rows.append(row)
            else:
                outcomes["missing_abstract_or_old_publication"] = outcomes.get("missing_abstract_or_old_publication", 0) + 1
        except Exception as exc:
            outcomes["fetch_failed"] = outcomes.get("fetch_failed", 0) + 1
            print(f"  [PAPER_FETCH_FAILED] {feed_name}: {type(exc).__name__}")
    print(f"  [PAPER_RSS] {feed_name}: candidates={len(rows)}, omitted={outcomes}")
    return rows
