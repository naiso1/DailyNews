"""Verified, bounded source-text links. No LLM, browser or image downloads."""

from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import urljoin, urlparse
from urllib.request import getproxies

from bs4 import BeautifulSoup
import requests

try:
    from .summary_grounding import BRAND_ALIASES, INTERIOR_TOPICS
except ImportError:
    from summary_grounding import BRAND_ALIASES, INTERIOR_TOPICS

VERSION = 3
CACHE_PATH = Path(__file__).with_name("source_highlights.json")
MAX_BYTES = 3 * 1024 * 1024
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
FIELDS = ("sourceExcerpt", "sourceExcerptEnd")
TOPICS = tuple(re.compile(p.pattern + "|" + cn, re.I) for p, cn in zip(INTERIOR_TOPICS, (
    "中控台|中央扶手|中央控制台", "显示屏|屏幕|中控屏", "座椅|座席", "冰箱|储物|行李厢", "门板|饰板|真皮", "氛围灯|环境照明",
))) + tuple(re.compile(p, re.I) for p in (
    r"内装|内饰|座舱|\b(?:interior|cabin|cockpit)\b",
    r"ステアリング|ハンドル|方向盘|\bsteering\b",
    r"触感|触覚|振動|\b(?:haptic|tactile)\b",
    r"ボタン|スイッチ|物理操作|按钮|按键|\b(?:buttons?|switches?|controls?)\b",
    r"HUD|ヘッドアップ|抬头显示|head.up|windshield",
    r"充電|充电|\bcharg(?:e|es|ed|ing|ers?)\b",
    r"電池|バッテリー|电池|\bbatter(?:y|ies)\b",
    r"航続|续航|\brange\b",
    r"手仕事|工芸|職人|craft|artisan|gestures?|\bhands?\b",
    r"絹|シルク|silk|織物|textile|fabric|upholstery|面料",
    r"照明|灯籠|灯具|lighting|lantern|LED",
    r"安全|エアバッグ|衝突|安全气囊|\b(?:safety|airbags?|crash)\b",
    r"半導体|チップ|semiconductor|\bchips?\b|芯片",
    r"工場|生産|投資|factory|production|invest|工厂|生产",
    r"価格|万円|万元|ルピー|\b(?:price|cost|pricing|lakh)\b",
    r"(?<![a-z])AI(?![a-z])|人工知能|人工智能|artificial intelligence",
    r"素材|質感|materials?|finish|材质",
    r"ダッシュボード|インパネ|\bdashboard\b|仪表台",
    r"高級|ラグジュアリー|luxury|premium|豪华",
))
BODY_SELECTORS = (
    "[itemprop='articleBody']", ".field-name-body", ".caas-body",
    ".article_body", ".article-body", ".articleBody", "[class*='articleBody']",
    ".entry-content", ".td-post-content", ".post-content", ".article__body",
    ".article-content", ".article_content", ".article-text", ".article_text",
    ".read__content", ".content-body", ".article__text", ".content-main-detail", ".left_zw",
)
NOISE = re.compile(r"^(?:関連記事|おすすめの記事|続きを読む|会員登録|ログイン|この記事を|写真を|画像を|広告|著者|Comments?|Read more|Related|Subscribe|Sign in|Advertisement|Share this|Follow us|Copyright)\b", re.I)
STOP_WORDS = set("the and for with from that this have more will new car cars auto news suv ev what copy can electric edition max pro ai".split())


def plain(text):
    # Do not NFKC-normalize, translate or rewrite punctuation in an exact quote.
    return re.sub(r"\s+", " ", str(text or "")).strip()


def public_url(url):
    parsed = urlparse(str(url or ""))
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
        return False
    if "." not in host or host.endswith((".local", ".localhost", ".internal")):
        return False
    try:
        return ipaddress.ip_address(host).is_global
    except ValueError:
        return bool(re.fullmatch(r"[a-z0-9.-]+", host))


