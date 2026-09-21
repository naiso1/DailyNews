"""Deterministic interior editorial gates; no I/O, models or free-text rules."""
import re
import unicodedata

POLICY_VERSION = "interior-development-value-v1"
EVIDENCE_COLUMNS = {
    "target_component": "採用根拠_対象部品",
    "new_information": "採用根拠_新情報",
    "development_reference": "採用根拠_開発参考",
    "source_quote": "採用根拠_出典",
}
PUBLISHED_EVIDENCE_FIELDS = {
    "target_component": "selectionTargetComponent", "new_information": "selectionNewInformation",
    "development_reference": "selectionDevelopmentReference", "source_quote": "selectionSourceQuote",
}
PRESET_KEYS = frozenset({"exclude_non_passenger_vehicles", "exclude_off_topic",
                         "seat_requires_transferable_value", "interior_lighting_only",
                         "require_development_value"})


def exterior_scope_rules(rules=()):
    """Exterior retains its own baseline; only approved shared scope switches apply."""
    configured = {key: {"key": key, "enabled": False, "review_status": "approved", "version": 1}
                  for key in PRESET_KEYS}
    for rule in rules or ():
        if (isinstance(rule, dict) and rule.get("key") in {"exclude_non_passenger_vehicles", "exclude_off_topic"}
                and rule.get("review_status") == "approved" and rule.get("version") == 1
                and isinstance(rule.get("enabled"), bool)):
            configured[rule["key"]] = dict(rule)
    return list(configured.values())


def _text(value):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(value or ""))).strip()


def _matches(pattern, text):
    return bool(re.search(pattern, text, re.I))


_INTERIOR_LIGHT = (r"室内灯|車内灯|ルームランプ|読書灯|フット(?:ランプ|ライト)|"
                   r"(?:車室内|車内|室内|インパネ|ドアトリム|コンソール)[^。.!?]{0,18}(?:照明|ライト|イルミ)|"
                   r"(?:interior|cabin|footwell|dashboard|door trim)[^。.!?]{0,24}(?:light|illumination)")
_EXTERIOR_LIGHT = (r"ヘッド(?:ライト|ランプ)|テール(?:ライト|ランプ)|前照灯|尾灯|デイタイム|"
                   r"(?:発光|照明|イルミネー[テト]ッド)[^。.!?]{0,12}(?:グリル|エンブレム)|"
                   r"(?:グリル|エンブレム|ボディー|外装)[^。.!?]{0,18}(?:発光|照明|ライト|イルミ)|"
                   r"\b(?:headlights?|headlamps?|taillights?|tail lamps?|DRL)\b|"
                   r"(?:illuminated|lighted)[^。.!?]{0,15}(?:grille|emblem)|exterior[^。.!?]{0,20}(?:light|illumination)")
_AMBIENT = r"アンビエント(?:ライト|照明|ライティング)|\bambient lighting\b"


def classify_lighting(title="", content=""):
    """Classify installation context; an unqualified 'lighting' is unknown."""
    text = _text(f"{title} {content}")
    interior = _matches(_INTERIOR_LIGHT, text)
    exterior = _matches(_EXTERIOR_LIGHT, text)
    # Ambient lighting is normally cabin terminology, except when the article
    # explicitly places that lighting outside the vehicle.
    if _matches(_AMBIENT, text) and not _matches(
            r"(?:外装|車外|exterior).{0,12}(?:アンビエント|ambient)", text):
        interior = True
    return "both" if interior and exterior else "interior" if interior else "exterior" if exterior else ""


_CABIN_PART = (r"ドアトリム|インパネ|ダッシュボード|センターコンソール|ステアリング|車室内|"
               r"自動車内装|内装材|表皮材|加飾|触覚|乗員検知|ドライバー監視|"
               r"\b(?:HMI|dashboard|door trim|center console|steering wheel|automotive interior|"
               r"cabin materials?|occupant sensing|driver monitoring)\b")
_TRANSFER_FEATURE = (r"NUGRAIN|ヌグレ|ヌバック|高触感表皮|インモールド|静電容量|圧力センサ|荷重センサ|"
                     r"乗員検知|生体センシング|触覚フィードバック|表皮一体|センサー内蔵|"
                     r"低VOC|バイオ由来|再生(?:樹脂|レザー|皮革)|透光(?:表皮|加飾)|体圧分布|熱伝導構造|通気構造|"
                     r"(?:合成皮革|表皮材).{0,45}(?:風合い|触感|防汚|耐摩耗|清掃|メンテナンス)|"
                     r"(?:防汚|耐摩耗|触感|清掃性).{0,35}(?:合成皮革|表皮材)|"
                     r"\b(?:capacitive|haptic feedback|occupant sensing|pressure sensor|low.VOC|"
                     r"recycled leather|bio.based|in.mold electronics|NUGRAIN)\b|"
                     r"(?:synthetic leather|upholstery material).{0,50}(?:texture|tactile|clean|durab|stain)")
