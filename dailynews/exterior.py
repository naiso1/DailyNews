"""Exterior-specific editorial rules; transport and publishing remain shared."""

import re
from dailynews.exterior_scope import BODY, THEMES, SCOPE_TEXT, transfer_candidate, theme_hits

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
LEGACY_PRODUCT_TERMS = PRODUCT_TERMS
PRODUCT_TERMS += THEMES["body"]
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
    "比較・評価試験の実施だけが書かれている場合は『比較した』『評価した』と記す。効果が良い・悪い・未実証のいずれも補わず、結果が原文にある場合だけ結果を述べる。laserはレーザー、couponは試験片など、一般技術語を企業名扱いにしない。\n"
    "車体・開閉体・接合・製造工程・冷却・NV・安全評価の具体情報も残す。周辺技術は原文の材料・方法・特性を要約し、外装への転用を採用済みと書かない。\n"
    "原文にある事実・評価だけを使い、原文にない装備・数値を補わない。\n"
    "要望・批評・否定・仮定を維持し、提案を採用済みと書かない。競合車の装備を対象車の装備へ置き換えない。\n"
    "過去の取材・再掲はその旨を残す。開発車、車名の推定、発売予想を確定した量産仕様と書かず、観察・記者の推測・メーカー発表を区別する。\n"
    "外装の具体情報（グリル、バンパー、加飾、発光、エンブレム、センサー透過、シール、材料、空力）が複数ある場合は2〜3点を残す。\n"
    "原文に外装の具体情報がなければ補わず、写真だけから素材・性能・採用技術を推定しない。\n"
    "市場・規制・材料・競合・デザインのトレンド記事は、対象車種/地域、変化、期間、根拠データを優先し、外装部品の事実を無理に補わない。\n"
)
SUMMARY_FOCUS = (
    "本文にある具体的な部品・材料・製法・評価内容を最低1つ要約に残す。比較試験の実施だけを性能向上の実証と書かない。"
    "外装・車体の部品、接合、表面処理、製法、軽量化、資源循環、冷却、騒音振動、空力、安全評価も対象。"
    "自動車用途未記載の周辺技術では材料・方法・特性を優先し、外装への応用は仮説として分離する。"
    "自動車外装の具体情報、または乗用車のデザイン・市場・規制・材料・競合トレンドの本文根拠を優先する。"
    "トレンド記事には対象地域・車種・期間・変化を残し、外装部品の採用や需要増を創作しない。"
    "過去の取材・再掲はその旨を残す。開発車、車名の推定、発売予想を確定した量産仕様と書かず、観察・記者の推測・メーカー発表を区別する。"
)

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
    if (has_product_details(text) or transfer_candidate(text)
            or (AUTOMOTIVE_CONTEXT.search(text) and set(theme_hits(text)) & {"performance", "sensing", "safety"})):
        return "product", ""
    if category != "product" and topics:
        return "trend", topics[0]
    return "", ""


def has_product_details(text):
    folded = str(text or "").lower()
    return (any(term.lower() in folded for term in LEGACY_PRODUCT_TERMS)
            or bool(BODY.search(folded) and AUTOMOTIVE_CONTEXT.search(folded)))


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
        SCOPE_TEXT + "\n"
        "Return JSON: score (0-100), reason (short Japanese), category ('product' for direct/transfer or 'trend'), "
        "development_lane ('direct','transfer','trend','exclude'), source_evidence (short source technology fact), "
        "application (Japanese exterior application hypothesis; required for transfer), "
        "trend_topic ('design','market','regulation','materials','competitor' or empty), image_interior (true/false/null; legacy name for EXTERIOR image).\n"
        "80-100: strong specific development information. 60-79: concrete component design changes, process/material/evaluation facts, or credible transfer technology. One theme is sufficient; do not require multiple themes or manufacturing details in a design article. "
        "36-59: vague styling or weak connection. 0-35: excluded/off-topic. An image alone is insufficient. "
        "Trends need actual passenger-car demand, design, regulation, supplier or OEM strategy facts; part naming is optional. "
        "Price-only promotions, stock prices, battery/engine specs alone and generic vehicle photos are excluded. "
        "Use semantic relevance, not keyword counts. Source evidence must come from the original, not the generated summary.\n"
        f"Title: {title}\nArticle: {content}\nJapanese summary: {summary}\nURL: {url}\n"
    )


def out_of_scope_idea(text):
    return not (has_product_details(text) or BODY.search(str(text or "")))


def select_items(items, limit=6):
    candidates = [item for item in items if item.get("newsId") and item.get("title") and item.get("desc")]
    ranked = sorted(candidates, key=lambda item: (item.get("productScore", item.get("interiorScore")) or 0, len(item.get("desc", ""))), reverse=True)
    if limit <= 0 or len(ranked) <= limit:
        return ranked[:max(0, limit)]
    trends = [item for item in ranked if item.get("contentCategory") == "trend"]
    products = [item for item in ranked if item.get("contentCategory") != "trend"]
    trend_slots = min(len(trends), 2, max(1, limit // 3))
    selected = products[:limit - trend_slots] + trends[:trend_slots]
    selected.extend(item for item in ranked if item not in selected)
    return selected[:limit]


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
{SCOPE_TEXT}
応用技術からの案は元の材料・製法・特性を起点にし、外装部品への応用仮説と検証する条件を記す。
トレンド記事を根拠とする案は、観測された変化に対応する外装開発の仮説にとどめる。根拠が弱ければ案を減らす。元記事にない性能や需要量を補わない。
画像は後段のexaBase連携で生成するため、imagePromptおよびimgは出力しない。外装製品の説明をテキストだけで完結させる。
"""


def selection_thresholds(selection, article_date="", issue_date=""):
    """Return (product, trend) minimum scores; the issue's own day is relaxed
    so fresh news fills the quota before older lookback articles."""
    base = int(selection.get("minimum_score", 60))
    trend = int(selection.get("trend_minimum_score", 65))
    if issue_date and str(article_date or "")[:10] == str(issue_date)[:10]:
        return (int(selection.get("issue_date_minimum_score", base)),
                int(selection.get("issue_date_trend_minimum_score", trend)))
    return base, trend
