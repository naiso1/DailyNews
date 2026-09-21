"""Conservative, offline article identity checks shared by collection/publication.

This deliberately does not equate a vehicle name or text similarity with a news
story. Unknown events, different reviews and material follow-up information stay
separate. ``duplicate_of`` in the audit decisions is the representative URL.
"""

from copy import deepcopy
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from functools import lru_cache
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


_TRACKING_KEYS = frozenset({
    "fbclid", "gclid", "dclid", "msclkid", "igshid", "mc_cid", "mc_eid",
    "_ga", "_gl", "vero_id", "oly_anon_id", "oly_enc_id",
})
_RSS_PARAMS = {"source", "src", "from", "ref"}


def normalize_article_url(url):
    """Remove known tracking only; retain article IDs, page and unknown queries.

    No network access, redirect guessing, www removal, scheme upgrade or path
    rewriting. Query order, duplicate parameters and fragments remain significant.
    """
    value = str(url or "").strip()
    if not value:
        return ""
    try:
        parts = urlsplit(value)
        if parts.scheme.lower() not in {"http", "https"} or not parts.netloc:
            return value
        query = []
        for key, val in parse_qsl(parts.query, keep_blank_values=True):
            name = key.casefold()
            if name.startswith("utm_") or name in _TRACKING_KEYS:
                continue
            if name in _RSS_PARAMS and val.casefold() in {"rss", "rssfeed", "rss_feed"}:
                continue
            query.append((key, val))
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path,
                           urlencode(query), parts.fragment))
    except (ValueError, UnicodeError):
        return value


def _day(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value or "").strip()[:10])
    except ValueError:
        return None


def recent_title_history(rows, limit=500):
    """Return latest original titles, accepting article or Japanese CSV rows.

    Equal dates retain input order. Undated rows follow dated rows. Exact repeated
    titles do not use another history slot. The input rows are never modified.
    """
    if limit <= 0:
        return []
    ranked = sorted(rows, key=lambda r: _day(r.get("date") or r.get("日付")) or date.min,
                    reverse=True)
    result, seen = [], set()
    for row in ranked:
        title = str(row.get("originalTitle") or row.get("タイトル") or row.get("title") or "").strip()
        if title and title not in seen:
            result.append(title)
            seen.add(title)
            if len(result) >= limit:
                break
    return result


def _text(value):
    value = unicodedata.normalize("NFKC", str(value or "")).casefold()
    value = re.sub(r"[‐‑‒–—−]", "-", value)
    return re.sub(r"\s+", " ", value).strip()


_BRANDS = {
    "nissan": ("nissan", "日産"), "renault": ("renault", "ルノー"),
    "daihatsu": ("daihatsu", "ダイハツ"), "subaru": ("subaru", "スバル"),
    "xpeng": ("xpeng", "x-peng", "小鵬", "小鹏", "シャオペン"),
    "toyota": ("toyota", "トヨタ"), "lexus": ("lexus", "レクサス"),
    "honda": ("honda", "ホンダ"), "mazda": ("mazda", "マツダ"),
    "suzuki": ("suzuki", "スズキ"), "bmw": ("bmw",),
    "mercedes": ("mercedes", "メルセデス"), "volvo": ("volvo", "ボルボ"),
    "volkswagen": ("volkswagen", "フォルクスワーゲン"),
    "hyundai": ("hyundai", "ヒョンデ"), "kia": ("kia", "起亜"),
    "ford": ("ford", "フォード"), "gm": ("general motors", "gm"),
    "tesla": ("tesla", "テスラ"), "byd": ("byd",),
    "mg": ("mg",), "bride": ("bride", "ブリッド"),
    "tata": ("tata", "タタ"), "mahindra": ("mahindra", "マヒンドラ"),
}
_MODEL_STOP = set("""new car cars auto automotive motor motors electric hybrid phev bev ev suv
    review drive test reasons buy not and the for with from first world global international
    launch launched revealed reveal release production investment announced announces confirmed
    design future chief family market show paris japan china india europe uk us america europe
    e-power epower ai led hmi adas tops nugrain iii ii iv concept volvo nissan renault xpeng mg
    toyota lexus bmw bride daihatsu subaru tata ford honda mazda suzuki byd tesla
    インド 中国 日本 米国 欧州 英国 パリ モーターショー オートショー リコール シート シートカバー
    コンセプト コンセプトカー デザイン ブランド プロポーション ニュース モデル シリーズ
    ハイブリッド システム グローバル バケットシート スーパーセミバケットシート
    ソフトタッチ カーボン シェル ヌグレ センターコンソール ディスプレイ インチ
    """.split())
