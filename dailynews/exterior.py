"""Exterior-specific editorial rules; transport and publishing remain shared."""

import re

PRODUCT_TERMS = (
    "グリル", "バンパー", "フェンダー", "エンブレム", "外装", "エクステリア",
    "レドーム", "レーダー透過", "ミリ波透過", "センサー透過", "ウェザーストリップ",
    "ウエザーストリップ", "シール材", "ヘッドランプ", "テールランプ", "ヘッドライト",
    "テールライト", "デイタイムランニング", "発光エンブレム", "ボディ加飾", "モールディング",
    "スポイラー", "ディフューザ", "スプリッタ", "ディフレクタ",
    "grille", "bumper", "fender", "emblem", "exterior", "radome", "radar transparent",
    "radar-transparent", "weatherstrip", "weather strip", "body sealing", "headlamp", "headlight",
    "taillamp", "taillight", "tail lamp", "tail light", "daytime running", "body trim",
    "spoiler", "diffuser", "splitter", "deflector",
    "车外", "外饰", "格栅", "保险杠", "翼子板", "车标", "透波", "密封条", "前大灯", "尾灯",
)
TECHNOLOGY_TERMS = ("材料", "樹脂", "加飾", "塗装", "成形", "発光", "照明", "透過", "空力", "耐候", "リサイクル", "軽量", "設計", "センサー", "material", "resin", "molding", "coating", "lighting", "sensor", "aerodynamic", "recycl", "lightweight", "design", "surface", "发光", "材料", "传感", "空气动力")
TOPICS = tuple(re.compile(pattern, re.I) for pattern in (
    r"グリル|格栅|\bgrilles?\b",
    r"バンパー|保险杠|\bbumpers?\b",
    r"エンブレム|車標|车标|\bemblems?\b",
    r"レドーム|透過|透波|\bradomes?\b|radar.transparent",
    r"ヘッド(?:ランプ|ライト)|テール(?:ランプ|ライト)|照明|発光|灯|\b(?:headlights?|headlamps?|taillights?|taillamps?|lighting)\b",
    r"ウェザーストリップ|ウエザーストリップ|シール材|密封条|weather.?strip|body.seal",
    r"加飾|モール|塗装|樹脂|材料|リサイクル|カーボンファイバー?|炭素繊維|アラミド|\b(?:trim|coating|resin|material|recycled|paint(?:s|ed|ing)?|carbon[\s-]+fib(?:er|re)s?|aramid)\b",
    r"空力|エアロ|空气动力|スポイラー|ディフューザー?|スプリッター?|ディフレクター?|\baerodynamic|\b(?:spoilers?|diffusers?|splitters?|deflectors?)\b",
))

SUMMARY_RULES = (
    "原文にある事実・評価だけを使い、原文にない装備・数値を補わない。\n"
    "要望・批評・否定・仮定を維持し、提案を採用済みと書かない。競合車の装備を対象車の装備へ置き換えない。\n"
    "外装の具体情報（グリル、バンパー、加飾、発光、エンブレム、センサー透過、シール、材料、空力）が複数ある場合は2〜3点を残す。\n"
    "原文に外装の具体情報がなければ補わず、写真だけから素材・性能・採用技術を推定しない。\n"
    "市場・規制・材料・競合・デザインのトレンド記事は、対象車種/地域、変化、期間、根拠データを優先し、外装部品の事実を無理に補わない。\n"
)
SUMMARY_FOCUS = "自動車外装の具体情報、または乗用車のデザイン・市場・規制・材料・競合トレンドの本文根拠を優先する。トレンド記事には対象地域・車種・期間・変化を残し、外装部品の採用や需要増を創作しない。"

