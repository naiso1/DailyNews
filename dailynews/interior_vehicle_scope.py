"""Passenger-cabin scope gate, independent of scores and country quotas."""
import re
import unicodedata
from urllib.parse import unquote, urlsplit

from dailynews.editorial_policy import article_source

POLICY_VERSION = "interior-motorcycle-scope-v1"

_BIKE = (r"二輪(?:車)?|オートバイ|モーターサイクル|原付|スクーター|バイク|摩托车|摩托車|"
         r"ライディング(?:用品|ブーツ|グローブ|ウェア|ジャケット)|\briding (?:boots|gloves|gear|jackets?)\b|"
         r"\b(?:motorcycles?|motorbikes?|scooters?|two[ -]wheelers?|superbikes?)\b|"
         r"\b(?:sport|sports|touring|adventure|electric|dirt) bikes?\b|"
         r"Royal Enfield|ロイヤルエンフィールド|Harley[ -]Davidson|ハーレーダビッドソン|"
         r"\b(?:Ducati|Aprilia)\b|ドゥカティ|アプリリア|"
         r"(?:Bajaj|バジャジ).{0,15}(?:Pulsar|パルサー|パルス)|"
         r"(?<![A-Za-z0-9])(?:Pulsar NS\d+|YZF[ -]?R\d[A-Za-z0-9]*|GSX[ -]?S\d+[A-Za-z0-9+]*|TVS Ronin|Jawa 42)(?![A-Za-z0-9])")
_BIKE_PATH = r"(?:^|/)(?:bike-news|bike-reviews|motorcycles?|motorbikes?|scooters?)(?:/|$)|(?:^|[-/])(?:motorcycles?|motorbikes?|superbikes?)(?:[-/]|$)"
_CABIN = (r"乗用車|四輪車|自動車内装|車室内|車内|ドアトリム|センターコンソール|"
          r"\b(?:passenger cars?|car cabin|automotive interiors?|door trim|center console)\b")
_FEATURE = (r"センサ|表皮|触覚|加飾|成形|低VOC|通気構造|静電容量|"
            r"\b(?:sensors?|capacitive|haptic|upholstery|low.VOC|in.mold)\b")
_APPLIED = r"採用|開発|組み込|統合|内蔵|転用|応用|共用|\b(?:adapted|transferred|integrated|developed|incorporated|adopted)\b"
_HYPOTHETICAL = r"可能性|応用でき|転用でき|検討でき|期待でき|\b(?:could|might|potential|would)\b"


def _has(pattern, text):
    return bool(re.search(pattern, text, re.I))


def _clean(text):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(text or ""))).strip()


def _source_body(body):
    # Related-link/navigation text is not evidence of the article's subject.
    return re.split(r"関連記事|あわせて読みたい|\b(?:Related (?:articles|stories)|Other news|Read also|Also read)\b",
                    body, maxsplit=1, flags=re.I)[0]


def _car_storage(source):
    return _has(r"(?:SUV|ミニバン|乗用車|四輪車).{0,45}(?:収納|積載|荷室)|"
                r"(?:収納|積載|荷室).{0,35}(?:SUV|ミニバン|乗用車)|"
                r"\b(?:car|SUV|minivan).{0,40}(?:bike rack|bicycle storage|cargo storage)", source)


def _explicit_cabin_application(source):
    # All evidence must occur together in an original sentence. A generated
    # suggestion, distant page keyword or a display/seat alone cannot exempt a bike.
    for sentence in re.split(r"[。!?！？]|(?<=[a-zA-Z])\.\s+", source):
        if (_has(_CABIN, sentence) and _has(_FEATURE, sentence)
                and _has(_APPLIED, sentence) and not _has(_HYPOTHETICAL, sentence)):
            return True
    return False


def motorcycle_exclusion(article, rules=()):
    """Return an exclusion reason, or empty text for a scope-only pass.

    This is not an adoption decision and does not require/rewrite other evidence.
    It applies to new interior candidates, including resumed CSV and quota fill.
    """
    for rule in rules or ():
        if (isinstance(rule, dict) and rule.get("key") == "exclude_non_passenger_vehicles"
                and rule.get("review_status") == "approved" and rule.get("version") == 1
                and rule.get("enabled") is False):
            return ""
    title, body = article_source(article)
    body = _source_body(body)
    source = f"{title}。{body}"
    heading = _clean(f"{title} {article.get('title', '')}")
    try:
        path = unquote(urlsplit(str(article.get("url", ""))).path)
    except ValueError:
        path = ""
    headline_bike = _has(_BIKE, heading)
    section_bike = _has(_BIKE_PATH, path)
    # A generic headline can omit vehicle class; use the article lead as well.
    # A cabin-focused original headline is not overturned by a passing mention.
    lead = body or _clean(article.get("desc", ""))
    lead_bike = _has(_BIKE, lead[:700]) and not _has(_CABIN, title)
    if not (headline_bike or section_bike or lead_bike):
        return ""
    if _car_storage(source) or _explicit_cabin_application(source):
        return ""
    return "motorcycle_primary_heading" if headline_bike else "motorcycle_section_url" if section_bike else "motorcycle_primary_lead"