_NAMED_MODELS = {
    "kicks": ("kicks", "キックス"), "move": ("move", "ムーヴ", "ムーブ"),
    "stella": ("stella", "ステラ"), "rafale": ("rafale", "ラファール"),
    "scenic": ("scenic", "シエニック", "セニック"),
    "gias": ("gias",), "stradia": ("stradia",),
    "hector": ("hector", "ヘクター"), "tomahawk": ("tomahawk", "トマホーク"),
    "qashqai": ("qashqai", "キャシュカイ"), "juke": ("juke", "ジューク"),
    "corolla": ("corolla", "カローラ"), "prius": ("prius", "プリウス"),
    "serena": ("serena", "セレナ"), "leaf": ("leaf", "リーフ"),
    "civic": ("civic", "シビック"), "accord": ("accord", "アコード"),
}
_REGIONS = {
    "uk": ("英国", "イギリス", "uk", "united kingdom", "britain"),
    "eu": ("欧州", "ヨーロッパ", "europe", "european"),
    "jp": ("日本", "japan", "japanese"),
    "cn": ("中国", "china", "chinese"),
    "in": ("インド", "india", "indian"),
    "us": ("米国", "アメリカ", "united states", "usa", "us"),
}
_SHOWS = {
    "paris_motor_show": r"パリ(?:モーター|オート)ショー|paris (?:motor|auto) show",
    "munich_iaa": r"iaa mobility|ミュンヘン(?:モーター|オート)ショー",
    "tokyo_mobility": r"ジャパンモビリティショー|japan mobility show",
}
_FACTORIES = {
    "sunderland": r"sunderland|サンダーランド|サドルランド|サندرランド",
    "graz": r"graz|グラーツ",
}
_DEFECTS = {
    "flammability": r"燃焼|難燃|flammability|flame.resistan|fire.resistan",
    "airbag": r"エアバッグ|airbag|air bag",
    "brake": r"ブレーキ|brak(?:e|ing)",
    "steering": r"ステアリング|操舵|steering",
    "seatbelt": r"シートベルト|seat.?belt",
}
_REVIEW = re.compile(r"レビュー|試乗|乗り比べ|購入判断|\breview\b|\btest.drive\b|reasons (?:not )?to buy")
_FOLLOWUP = re.compile(
    r"値上げ|値下げ|価格|料金|受注|予約|納車|販売開始|仕様変更|新仕様|追加装備|改良|アップデート|"
    r"規制|条件|警告|延期|中止|\bpric(?:e|es|ing)\b|\borders?\b|\bdeliver(?:y|ies)\b|"
    r"\bupdate[ds]?\b|\bnew specs?\b|\bregulat\w*|\bconditions?\b|\bwarn\w*|\bdelay\w*"
)
_POLICY = re.compile(r"zev|規制緩和|条件|限り|見送|警告|unless|provided that|\bwarn\w*")
_NUM = r"\d[\d,]*(?:\.\d+)?(?:(?:億|千万|百万|万|千|百)\d[\d,]*(?:\.\d+)?)*(?:億|千万|百万|万|千|百)?"
_EN_NUM = r"\d[\d,]*(?:\.\d+)?(?:\s*(?:billion|million|bn|m))?"


def _contains(text, alias):
    if alias.isascii():
        return bool(re.search(r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])", text))
    return alias in text


def _number(value):
    value = value.replace(",", "").replace(" ", "")
    units = {"億": 100000000, "千万": 10000000, "百万": 1000000, "万": 10000,
             "千": 1000, "百": 100, "billion": 1000000000, "million": 1000000,
             "bn": 1000000000, "m": 1000000, "": 1}
    try:
        return sum(Decimal(n) * units[u] for n, u in re.findall(
            r"(\d+(?:\.\d+)?)(billion|million|千万|百万|億|万|千|百|bn|m)?", value))
    except (InvalidOperation, KeyError):
        return None