# These are candidate hints and score guards, not automatic acceptance rules.
# The LLM still checks the article's concrete relevance to exterior planning.
TREND_TOPICS = {
    "materials": re.compile(r"樹脂|ゴム|塗料|塗装|再生材|リサイクル|循環|軽量材料|塑料|橡胶|回收|再生材料|\b(?:resins?|polymers?|plastics?|coatings?|recycl\w*|circular\w*|lightweight materials?)\b", re.I),
    "regulation": re.compile(r"規制|法規|安全基準|歩行者保護|義務化|法规|法规|强制标准|\b(?:regulations?|legislation|standards?|pedestrian protection|end.of.life vehicles?|ELV|Euro NCAP)\b", re.I),
    "market": re.compile(r"販売台数|登録台数|販売動向|市場|需要|シェア|销量|份额|市场|\b(?:sales|registrations?|market|demand|forecast|segment|market share)\b", re.I),
    "design": re.compile(r"デザイン|スタイリング|造形|コンセプトカー|外観|意匠|设计|造型|概念车|\b(?:design|styling|facelift|concept car|concept vehicle|new.look)\b", re.I),
    "competitor": re.compile(r"商品戦略|車種構成|新型車|新モデル|モデルチェンジ|新車投入|事業提携|共同開発|新车型|新车|战略|车型|\b(?:new model|model range|line.up|product strategy|launch|debut|partnership|collaborat\w*|expan\w*|deliveries|pre.sales)\b", re.I),
}
AUTOMOTIVE_CONTEXT = re.compile(
    r"自動車|乗用車|新車|車両|SUV|セダン|ミニバン|トヨタ|レクサス|日産|ホンダ|マツダ|スズキ|ダイハツ|三菱|スバル|汽车|乘用车|轿车|\b(?:automotive|automakers?|vehicles?|cars?|SUVs?|MPVs?|sedans?|Toyota|Lexus|Nissan|Honda|Mazda|Suzuki|Hyundai|Kia|BMW|Mercedes|Volkswagen|Volvo|Ford|GM|Stellantis|JLR|BYD|Geely|Nio|Xpeng|Voyah|Aito|Seres|Maruti|Mahindra|Tata)\b", re.I)


def matching_trend_topics(text):
    text = str(text or "")
    if not AUTOMOTIVE_CONTEXT.search(text):
        return []
    return [topic for topic, pattern in TREND_TOPICS.items() if pattern.search(text)]


def news_category(title="", content="", category=None, trend_topic=None):
    text = f"{title} {content}"
    topics = matching_trend_topics(text)
    category = str(category or "").strip().lower()
    trend_topic = str(trend_topic or "").strip().lower()
    if category == "trend":
        return ("trend", trend_topic) if trend_topic in topics else ("", "")
    if has_product_details(text):
        return "product", ""
    if category != "product" and topics:
        return "trend", topics[0]
    return "", ""


def has_product_details(text):
    folded = str(text or "").lower()
    return any(term.lower() in folded for term in PRODUCT_TERMS)


def summary_omits_details(summary, source):
    topics = [pattern for pattern in TOPICS if pattern.search(str(source or ""))]
    return len(topics) >= 2 and sum(bool(pattern.search(str(summary or ""))) for pattern in topics) < 2


def calibrate_score(score, title="", content="", summary="", category=None, trend_topic=None):
    # An exterior photograph alone does not demonstrate product-development relevance.
    # Generated summaries cannot supply evidence absent from the original text.
    accepted_category, _ = news_category(title, content, category, trend_topic)
    if not accepted_category:
        return min(int(score), 35), "外装製品または企画に関係するトレンドの本文根拠なし"
    return max(0, min(100, int(score))), ""