def make_session(windows_proxy=False):
    session = requests.Session()
    session.trust_env = False
    proxies = getproxies()
    if windows_proxy:
        from urllib.request import getproxies_registry
        proxies = getproxies_registry()
    session.proxies = {k: v for k, v in proxies.items() if k in {"http", "https"}}
    session.headers["User-Agent"] = USER_AGENT
    return session


def fetch_html(session, url):
    start = time.monotonic()
    for _ in range(4):
        if not public_url(url):
            raise ValueError("not a public HTTP(S) article URL")
        with session.get(url, timeout=(5, 8), stream=True, allow_redirects=False) as response:
            if response.status_code in {301, 302, 303, 307, 308}:
                url = urljoin(url, response.headers.get("Location", ""))
                continue
            response.raise_for_status()
            if "html" not in response.headers.get("Content-Type", "").lower():
                raise ValueError("not HTML")
            chunks, size = [], 0
            for chunk in response.iter_content(65536):
                size += len(chunk)
                if size > MAX_BYTES or time.monotonic() - start > 20:
                    raise ValueError("article fetch size/time limit")
                chunks.append(chunk)
            # Decode using the document declaration, not requests' ISO-8859-1 default.
            return b"".join(chunks), url
    raise ValueError("too many redirects")


def article_paragraphs(html):
    soup = BeautifulSoup(html, "html.parser")
    for node in soup.select("script, style, noscript, nav, footer, header, aside, form, button, [hidden], [aria-hidden='true']"):
        node.decompose()
    for node in soup.select("[style]"):
        if node.attrs is not None and re.search(r"display\s*:\s*none|visibility\s*:\s*hidden", node.get("style", ""), re.I):
            node.decompose()
    roots = soup.select(",".join(BODY_SELECTORS))
    if not roots:
        roots = soup.select("article, main")
    if not roots:
        return []  # Menus, RSS descriptions and hidden JSON are not article evidence.
    root = max(roots, key=lambda n: len(n.get_text(" ", strip=True)))
    for node in root.select("[class*='related'], [class*='comment'], [id*='comment'], [class*='recommend'], [class*='newsletter']"):
        node.decompose()
    nodes = root.select("p, li, blockquote")
    if not nodes:
        nodes = [root]
    paragraphs, seen = [], set()
    for node in nodes:
        raw = node.get_text("", strip=False)
        linked = sum(len(a.get_text()) for a in node.select("a"))
        if linked > len(raw) * .7:
            continue
        for part in re.split(r"\n\s*\n", raw):
            text = plain(part)
            if len(text) < 25 or NOISE.search(text) or text in seen:
                continue
            seen.add(text)
            paragraphs.append(text)
    return paragraphs[:180]