def _money(text):
    result = set()
    for currency, patterns in {
        "gbp": (rf"({_NUM})\s*(?:ポンド)", rf"(?:£|gbp\s*)({_EN_NUM})", rf"({_EN_NUM})\s*(?:pounds|gbp)\b"),
        "usd": (rf"({_NUM})\s*(?:米ドル)", rf"(?:us\$|usd\s*)({_EN_NUM})", rf"({_EN_NUM})\s*(?:us dollars|usd)\b"),
        "eur": (rf"({_NUM})\s*(?:ユーロ)", rf"(?:€|eur\s*)({_EN_NUM})"),
        "jpy": (rf"({_NUM})\s*円",),
    }.items():
        for pattern in patterns:
            for match in re.finditer(pattern, text):
                number = _number(match.group(1))
                if number is not None:
                    result.add((currency, number))
    return frozenset(result)


def _market_targets(text):
    targets = set()
    for key, aliases in _REGIONS.items():
        for alias in aliases:
            if alias.isascii():
                pattern = r"\b(?:in|for|to)\s+(?:the\s+)?" + re.escape(alias) + r"\b"
            else:
                pattern = re.escape(alias) + r"(?:[・／/](?:英国|欧州|日本|中国|米国|インド))*(?:市場|向け|仕様|導入|投入|発売|販売|展開|進出|へ)"
            if re.search(pattern, text):
                targets.add(key)
    return frozenset(targets)


def _models(text):
    # Plain shared vocabulary ("design", "seat", "launch", materials etc.) is
    # not product identity. Unknown named models fail open until an explicit
    # alias is added; alphanumeric model codes can be recognised without a list.
    names = {key for key, aliases in _NAMED_MODELS.items() if any(_contains(text, a) for a in aliases)}
    codes = re.findall(r"(?<![a-z0-9])[a-z][a-z0-9-]*\d[a-z0-9-]*(?![a-z0-9])", text)
    return frozenset(names | {code for code in codes if code not in _MODEL_STOP})


def _event_dates(text):
    result = {(int(m), int(d)) for m, d in re.findall(r"(?<!\d)(\d{1,2})月(\d{1,2})日", text)
              if 1 <= int(m) <= 12 and 1 <= int(d) <= 31}
    months = "january february march april may june july august september october november december".split()
    for index, month in enumerate(months, 1):
        for day in re.findall(r"\b" + month + r"\s+(\d{1,2})(?:st|nd|rd|th)?\b", text):
            if 1 <= int(day) <= 31:
                result.add((index, int(day)))
    return frozenset(result)


def _money_agrees(a, b):
    currencies = {currency for currency, _ in a} & {currency for currency, _ in b}
    return bool(currencies) and all(
        {amount for currency, amount in a if currency == key} ==
        {amount for currency, amount in b if currency == key}
        for key in currencies
    )


@lru_cache(maxsize=4096)
def _profile(title, body):
    text = title + " " + body
    brands = frozenset(key for key, aliases in _BRANDS.items() if any(_contains(text, a) for a in aliases))
    return {
        "brands": brands, "models": _models(title), "all_models": _models(text),
        "markets": _market_targets(text), "money": _money(text),
        "dates": _event_dates(text),
        "shows": frozenset(key for key, pattern in _SHOWS.items() if re.search(pattern, text)),
        "factories": frozenset(key for key, pattern in _FACTORIES.items() if re.search(pattern, text)),
        "defects": frozenset(key for key, pattern in _DEFECTS.items() if re.search(pattern, text)),
        # The headline may round 10,091 vehicles to "10,000". Do not let that
        # approximate title number hide conflicting exact counts in the body.
        "counts": frozenset(_number(m.group(1)) for m in re.finditer(rf"({_NUM})\s*(?:台|vehicles?\b|cars?\b)", body)),
        "recall": bool(re.search(r"リコール|\brecall\w*", text)),
        "recall_focus": bool(re.search(r"リコール|\brecall\w*", title)),
        "show_focus": bool(any(re.search(pattern, title) for pattern in _SHOWS.values()) or
                           re.search(r"世界初公開|国際展開|グローバル展開|\b(?:global|international|world) (?:launch|debut|premiere)", title)),
        "production_focus": bool(re.search(r"生産|量産|工場|投資|\bproduction\b|\bmanufactur\w*|\bfactor(?:y|ies)\b|\bplant\b|\binvest\w*", title)),
        "production": bool(re.search(r"生産|量産|\bproduction\b|\bmanufactur\w*|\bbuilt\b", text)),
        "investment": bool(re.search(r"投資|\binvest\w*", text)),
        "review": bool(_REVIEW.search(title)), "followup": bool(_FOLLOWUP.search(title)),
        "policy": bool(_POLICY.search(text)),
    }