def assessment_prompt(title, content, url, summary):
    return (
        "Classify automotive news for passenger-vehicle EXTERIOR product development.\n"
        "Return JSON with score (integer 0-100), reason (short Japanese explaining the concrete planning relevance), "
        "category ('product' or 'trend'), trend_topic (one of design, market, regulation, materials, competitor for trend; empty for product), image_interior (true/false/null). "
        "The legacy field image_interior means whether this image shows relevant EXTERIOR component details.\n"
        "Score 80-100: specific exterior component technology, grille, bumper, emblem, radome/radar-transparent cover, "
        "exterior trim, illumination, weatherstrip/body seal, durable coatings, recycled resin or aerodynamic component.\n"
        "Score 60-79: vehicle article with concrete exterior part design, function, material or integration details.\n"
        "For category=trend, score 80-100 for specific evidence useful to exterior product planning: passenger-car segment demand, "
        "OEM model/design strategy, exterior-relevant regulations, material/supplier developments. Score 60-79 for a clear but narrower planning signal. "
        "Trend articles need not name an exterior part, but must contain actual facts, changes, comparisons or data, and your reason must explain the planning connection.\n"
        "Score 36-59: vague styling or weak/indirect relevance. Score 0-35: interior-only, stock prices, dealer discounts, "
        "battery/engine specifications alone, logistics, general IT, celebrity stories, or a general vehicle photo without useful text evidence. "
        "Sales is eligible when it reports passenger-vehicle segments, model demand or market structure; a price-only promotion is not.\n"
        "An exterior photo alone cannot qualify an article. Do not infer material or engineering functions from an image. "
        "ADAS/LiDAR qualifies only with exterior sensor integration, radome, cleaning, heating, surface or transparency details. "
        "Passenger cars are the main scope. Motorcycles, buses and heavy trucks without transferable component lessons score below 40.\n"
        "Use semantic relevance and specificity, not arbitrary keyword or image bonuses.\n"
        f"Title: {title}\nArticle: {content}\nJapanese summary: {summary}\nURL: {url}\n"
    )


def out_of_scope_idea(text):
    return not has_product_details(text)


def select_items(items, limit=6):
    candidates = [item for item in items if item.get("newsId") and item.get("title") and item.get("desc")]
    return sorted(candidates, key=lambda item: (item.get("productScore", item.get("interiorScore")) or 0, len(item.get("desc", ""))), reverse=True)[:limit]


def make_country_prompt(date_key, country, items, template, history, need_count, anchors, format_item):
    selected = select_items(items)
    ids = [item["newsId"] for item in selected]
    anchors = anchors or ([[selected[i % len(selected)]] for i in range(max(0, need_count))] if selected else [])
    anchor_text = "\n".join(f"ideas[{i}] anchor IDs: {','.join(item['newsId'] for item in group)}\n" + "\n".join(format_item(item) for item in group) for i, group in enumerate(anchors[:need_count]))
    return f"""{template}
対象日: {date_key} / 対象地域: {country}
ニュース:
{chr(10).join(format_item(item) for item in selected)}
ニュース区分: {', '.join(str(item.get('newsId', '')) + '=' + str(item.get('contentCategory', 'product')) + '/' + str(item.get('trendTopic', '')) for item in selected)}
アイデアの根拠:
{anchor_text}
過去の企画（繰り返し禁止）:
{chr(10).join(str(item.get('title', '')) + ': ' + str(item.get('desc', '')) for item in (history or [])[:12])}
JSONのみ: {{"analysis":"...", "ideas":[{{"title":"...", "desc":"...", "sourceNewsIds":["..."]}}]}}
analysisは300〜420字を目安に、外装開発の示唆を具体化する。記事数が少ない場合は短くし、地域全体のトレンドと断定しない。
製品・技術の記事とトレンド・マーケットの記事を区別する。市場や規制の事実から導く開発上の示唆は推論として書き、部品の採用実績と混同しない。
各文に直接関係する参照IDを関連語の直後に付ける（例: 新しい加飾[{ids[0] if ids else 'jp1'}]）。使用可能なID: {','.join(ids)}。
ideasは最大{need_count}件。根拠が足りなければ減らす。titleは日本語で20文字以内、descは120〜180字程度。
各ideaは割り当てられたanchor IDだけを根拠とし、1件のニュースの課題・部品・材料から提案する。
descの第1文で根拠ニュースの車名または技術名を明記し、提案する製品と誰にどんな価値があるかを書く。
提案は仮説と分かる表現にする。出典にない性能・採用実績を事実として書かない。
sourceNewsIdsは対応するanchor IDと一致させ、desc末尾に同じIDを[]で付記する。
企画対象はグリル、バンパー、外装加飾、発光エンブレム、レドーム、センサー透過カバー、ウェザーストリップなど。
トレンド記事を根拠とする案は、観測された変化に対応する外装開発の仮説にとどめる。根拠が弱ければ案を減らす。元記事にない性能や需要量を補わない。
画像生成は停止中。imagePromptおよびimgは出力しない。外装製品の説明をテキストだけで完結させる。
"""