def fingerprint(item):
    value = json.dumps([VERSION, item.get("url"), item.get("title"), item.get("desc")], ensure_ascii=False)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def choose_excerpt(item, paragraphs):
    """Find a short, literal source passage with shared topics/names; not a translation."""
    summary = plain(f"{item.get('title', '')} {item.get('desc', '')}")
    folded = summary.casefold()
    # Prefer specific cabin/HMI/material evidence over generic price and range facts.
    topics = [(p, 7 if n < 11 or n in {22, 23} else 4) for n, p in enumerate(TOPICS) if p.search(summary)]
    terms = {w.casefold() for w in re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}", summary) if w.casefold() not in STOP_WORDS}
    for brand, aliases in BRAND_ALIASES.items():
        if brand in folded or any(a in summary for a in aliases):
            terms.add(brand)
    cjk = {s[i:i+3] for s in re.findall(r"[\u3041-\u30fa\u4e00-\u9fff]{3,}", summary) for i in range(len(s)-2)}
    best = None
    for index, paragraph in enumerate(paragraphs):
        # Keep sentences within the same visible paragraph, never across DOM blocks.
        sentences = re.split(r"(?<=[。！？])|(?<=[.!?])\s+(?=[A-Z\u201c\u2018])", paragraph)
        for sentence in sentences:
            sentence = sentence.strip()
            if not 25 <= len(sentence) <= 1800:
                continue
            lower = sentence.casefold()
            topic_hits = sum(bool(p.search(sentence)) for p, _ in topics)
            topic_score = sum(weight for p, weight in topics if p.search(sentence))
            term_hits = sum(bool(re.search(r"(?<![a-z0-9])" + re.escape(t) + r"(?![a-z0-9])", lower)) for t in terms)
            cjk_hits = sum(t in sentence for t in cjk)
            if topic_hits < 1 and term_hits < 1 and cjk_hits < 3:
                continue
            score = topic_score + min(term_hits, 4) * 2 + min(cjk_hits, 8) + 1 / (1 + index)
            if best is None or score > best[0]:
                best = (score, sentence)
    if best is None:
        return {}
    sentence = best[1]
    # Bound stored quotation size; a start/end pair highlights the intervening text.
    words = list(re.finditer(r"\S+", sentence))
    if len(words) > 24:
        begin = sentence[:words[11].end()]
        end = sentence[words[-10].start():]
    elif len(sentence) > 160:
        begin, end = sentence[:70], sentence[-60:]
    else:
        begin, end = sentence, ""
    result = {"sourceExcerpt": begin}
    if end:
        result["sourceExcerptEnd"] = end
    # A text directive targets the first occurrence. Ambiguous anchors are omitted.
    all_text = "\n".join(paragraphs)
    if all_text.casefold().count(begin.casefold()) != 1:
        return {}
    return result


def read_cache(path=CACHE_PATH):
    if not Path(path).exists():
        return {}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Invalid source highlight cache")
    return data


def write_cache(cache, path=CACHE_PATH):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def enrich_items(items, *, session=None, cache_path=CACHE_PATH, refresh=False, log=print):
    """Best effort: never block news publication or drop articles on a fetch failure."""
    try:
        cache = read_cache(cache_path)
    except (ValueError, OSError):
        log("[HIGHLIGHT] cache unreadable; checking sources again")
        cache = {}
    owned = session is None
    session = session or make_session()
    report = []
    try:
        for item in items:
            if item.get("sourceExcerpt"):
                report.append({"id": item.get("id"), "status": "already_configured"})
                continue
            url, key = item.get("url", ""), fingerprint(item)
            cached = cache.get(url, {})
            if not isinstance(cached, dict):
                cached = {}
            cache_valid = isinstance(cached.get("sourceExcerpt"), str) and bool(cached["sourceExcerpt"])
            if not refresh and cache_valid and cached.get("fingerprint") == key and cached.get("status") == "verified":
                item.update({f: cached[f] for f in FIELDS if cached.get(f)})
                report.append({"id": item.get("id"), "url": url, "status": "cached"})
                continue
            record = {"fingerprint": key, "checkedAt": datetime.now(timezone.utc).isoformat(), "method": f"literal-topic-match-v{VERSION}"}
            try:
                html, final_url = fetch_html(session, url)
                paragraphs = article_paragraphs(html)
                quote = choose_excerpt(item, paragraphs)
                record.update(status="verified" if quote else "no_matching_passage", finalUrl=final_url, **quote)
                item.update(quote)
            except Exception as exc:
                # This optional annotation must not abort a successfully generated edition.
                record.update(status="fetch_failed", error=type(exc).__name__)
            cache[url] = record
            report.append({"id": item.get("id"), "url": url, **record})
            log(f"[HIGHLIGHT] {item.get('id') or url}: {record['status']}")
    finally:
        try:
            write_cache(cache, cache_path)
        except OSError:
            log("[HIGHLIGHT] could not save cache; verified links remain usable")
        if owned:
            session.close()
    return report