def _article_text(article):
    title = _text(str(article.get("title") or "") + " " + str(article.get("originalTitle") or ""))
    body = _text(str(article.get("desc") or "") + " " + str(article.get("originalDesc") or ""))
    return title, body


def _url_set(article):
    related = article.get("relatedUrls", [])
    if not isinstance(related, (list, tuple)):
        related = []
    return {value for value in (normalize_article_url(u) for u in [article.get("url"), *related]) if value}


def _gallery_pair(url_a, url_b):
    """Explicit same-publisher gallery slug matching, not adjacent numeric IDs."""
    try:
        a, b = urlsplit(url_a), urlsplit(url_b)
        if not a.hostname or a.hostname.lower().removeprefix("www.") != (b.hostname or "").lower().removeprefix("www."):
            return False
        if a.query != b.query:
            return False
        for gallery, article in ((a, b), (b, a)):
            slug = gallery.path.rstrip("/").split("/")[-1]
            base = re.sub(r"-(?:pictures|photos|photo-gallery|gallery)(?:\.html)?$", "", slug)
            if base == slug or len(base.split("-")) < 3:
                continue
            other = article.path.rstrip("/").split("/")[-1]
            if other == base or other.startswith(base + "-"):
                return True
    except ValueError:
        pass
    return False


def same_story(a, b):
    """Return an evidence-specific reason, or '' when identity is uncertain."""
    urls_a, urls_b = _url_set(a), _url_set(b)
    if urls_a & urls_b:
        return "same_url"
    url_a, url_b = normalize_article_url(a.get("url")), normalize_article_url(b.get("url"))
    try:
        ua, ub = urlsplit(url_a), urlsplit(url_b)
        # Distinct IDs/page parameters on one endpoint are not URL aliases.
        if ua.netloc and (ua.netloc, ua.path) == (ub.netloc, ub.path) and ua.query != ub.query:
            return ""
    except ValueError:
        return ""
    day_a, day_b = _day(a.get("date")), _day(b.get("date"))
    if not day_a or not day_b or abs((day_a - day_b).days) > 7:
        return ""
    title_a, body_a = _article_text(a)
    title_b, body_b = _article_text(b)
    if not title_a or not title_b:
        return ""
    # Verbatim long copy is stronger evidence than a model dictionary or genre:
    # syndicated reviews and unfamiliar companies are still the same article.
    # Date and meaningful endpoint/query checks above remain in force.
    if title_a == title_b and body_a == body_b and len(body_a) >= 80:
        return "identical_article_copy"
    pa, pb = _profile(title_a, body_a), _profile(title_b, body_b)
    if pa["markets"] and pb["markets"] and not pa["markets"] & pb["markets"]:
        return ""
    if pa["policy"] != pb["policy"]:
        return ""
    if _gallery_pair(url_a, url_b) and abs((day_a - day_b).days) <= 3:
        if pa["brands"] & pb["brands"] and len(pa["all_models"] & pb["all_models"]) >= 2:
            return "article_picture_gallery"
    if pa["review"] or pb["review"] or pa["followup"] or pb["followup"]:
        return ""
    common_brands = pa["brands"] & pb["brands"]
    common_models = pa["models"] & pb["models"]
    if not common_brands or not common_models:
        return ""
    if pa["recall"] and pb["recall"]:
        if (pa["recall_focus"] and pb["recall_focus"] and pa["counts"] and
                pa["counts"] == pb["counts"] and pa["defects"] & pb["defects"]):
            return "same_recall_model_count_defect"
        return ""
    # A headline introducing another model alongside the existing one may be a
    # new announcement. Common background information must not swallow it.
    if pa["models"] != pb["models"]:
        return ""
    if abs((day_a - day_b).days) > 3:
        return ""
    if (pa["show_focus"] and pb["show_focus"] and pa["shows"] & pb["shows"] and
            pa["dates"] and pa["dates"] == pb["dates"]):
        return "same_model_show_and_event_date"
    if pa["production_focus"] and pb["production_focus"] and pa["production"] and pb["production"] and pa["investment"] and pb["investment"]:
        if pa["factories"] and pb["factories"] and not pa["factories"] & pb["factories"]:
            return ""
        if _money_agrees(pa["money"], pb["money"]) and (pa["factories"] & pb["factories"] or pa["markets"] & pb["markets"]):
            return "same_model_production_investment"
    return ""