_SEAT = r"シート|バケット|座席|\b(?:seat|seats|bucket)\b"
_SEAT_PRODUCT = r"BRIDE|ブリッド|NURMAN|ニュルマン|ZIEG|ジーグ|(?:シート|バケット|seat).{0,30}(?:発売|受注|launch|sale)"
_NON_SEAT_PART = r"ドアトリム|インパネ|センターコンソール|ステアリング|\b(?:HMI|dashboard|door trim|center console|steering wheel)\b"
_BIKE = (r"二輪車|オートバイ|モーターサイクル|原付|\b(?:motorcycles?|motorbikes?|scooters?)\b|"
         r"Royal Enfield|ロイヤルエンフィールド|Aprilia|アプリリア|\b(?:CB350RS|H.ness CB350|Jawa 42|TVS Ronin)\b")
_FINANCE = r"(?:車|自動車|car).{0,12}ローン|頭金なし|ローン.{0,12}(?:審査|手続)|\b(?:car loan|down.payment|loan eligibility|loan application)\b"
_SPACE = r"アポロ\s*\d+|サターン\s*V|宇宙船|ロケット.{0,18}(?:打ち上げ|飛行)|\b(?:Apollo\s*\d+|Saturn V|spacecraft|lunar mission)\b"
_TRAVEL = r"旅行記|観光ツアー|記念ロードトリップ|\d+日間ツアー|ノルウェー.{0,20}(?:旅行|ツアー)|\b(?:tour itinerary|exploring norway|norway our way)\b"
_GENERIC = (r"seat and display plus cabin image|具体的な新情報|対象部品|開発への参考|"
            r"(?:内装|製品|開発)(?:の|に)?(?:参考になる|役立つ|有用です|有用である)$|"
            r"^(?:useful|relevant|good|interior related|new features|specific new information|example|n/?a|unknown|none)$")


def article_source(article):
    """Original source text takes precedence over generated summaries."""
    # CSV adapters explicitly supply original fields, including empty values.
    # An absent source body must never be replaced by the generated summary.
    if "originalTitle" in article or "originalDesc" in article:
        return _text(article.get("originalTitle")), _text(article.get("originalDesc"))
    if "タイトル" in article or "内容" in article:
        return _text(article.get("タイトル")), _text(article.get("内容"))
    return _text(article.get("title")), _text(article.get("desc"))


def extract_evidence(article):
    supplied = article.get("evidence")
    supplied = supplied if isinstance(supplied, dict) else {}
    return {key: _text(supplied.get(key) or article.get(column) or article.get(PUBLISHED_EVIDENCE_FIELDS[key]))
            for key, column in EVIDENCE_COLUMNS.items()}


def evidence_problems(article, evidence=None):
    evidence = evidence if isinstance(evidence, dict) else extract_evidence(article)
    if "seat and display plus cabin image" in _text(article.get("reason") or article.get("interiorReason") or article.get("内装判定理由")).lower():
        return ["copied_prompt_reason"]
    missing = [f"missing_{key}" for key in EVIDENCE_COLUMNS if not _text(evidence.get(key))]
    if missing:
        return missing
    if _text(evidence["target_component"]).lower() in {"内装", "車内", "自動車", "車両", "内装部品", "interior", "interior parts", "cabin", "vehicle"}:
        return ["unspecified_target_component"]
    if any(_matches(_GENERIC, _text(evidence[key])) for key in EVIDENCE_COLUMNS if key != "source_quote"):
        return ["generic_or_template_evidence"]
    title, body = article_source(article)
    quote = _text(evidence["source_quote"])
    if not 8 <= len(quote) <= 240 or quote.casefold() not in f"{title} {body}".casefold():
        return ["source_quote_not_found"]
    if len(_text(evidence["new_information"])) < 8 or len(_text(evidence["development_reference"])) < 12:
        return ["insufficient_specificity"]
    new_numbers = set(re.findall(r"\d+(?:\.\d+)?", _text(evidence["new_information"])))
    source_numbers = set(re.findall(r"\d+(?:\.\d+)?", f"{title} {body}"))
    if new_numbers - source_numbers:
        return ["new_information_has_unsupported_number"]
    # The cited passage must name the component or a concrete technology.
    if not _matches(_CABIN_PART + "|" + _TRANSFER_FEATURE + "|" + _SEAT + "|" + _INTERIOR_LIGHT +
                    r"|ディスプレイ|スクリーン|カップホルダー|収納|換気|空調|\b(?:display|screen|storage|ventilation|HVAC)\b", quote):
        return ["source_quote_has_no_component"]
    return []