def _append_related_urls(representative, item):
    related = representative.get("relatedUrls", [])
    related = list(related) if isinstance(related, (list, tuple)) else []
    seen = _url_set(representative)
    extra = item.get("relatedUrls", [])
    extra = list(extra) if isinstance(extra, (list, tuple)) else []
    for alternate in [item.get("url"), *extra]:
        normalized = normalize_article_url(alternate)
        if normalized and normalized not in seen:
            related.append(str(alternate))
            seen.add(normalized)
    if related:
        representative["relatedUrls"] = related


def deduplicate_articles(candidates, history=(), *, issue_date=None, history_days=14, protected_urls=()):
    """Choose stable representatives without mutating inputs.

    Caller order is preference order. Protected candidates take precedence;
    those with distinct URLs are never removed against one another. Repeated rows with
    the same normalized primary URL are still consolidated. Nonprotected
    duplicates can attach to them. Representatives retain original order.
    Only batch duplicates contribute relatedUrls; historical items are not edited.
    Without issue_date, the latest valid candidate date defines the history window.
    Undated history, future history and history outside the inclusive window are
    ignored. With no usable issue date, historical suppression is disabled.
    """
    if history_days < 0:
        raise ValueError("history_days must be nonnegative")
    candidates = list(candidates)
    if issue_date is not None and not _day(issue_date):
        raise ValueError("issue_date must be an ISO date")
    issue = _day(issue_date) or max((_day(a.get("date")) for a in candidates if _day(a.get("date"))), default=None)
    protected = {normalize_article_url(u) for u in protected_urls if u}
    history_rows = [h for h in history if issue and _day(h.get("date")) and
                    issue - timedelta(days=history_days) <= _day(h.get("date")) <= issue]
    history_rows.sort(key=lambda h: _day(h.get("date")), reverse=True)
    ordered = sorted(enumerate(candidates), key=lambda pair: normalize_article_url(pair[1].get("url")) not in protected)
    kept, decisions = [], []
    for index, article in ordered:
        item = deepcopy(article)
        url = str(item.get("url") or "")
        is_protected = bool(normalize_article_url(url) in protected)
        if is_protected:
            prior = next((rep for _, rep in kept if normalize_article_url(rep.get("url")) == normalize_article_url(url)), None)
            if prior is not None:
                _append_related_urls(prior, item)
                decisions.append({"url": url, "duplicate_of": prior.get("url", ""),
                                  "reason": "same_url", "kind": "batch"})
            else:
                kept.append((index, item))
            continue
        duplicate = False
        for _, representative in kept:
            reason = same_story(item, representative)
            if not reason:
                continue
            _append_related_urls(representative, item)
            decisions.append({"url": url, "duplicate_of": representative.get("url", ""),
                              "reason": reason, "kind": "batch"})
            duplicate = True
            break
        if duplicate:
            continue
        for historical in history_rows:
            reason = same_story(item, historical)
            if reason:
                decisions.append({"url": url, "duplicate_of": historical.get("url", ""),
                                  "reason": reason, "kind": "history"})
                duplicate = True
                break
        if not duplicate:
            kept.append((index, item))
    kept.sort(key=lambda pair: pair[0])
    return [item for _, item in kept], decisions