def apply_policy(article, rules=(), *, require_evidence=True):
    """Apply only approved fixed presets; unknown rules never become code.

    The caller separately honors exact excluded URLs and preserves published
    representatives. A keep result with require_evidence=False is only a scope
    precheck, never permission to publish a new article without its rationale.
    """
    enabled = {key: True for key in PRESET_KEYS}
    for rule in rules or ():
        if (isinstance(rule, dict) and rule.get("key") in PRESET_KEYS
                and rule.get("review_status") == "approved" and rule.get("version") == 1
                and isinstance(rule.get("enabled"), bool)):
            enabled[rule["key"]] = rule["enabled"]
    title, body = article_source(article)
    source = f"{title} {body}"
    # Translated text helps identify scope, but cannot validate a source quote.
    heading = _text(f"{title} {article.get('title', '')}")
    scope = _text(f"{source} {article.get('title', '')} {article.get('desc', '')}")
    evidence = extract_evidence(article)
    lighting = classify_lighting(heading, scope)
    result = {"decision": "keep", "reason": "development_value_supported", "policy_version": POLICY_VERSION,
              "evidence": evidence, "lighting": lighting, "matched_rule_ids": []}

    def reject(reason, key, decision="exclude"):
        return dict(result, decision=decision, reason=reason, matched_rule_ids=[key])

    if str(article.get("country") or article.get("国") or "").lower() in {"paper", "papers", "論文"}:
        return dict(result, reason="curated_paper")
    transferable = _matches(_TRANSFER_FEATURE, source)
    explicit_cabin_transfer = (transferable and _matches(_CABIN_PART, source)
                               and _matches(r"転用|応用|共用|乗用車|自動車内装|\b(?:adapt|transfer|passenger.car|automotive interior)", source))
    bike_primary = (_matches(_BIKE, heading) or _matches(r"バイク|ライディングブーツ|防水ブーツ", heading)
                    or _matches(r"/(?:bike-reviews|bike-news|motorcycles?)/", str(article.get("url", ""))))
    # Bicycle luggage in a passenger-car storage article is not a motorcycle item.
    car_storage = _matches(r"(?:SUV|ミニバン|乗用車|車室内).{0,40}(?:収納|積載)|(?:収納|積載).{0,30}(?:SUV|ミニバン)", scope)
    if enabled["exclude_non_passenger_vehicles"] and bike_primary and not explicit_cabin_transfer and not car_storage:
        return reject("motorcycle_or_riding_equipment", "exclude_non_passenger_vehicles")
    if enabled["exclude_off_topic"]:
        for pattern, reason in ((_FINANCE, "consumer_finance_procedure"), (_SPACE, "space_history"), (_TRAVEL, "travel_itinerary")):
            if _matches(pattern, heading) and not explicit_cabin_transfer:
                return reject(reason, "exclude_off_topic")
    if enabled["seat_requires_transferable_value"] and _matches(_SEAT_PRODUCT, heading) and _matches(_SEAT, scope):
        if not transferable and not _matches(_NON_SEAT_PART, source):
            return reject("seat_only_without_transferable_value", "seat_requires_transferable_value")
    if enabled["interior_lighting_only"] and lighting == "exterior" and not (_matches(_NON_SEAT_PART, source) or explicit_cabin_transfer):
        return reject("exterior_lighting_only", "interior_lighting_only")
    if require_evidence and enabled["require_development_value"]:
        problems = evidence_problems(article, evidence)
        if problems:
            return reject(";".join(problems), "require_development_value", "hold")
    return result


def assessment_instructions():
    return (
        "Assess usefulness to passenger-car INTERIOR component development, not general automotive interest.\n"
        "A standalone seat launch, dimensions, fitment or price is normally out of scope. Keep concrete transferable "
        "upholstery, trim, sensing, HMI, material-process or cabin comfort engineering information.\n"
        "Motorcycles/riding equipment, consumer loan procedures, tourism, space history and exterior-only lighting "
        "are out of scope unless the source explicitly describes transferable cabin technology.\n"
        "Return score (integer 0-100), reason, image_interior (boolean/null), and evidence object with four strings: "
        "target_component, new_information, development_reference, source_quote.\n"
        "target_component names the relevant interior part or technology. new_information describes what specifically changed. "
        "development_reference explains the concrete comparison, material/process choice, design constraint or test that the "
        "source can inform; describe proposed applications as hypotheses. source_quote is an 8-240 character exact passage copied from "
        "the ORIGINAL title/article that supports the new information, including the component or technology.\n"
        "Do not copy illustrative reasons or use generic claims such as useful for interior development. "
        "If those fields cannot be grounded, leave them empty and score below 40; the article will be held or excluded. "
        "An attractive cabin image never replaces textual evidence. Do not add benefits absent from the source.\n"
    )
