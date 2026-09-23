import argparse
import csv
import hashlib
import os
import random
import re
import sys
from difflib import SequenceMatcher
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
import json
import textwrap
import requests

from ニュース収集.currency_guard import repair_indian_price_units
from dailynews.editions import get_edition
from dailynews import exterior as exterior_rules
from dailynews.collection_digest import parse_published_news
from dailynews.deduplication import normalize_article_url
from dailynews.editorial_policy import apply_policy, classify_lighting, exterior_scope_rules, EVIDENCE_COLUMNS
from dailynews.feedback_snapshot import load_feedback_snapshot

ROOT = Path(__file__).resolve().parent
EDITION = get_edition()


def configure_edition(edition_id=None):
    global EDITION, NEWS_PATH, INSIGHTS_PATH, HTML_PATH, PROMPT_PATH, DEFAULT_SHEET, IDEA_ANGLES_PATH, TG_PRODUCTS_PATH
    EDITION = get_edition(edition_id)
    os.environ["DAILYNEWS_EDITION"] = EDITION.id
    NEWS_PATH = EDITION.content_dir / "news_data.js"
    INSIGHTS_PATH = EDITION.content_dir / "insights_data.js"
    HTML_PATH = EDITION.content_dir / "内装製品デイリーニュース.html"
    PROMPT_PATH = EDITION.insights_prompt_path
    DEFAULT_SHEET = EDITION.runtime_dir / "sheet2_llm_targets.csv"
    IDEA_ANGLES_PATH = EDITION.idea_angles_path
    TG_PRODUCTS_PATH = EDITION.products_path
    return EDITION


configure_edition(EDITION.id)

ENCODINGS = ["utf-8-sig", "utf-8", "cp932", "utf-16"]
ANALYSIS_CHAR_LIMIT = 420

COUNTRY_MAP = {
    "日本": "jp",
    "jp": "jp",
    "japan": "jp",
    "中国": "cn",
    "cn": "cn",
    "china": "cn",
    "インド": "in",
    "in": "in",
    "india": "in",
    "米国": "us",
    "アメリカ": "us",
    "us": "us",
    "usa": "us",
    "united states": "us",
    "欧州": "eu",
    "eu": "eu",
    "europe": "eu",
    "論文": "paper",
    "paper": "paper",
    "papers": "paper",
    "学術": "paper",
}

TAG_RULES = [
    (r"HMI|ヒューマンマシン|UI|UX|インターフェース", "HMI"),
    (r"HUD|ヘッドアップ|AR-HUD|AR\s*HUD", "HUD"),
    (r"AR|拡張現実", "AR"),
    (r"ディスプレイ|スクリーン|モニター|液晶|OLED|LCD", "ディスプレイ"),
    (r"ナビ|インフォテインメント|IVI|コネクテッド|通信", "コネクテッド"),
    (r"AI|人工知能|音声|ジェスチャー|対話", "AI"),
    (r"センサー|モニタリング|ドライバー監視", "センシング"),
    (r"シート|座席|シートベルト|マッサージ|ベンチレーション", "シート"),
    (r"ダッシュボード|インパネ|コックピット", "コックピット"),
    (r"センターコンソール|コンソール", "センターコンソール"),
    (r"イルミ|照明|アンビエント", "イルミ"),
    (r"素材|レザー|革|バイオ|リサイクル|サステナ", "新素材"),
    (r"EV|電動|電気自動車|充電|バッテリー|BEV", "EV"),
    (r"電池|動力電池|LFP|三元|NCM|CATL|BYD|ギガワット|GWh", "バッテリー"),
    (r"安全|エアバッグ|ADAS|衝突|セーフティ", "安全"),
    (r"音響|スピーカー|オーディオ", "音響"),
    (r"カスタム|パーソナル|カスタマイズ", "カスタマイズ"),
]

PLACEHOLDER_IMG = "images/idea_dummy.svg"

ITEM_OVERRIDES = {
    "https://www.motor1.com/news/807764/new-dacia-spring-no-screen/": {
        "title": "ダチア新型スプリング、廉価版は中央画面を省きスマホで操作",
        "desc": "ダチアの新型スプリングは、廉価版の中央画面を省き、ダッシュボードに固定したスマホをナビや音楽再生に使う。ステアリングのスイッチで主要機能を操作でき、7インチのデジタルメーターは標準装備。フランスでの価格は1万7900ユーロからで、1500ユーロ高い上位仕様には10インチ画面や後退用カメラなどを備える。前席ヒーターはオプションとなる。",
    },
    "https://www.indiacarnews.com/news/new-4wd-electric-suv-spotted-in-india-harrier-ev-rival-68976/": {
        "title": "iCaur 03をインドで目撃、15.6インチ画面と前後席の通風機能",
        "desc": "5人乗り電動SUVのiCaur 03が、インドで輸送される姿を目撃された。JSWと奇瑞の提携による導入準備とみられるが、発売時期は未確定。記事では15.6インチの中央画面、9.2インチのメーター、電動調整式前席、前後席の通風機能、アンビエント照明、50Wワイヤレス充電などを紹介している。インド向けの最終仕様として確定した内容ではない。",
    },
    "https://www.indiacarnews.com/news/new-maruti-baleno-price-list-out-5-variants-rs-5-99-lakh-rs-9-99-lakh-68972/": {
        "title": "マルチ・スズキ新型バレーノ、全5グレードの価格と快適装備を紹介",
        "desc": "マルチ・スズキが新型バレーノの価格を公開。全5グレードで、導入時の車両価格は59.9万〜99.9万ルピー。記事はクラリオン製音響、前席通風機能、ワイヤレス充電、レベル2運転支援の追加を紹介する。9インチ中央画面、無線接続のスマホ連携、オートエアコン、HUDなども挙げているが、各装備のグレード別設定は本文では明示されていない。",
    },
    "https://autodesignmagazine.com/en/2026/09/what-ai-cant-copy/": {
        "title": "マツダ前田育男氏、AIに模倣できない手仕事の価値を語る",
        "desc": "マツダの前田育男氏らが、ヴェネツィアの工芸展「Homo Faber」でAI時代の手仕事の価値を議論。前田氏は、素材と向き合う手や身体の動きはAIでは再現できないと語る。絹や墨を使った灯籠、金継ぎなどの展示・体験を通じ、日本と欧州の工芸文化の融合や、人の感情を造形に込める意義を示した。",
    },
    "https://www.autocar.co.uk/car-news/consumer/top-tips-happy-ev-ownership-electric-car-veteran": {
        "title": "EV歴5年の筆者が紹介、電池容量と充電計画の選び方",
        "desc": "EVを5年間利用してきた筆者が、快適に乗り続けるための工夫を紹介。必要以上に大きい電池を選ばず、用途と急速充電網に合わせて容量を決める考え方を示す。残量20％を下回る前の充電や、ナビを使った経路上の充電器の確認、自宅での夜間の割安な電力の利用など、実体験に基づく助言を挙げる。",
    },
    "https://carnewschina.com/2026/09/07/xiaomi-launches-skynomad-n90-max-featuring-a-native-electric-pop-up-roof-cabin/": {
        "title": "小米Skynomad N90 Max発表、可動式コンソールと車中泊仕様",
        "desc": "小米の7人乗りEREV「Skynomad N90 Max」は、レール上を移動するセンターコンソールに9L冷蔵庫を内蔵。車内は3色展開で、16.1インチ画面とHyperOSを採用し、2＋2＋3席で11通りの空間レイアウトに対応する。前席・2列目にはマッサージ、通風、ヒーター機能を備えたゼログラビティシートの選択肢も用意。標準Maxは26.99万元、電動ポップアップルーフを備えるExplorer Editionは29.99万元。",
        "tags": ["HMI", "ディスプレイ", "センターコンソール", "シート", "EV"],
        "sourceExcerpt": "The central island is a movable, rail-mounted unit",
        "sourceExcerptEnd": "multiple ecological expansion interfaces.",
    },
    "https://news.yahoo.co.jp/articles/fac5ea53b286b35b74c62279370f5b24f40916c3?source=rss": {
        "title": "新型エルグランド、伝統工芸を思わせる内装と後席の細部への評価",
        "desc": "新型日産エルグランドのGグレードは、刺子を思わせる菱形ステッチをシートやドアトリムに配し、人工レザーのテーラーフィットを採用する。一方、筆者は後席まわりの見栄えをアルファード／ヴェルファイアと比較し、テーブルやスイッチ、室内灯などの細部には、最上位ミニバンとしてさらにこだわりが欲しかったと指摘している。",
        "sourceExcerpt": "センターテーブルやスイッチ類、室内灯などのディテールにも、",
        "sourceExcerptEnd": "こだわりが欲しかったようには思う。",
    },
    "https://www.sohu.com/a/994292210_122645970": {
        "title": "起亜EV9コンセプト、海をモチーフにしたサステナブル内装",
        "desc": "起亜のEV9コンセプトは、広大な海を着想源にしたエクステリアと、静かな空の青を取り入れた車内空間を組み合わせ、自然に近い安らぎを演出する。廃漁網由来の床材や再生PETボトル由来のシート・ドア加飾など、持続可能素材の活用も特徴。",
        "source": "搜狐",
    },
    "https://auto.ifeng.com/c/8rMV470fRfX": {
        "title": "新車コックピット週報：小米は個性化、VWは脱・大衆、極氪は4Dシアターへ",
        "desc": "極氪8XはNaimオーディオと4D体験を備えた内装を採用。小米SU7は安全装備と2色ステアリングを強化し、フォルクスワーゲン陣営は連動型ディスプレイ、ID.ERA 9XはSmart Surfaceのマジックスクリーンを導入している。",
        "source": "鳳凰網汽車",
    },
    "https://www.msn.com/en-in/autos/general/a-closer-look-at-the-luxurious-interior-of-the-skoda-vision-7s/vi-AA1XNsOx": {
        "title": "Skoda Vision 7Sの豪華な内装を詳しく見る",
        "desc": "SkodaのコンセプトカーVision 7Sは、技術、快適性、内装レイアウトの将来像を示すために設計された、未来志向のショーカーです。",
        "source": "Autogefuhl",
    },
}


def read_csv_any(path: Path):
    data = None
    last_err = None
    for enc in ENCODINGS:
        try:
            with path.open("r", encoding=enc, newline="") as f:
                reader = csv.reader(f)
                rows = list(reader)
            if not rows:
                continue
            header = rows[0]
            if any("タイトル" in c for c in header) and any("日付" in c for c in header):
                return header, rows[1:], enc
            data = (header, rows[1:], enc)
        except Exception as e:
            last_err = e
            continue
    if data:
        return data
    raise last_err or RuntimeError("CSV read failed")


def normalize_header(header):
    return [h.strip() for h in header]


def find_col(header, *candidates):
    for cand in candidates:
        for i, h in enumerate(header):
            if cand in h:
                return i
    return None


def find_col_exact(header, name):
    for i, h in enumerate(header):
        if h == name:
            return i
    return None


def parse_score_0_100(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", text)
    if not m:
        return None
    score = float(m.group(0))
    if score <= 1:
        score *= 100
    return int(max(0, min(100, round(score))))


def map_country(value: str):
    if not value:
        return ""
    key = str(value).strip().lower()
    for k, v in COUNTRY_MAP.items():
        if key == k.lower():
            return v
    for k, v in COUNTRY_MAP.items():
        if k.lower() in key:
            return v
    return ""


def derive_source(url, fallback=""):
    if fallback:
        return fallback
    try:
        host = urlparse(url).netloc
        return host.replace("www.", "")
    except Exception:
        return fallback or ""


def related_source_urls(value, primary_url=""):
    """Keep valid additional sources without collapsing meaningful URL queries."""
    if isinstance(value, str):
        try:
            value = json.loads(value) if value.strip() else []
        except (ValueError, TypeError):
            value = []
    if not isinstance(value, list):
        return []
    seen = {normalize_article_url(primary_url)}
    result = []
    for url in value:
        if not isinstance(url, str) or urlparse(url).scheme.lower() not in {"http", "https"} or not urlparse(url).netloc:
            continue
        key = normalize_article_url(url)
        if key and key not in seen:
            seen.add(key)
            result.append(url)
    return result


def unique_publication_items(items):
    """Last URL guard for direct CSV/resume publication, independent of collection."""
    # Resolve the complete URL graph before choosing representatives: a later
    # row can connect two earlier groups through their already trusted sources.
    prepared = [{**item, "relatedUrls": related_source_urls(item.get("relatedUrls", []), item.get("url", ""))}
                for item in items]
    parents = list(range(len(prepared)))

    def find(index):
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    owners = {}
    for index, item in enumerate(prepared):
        for key in publication_item_url_keys(item):
            if key in owners:
                a, b = find(index), find(owners[key])
                parents[max(a, b)] = min(a, b)
            else:
                owners[key] = index
    unique, representatives = [], {}
    for index, item in enumerate(prepared):
        group = find(index)
        if group not in representatives:
            representatives[group] = item
            unique.append(item)
        else:
            kept = representatives[group]
            kept["relatedUrls"] = related_source_urls(
                kept["relatedUrls"] + [item.get("url", "")] + item["relatedUrls"], kept.get("url", ""))
    return unique


def publication_item_url_keys(item):
    return [normalize_article_url(url) for url in related_source_urls(
        [item.get("url", ""), *related_source_urls(item.get("relatedUrls", []))])]


def news_string_field(block, name):
    """Read a quoted or unquoted JS property without changing its source text."""
    from dailynews.exabase import JSON_STRING
    match = re.search(rf'(?<![\w])"?{re.escape(name)}"?\s*:\s*({JSON_STRING})', block)
    return json.loads(match.group(1), strict=False) if match else ""


def publication_url_id_map(news_text):
    """Original and related URLs resolve to existing IDs, including retained aliases."""
    articles = parse_published_news(news_text)
    by_id = {}
    for article in articles:
        by_id.setdefault(article["id"], article)
    result = {}
    for article in articles:
        target = article
        visited = set()
        while target.get("duplicateOf"):
            if target["id"] in visited or target["duplicateOf"] not in by_id:
                target = None
                break
            visited.add(target["id"])
            target = by_id[target["duplicateOf"]]
        if not target:
            continue
        for url in [article["url"], *article.get("relatedUrls", [])]:
            key = normalize_article_url(url)
            if key:
                result.setdefault(key, target["id"])
    return result


def merge_related_sources(news_text, items):
    """Save newly discovered related sources on a same-issue retry as well."""
    from dailynews.exabase import LEAF_OBJECT
    canonical = publication_url_id_map(news_text)
    additions = {}
    for item in items:
        target = next((canonical[key] for key in publication_item_url_keys(item) if key in canonical), None)
        if target:
            additions.setdefault(target, []).extend(
                [item.get("url", ""), *related_source_urls(item.get("relatedUrls", []))])
    if not additions:
        return news_text
    # Alias records stay intact for existing citations; their URLs are also
    # discoverable on the representative's source list, including alias chains.
    for article in parse_published_news(news_text):
        target = canonical.get(normalize_article_url(article["url"]))
        if target in additions:
            additions[target].extend([article["url"], *article.get("relatedUrls", [])])
    edits = []
    for match in LEAF_OBJECT.finditer(news_text):
        block = match.group()
        url = news_string_field(block, "url")
        extra = additions.get(news_string_field(block, "id"))
        if not extra:
            continue
        existing = re.search(r'\brelatedUrls"?\s*:\s*(\[(?:\s*"(?:\\.|[^"\\])*"\s*,?)*\s*\])', block)
        old = json.loads(existing.group(1), strict=False) if existing else []
        merged = related_source_urls(old + extra, url)
        if merged == old:
            continue
        encoded = json.dumps(merged, ensure_ascii=False)
        if existing:
            replacement = block[:existing.start(1)] + encoded + block[existing.end(1):]
        else:
            replacement = block.rstrip()[:-1].rstrip().rstrip(",") + f", relatedUrls: {encoded} }}"
        edits.append((match.start(), match.end(), replacement))
    for start, end, replacement in reversed(edits):
        news_text = news_text[:start] + replacement + news_text[end:]
    return news_text


def apply_item_overrides(item: dict):
    if EDITION.id == "exterior":
        return item
    override = ITEM_OVERRIDES.get(item.get("url", ""))
    if not override:
        return item
    out = dict(item)
    for key, value in override.items():
        if value:
            out[key] = value
    return out


def generate_tags(text: str):
    if EDITION.id == "exterior":
        rules = [(r"グリル|格栅|grille", "グリル"), (r"バンパー|保险杠|bumper", "バンパー"), (r"エンブレム|车标|emblem", "エンブレム"), (r"レーダー|透過|レドーム|radome|radar", "センサー透過"), (r"発光|照明|ランプ|ライト|lighting|headlamp|taillamp", "照明・発光"), (r"加飾|塗装|モール|coating|trim", "外装加飾"), (r"ウェザーストリップ|ウエザーストリップ|シール|weatherstrip|sealing", "シール"), (r"素材|樹脂|リサイクル|material|resin|recycl", "材料"), (r"空力|aerodynamic", "空力")]
        return [tag for pattern, tag in rules if re.search(pattern, text, re.IGNORECASE)][:6]
    tags = []
    for pattern, tag in TAG_RULES:
        if tag == "イルミ" and classify_lighting(content=text) not in ("interior", "both"):
            continue
        if re.search(pattern, text, flags=re.IGNORECASE):
            if tag not in tags:
                tags.append(tag)
    return tags[:6]


SELECTION_FIELDS = {
    "target_component": "selectionTargetComponent",
    "new_information": "selectionNewInformation",
    "development_reference": "selectionDevelopmentReference",
    "source_quote": "selectionSourceQuote",
}


def validate_editorial_publication(items, existing_url_keys, snapshot, edition_id):
    """Defend direct/resumed CSV publication before enrichment or generation."""
    excluded = set(snapshot.get("excluded_urls", []))
    retained, pending = [], []
    for item in items:
        # The snapshot already expands a hidden representative to its aliases.
        # Hiding only an alias must not suppress an unhidden representative that
        # still mentions that URL as a related source (collector uses primary URL).
        if normalize_article_url(item.get("url", "")) in excluded:
            print(f"[EDITORIAL_HIDDEN] {item.get('url', '')}")
            continue
        if (item.get("country") == "paper"
                or normalize_article_url(item.get("url", "")) in existing_url_keys):
            retained.append(item)
            continue
        if edition_id == "exterior":
            result = apply_policy(item, exterior_scope_rules(snapshot.get("rules", [])), require_evidence=False)
            if result["decision"] != "keep":
                pending.append(f"{item.get('url', '')} ({result['reason']})")
            else:
                retained.append(item)
            continue
        # Interior trusts the collector's own selection (relevance classification,
        # score, and same-day quota backfill) as-is; only explicit takedowns
        # (excluded, above) and already-published duplicates are filtered here.
        retained.append(item)
    if pending:
        raise RuntimeError("Editorial validation failed; no news or insights have been updated. "
                           "Reassess these new source rows: " + ", ".join(pending))
    return retained


def has_japanese_text(text: str):
    return bool(re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", str(text or "")))


def validate_japanese_news_items(items):
    """Do not publish untranslated fallbacks or silently reduce the country quota."""
    pending = []
    for item in items:
        # Preserve the curated paper feed's existing inclusion policy.
        if item.get("country") == "paper":
            continue
        title = str(item.get("title") or "")
        body = str(item.get("desc") or "")
        if not re.search(r"[\u3041-\u3096\u30a1-\u30fa\u4e00-\u9fff]", title) or not re.search(r"[\u3041-\u3096\u30a1-\u30fa]", body):
            pending.append(str(item.get("url") or title))
    if pending:
        raise RuntimeError(
            f"Japanese summary validation failed ({len(pending)} articles). "
            "No news or insights have been updated. Repair these source rows first: "
            + ", ".join(pending)
        )


BAD_SUMMARY_PATTERNS = [
    r"新しい\s*JSON\s*の\s*タイトル",
    r"新しい\s*JSON\s*の\s*サマリー",
    r"JSON\s*形式の\s*サマリー",
    r"タイトルを\s*(?:日本語で)?\s*設定",
    r"サマリーを\s*(?:日本語で)?\s*設定",
]


def is_bad_generated_text(text: str):
    if not text:
        return True
    normalized = re.sub(r"\s+", "", text)
    return any(re.search(pattern, normalized, flags=re.IGNORECASE) for pattern in BAD_SUMMARY_PATTERNS)


def parse_existing_news(js_text: str):
    urls = set(re.findall(r"url:\s*\"([^\"]+)\"", js_text))
    ids = re.findall(r"id:\s*\"([a-z]+)(\d+)\"", js_text)
    max_ids = {}
    for prefix, num in ids:
        try:
            n = int(num)
        except Exception:
            continue
        max_ids[prefix] = max(max_ids.get(prefix, 0), n)
    return urls, max_ids


def parse_news_id_map(js_text: str):
    out = {}
    pattern = re.compile(r'id:\s*"([^"]+)"[\s\S]*?url:\s*"([^"]+)"')
    for m in pattern.finditer(js_text):
        out[m.group(2)] = m.group(1)
    return out


def update_news_updated_at(js_text: str):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    return re.sub(r"window\.NEWS_UPDATED_AT\s*=\s*\"[^\"]*\";", f"window.NEWS_UPDATED_AT = \"{now}\";", js_text, count=1)


def append_news_items(js_text: str, items_by_date):
    insertion = []
    for date_key in sorted(items_by_date.keys()):
        insertion.append(f"    // {date_key} (google検索からExcel sheet2_llm_targets)")
        insertion.extend(items_by_date[date_key])
    block = "\n".join(insertion) + "\n"
    updated = re.sub(r"\n\];\s*$", f"\n{block}];", js_text, flags=re.MULTILINE)
    if updated == js_text:
        # Fallback: append before last ]
        idx = js_text.rfind("];")
        if idx != -1:
            updated = js_text[:idx] + "\n" + block + js_text[idx:]
    return updated


def update_new_date_range(html_text: str, start: str, end: str):
    pattern = r"const NEW_DATE_RANGE_OVERRIDE = \{ start: (?:\"[^\"]*\"|null), end: (?:\"[^\"]*\"|null) \};"
    repl = f"const NEW_DATE_RANGE_OVERRIDE = {{ start: \"{start}\", end: \"{end}\" }};"
    return re.sub(pattern, repl, html_text, count=1)


def fix_existing_entries(js_text: str, items: list):
    from dailynews.exabase import LEAF_OBJECT, JSON_STRING
    corrections = {}
    for it in items:
        if it.get("title") and it.get("url"):
            corrections.setdefault(normalize_article_url(it["url"]), it)
    edits, corrected = [], set()
    for match in LEAF_OBJECT.finditer(js_text):
        block = match.group()
        key = normalize_article_url(news_string_field(block, "url"))
        if key not in corrections or key in corrected:
            continue
        it = corrections[key]
        # Correct only the matching primary article, not a different source
        # resolved through relatedUrls. IDs/dates/URLs/aliases remain unchanged.
        replacements = {
            "title": it.get("title", ""), "desc": it.get("desc", ""),
            "source": derive_source(it["url"], it.get("source", "")), "img": it.get("img", ""),
        }
        for field, value in replacements.items():
            if value:
                block = re.sub(
                    rf'((?<![\w])"?{field}"?\s*:\s*)({JSON_STRING})',
                    lambda m, v=value: m.group(1) + json.dumps(v, ensure_ascii=False),
                    block, count=1,
                )
        edits.append((match.start(), match.end(), block))
        corrected.add(key)
    updated = js_text
    for start, end, block in reversed(edits):
        updated = updated[:start] + block + updated[end:]
    return updated


def read_text_any(path: Path):
    for enc in ENCODINGS:
        try:
            return path.read_text(encoding=enc)
        except Exception:
            continue
    return path.read_text(encoding="utf-8", errors="ignore")


def _models_endpoint(endpoint: str):
    base = re.sub(r"/(chat/completions|responses)$", "", endpoint)
    if not base.endswith("/v1"):
        base = base.rstrip("/") + "/v1"
    return base + "/models"


def _is_loopback_url(url: str):
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    return host in {"127.0.0.1", "localhost", "::1"}


def _request_llm(method: str, url: str, **kwargs):
    if _is_loopback_url(url):
        session = requests.Session()
        session.trust_env = False
        return session.request(method, url, **kwargs)
    return requests.request(method, url, **kwargs)


def _pick_model(endpoint: str, fallback: str):
    try:
        resp = _request_llm("GET", _models_endpoint(endpoint), timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and "data" in data and data["data"]:
            return data["data"][0].get("id") or fallback
    except Exception:
        pass
    return fallback


def call_llm(endpoint, model, prompt):
    chosen_model = model or _pick_model(endpoint, model)
    # Prefer chat completions first
    payload = {
        "model": chosen_model,
        "reasoning_effort": os.getenv("LLM_REASONING_EFFORT", "none"),
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": "<think>\n</think>\n"},
        ],
        "temperature": 0.7,
        "max_tokens": 1200,
    }
    resp = _request_llm("POST", endpoint, json=payload, timeout=180)
    if resp.status_code >= 400:
        # retry with auto-selected model
        alt_model = _pick_model(endpoint, chosen_model)
        if alt_model and alt_model != chosen_model:
            payload["model"] = alt_model
            resp = _request_llm("POST", endpoint, json=payload, timeout=180)
    if resp.status_code >= 400:
        # Try /v1/responses as fallback
        responses_endpoint = re.sub(r"/chat/completions$", "/responses", endpoint)
        responses_payload = {
            "model": payload["model"],
            "input": prompt,
            "temperature": 0.7,
            "max_output_tokens": 1200,
        }
        resp = _request_llm("POST", responses_endpoint, json=responses_payload, timeout=180)
    if resp.status_code >= 400:
        raise requests.HTTPError(f"{resp.status_code} {resp.text}", response=resp)
    data = resp.json()
    if "choices" in data:
        return data["choices"][0]["message"]["content"]
    if "output_text" in data:
        return data["output_text"]
    # LM Studio responses format (array)
    if "output" in data and data["output"]:
        return data["output"][0].get("content", [{}])[0].get("text", "")
    return ""


def _prerepair_json(text: str) -> str:
    """LLMが出しやすい壊れたJSONを正規表現で簡易修復する。
    例: アイデア配列内で { が抜けた要素 -> 補完する"""
    # ], "title": -> ], {"title": (配列内の先頭 { 欠落)
    text = re.sub(r'(\})\s*,\s*"(title|desc|imagePrompt)":', r'\1, {"\2":', text)
    # [  "title": -> [ {"title": (最初の要素から { が欠落)
    text = re.sub(r'(\[)\s*"(title|desc|imagePrompt)":', r'\1{"\2":', text)
    return text


def extract_json_block(text: str):
    if not text:
        return None
    cleaned = re.sub(r"```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    cleaned = cleaned.replace("```", "")
    # </think> タグなど思考過程の除去
    cleaned = re.sub(r"</?think[^>]*>[\s\S]*?</think>", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"</?think[^>]*>", "", cleaned, flags=re.IGNORECASE)
    m = re.search(r"\{[\s\S]*\}", cleaned)
    if not m:
        return None
    raw = m.group(0)
    # まずそのまま試す
    try:
        return json.loads(raw)
    except Exception:
        pass
    # 簡易プレ修復後に再試行
    try:
        return json.loads(_prerepair_json(raw))
    except Exception:
        return None


def repair_json_with_llm(endpoint: str, model: str, raw_text: str):
    if not raw_text or not raw_text.strip():
        return None
    prompt = (
        "次のテキストを、内容を極力変えずに strict JSON へ整形してください。\n"
        "出力は JSON のみ。コードフェンスや説明文は禁止。\n"
        "形式:\n"
        "{\n"
        '  "analysis": "...",\n'
        '  "ideas": [\n'
        '    {"title": "...", "desc": "...", "imagePrompt": "..."},\n'
        '    {"title": "...", "desc": "...", "imagePrompt": "..."}\n'
        "  ]\n"
        "}\n\n"
        "入力テキスト:\n"
        f"{raw_text}"
    )
    try:
        repaired = call_llm(endpoint, model, prompt)
    except Exception:
        return None
    return extract_json_block(repaired)


def parse_insights_max_id(js_text: str):
    ids = re.findall(r"id:\s*(\d+)", js_text)
    nums = [int(x) for x in ids if x.isdigit()]
    return max(nums) if nums else 0


def _normalize_for_similarity(text: str):
    text = (text or "").lower()
    text = re.sub(r"[\s\"'`“”‘’「」『』【】\[\]（）(){}<>、。,.!！?？:：;；/\\|_-]+", "", text)
    return text


def _similarity(a: str, b: str):
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, _normalize_for_similarity(a), _normalize_for_similarity(b)).ratio()


def extract_recent_ideas_by_country(insights_text: str, country: str, limit: int = 40):
    from dailynews.exabase import LEAF_OBJECT, array_fields, string_field
    ideas = []
    for block in array_fields(insights_text, country):
        for match in LEAF_OBJECT.finditer(block):
            idea = {field: string_field(match.group(), field)[0].strip() for field in ("title", "desc", "imagePrompt")}
            if not idea["title"] or not idea["desc"]:
                continue
            ideas.append(idea)
            if len(ideas) >= limit:
                return ideas
    return ideas


def _clean_idea_field(text: str, max_len: int = 400) -> str:
    """LLM出力のtitle/descを正規化する。
    - **マークダウン** を除去
    - titleへのdesc混入を除去（）の後に続く余分なテキストをカット）
    - 先頭・末尾の空白除去
    - max_len 超過分をカット
    """
    text = text.strip()
    # **bold** マークダウン除去
    text = re.sub(r"\*+", "", text)
    # titleの場合: 「）**、...」のように閉じ括弧の後に説明が続く場合をカット
    if max_len <= 40:
        # 全角）または ) の後に読点・句点・空白が続く場合は括弧まででカット
        text = re.sub(r"[）\)][、。\s].*$", "）", text).rstrip("）") + ("）" if "（" in text and "）" not in text.split("（")[-1] else "")
        # それでも長すぎる場合は単純カット
        if len(text) > max_len:
            text = text[:max_len].rstrip("（（、。 　")
    text = text.strip()
    return text[:max_len]


def _is_out_of_scope_idea(text: str) -> bool:
    """Return True for seating or exterior products outside the interior team's scope."""
    if EDITION.id == "exterior":
        return exterior_rules.out_of_scope_idea(text)
    normalized = re.sub(r"\s+", " ", str(text or "")).lower()
    # Seat belts are safety products rather than seating products, so do not
    # reject an otherwise valid idea only because that term appears.
    normalized = normalized.replace("シートベルト", "").replace("seat belt", "").replace("seatbelt", "")
    if any(
        term in normalized
        for term in [
            "シート",
            "座席",
            "座面",
            "背もたれ",
            "ヘッドレスト",
            "ランバーサポート",
        ]
    ):
        return True
    if re.search(r"\b(?:seat|seats|seating|headrest|headrests|backrest|backrests)\b", normalized):
        return True
    return any(
        term in normalized
        for term in ["フロントグリル", "バンパー", "フェンダー", "外装部品", "外装パネル", "エクステリア製品"]
    )


def dedupe_ideas(raw_ideas: list, history_ideas: list, limit: int = 2):
    picked = []
    picked_texts = []
    history_texts = [f"{x.get('title','')} {x.get('desc','')}" for x in history_ideas or []]
    for idea in raw_ideas or []:
        title = _clean_idea_field(str((idea or {}).get("title", "")), max_len=40)
        desc = _clean_idea_field(str((idea or {}).get("desc", "")), max_len=400)
        image_prompt = str((idea or {}).get("imagePrompt", "")).strip()
        source_ids = idea.get("sourceNewsIds") or idea.get("sourceIds") or idea.get("newsIds") or []
        if isinstance(source_ids, str):
            source_ids = re.findall(r"[a-z]{2,5}\d+", source_ids, flags=re.IGNORECASE)
        if not isinstance(source_ids, list):
            source_ids = []
        source_ids = [
            str(x).strip().lower()
            for x in source_ids
            if re.fullmatch(r"[a-z]{2,5}\d+", str(x).strip(), flags=re.IGNORECASE)
        ]
        if not title or not desc:
            continue
        cand = f"{title} {desc}"
        if _is_out_of_scope_idea(cand):
            continue
        duplicate = False
        for ht in history_texts:
            if _similarity(cand, ht) >= 0.58:
                duplicate = True
                break
        if not duplicate:
            for pt in picked_texts:
                if _similarity(cand, pt) >= 0.78:
                    duplicate = True
                    break
        if duplicate:
            continue
        picked.append({"title": title, "desc": desc, "imagePrompt": image_prompt, "sourceNewsIds": source_ids})
        picked_texts.append(cand)
        if len(picked) >= limit:
            break
    return picked


def build_duplicate_guard_text(history_ideas: list, max_items: int = 50):
    if not history_ideas:
        return ""
    lines = []
    for x in history_ideas[:max_items]:
        t = (x.get("title", "") or "").strip()
        d = (x.get("desc", "") or "").strip()[:40]
        if t:
            entry = f"- {t}"
            if d:
                entry += f"（{d}…）"
            lines.append(entry)
    if not lines:
        return ""
    return "【過去アイデア（重複禁止）】\n" + "\n".join(lines)


def normalize_analysis_refs_per_sentence(text: str):
    if not text:
        return text
    text = re.sub(r"[\r\n\u2028\u2029]+", " ", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    # Keep refs as provided by LLM, only normalize bracket format: [id:jp1,us2] -> [jp1,us2]
    text = re.sub(r"\[id:\s*([^\]]+)\]", r"[\1]", text, flags=re.IGNORECASE)

    def _norm_ref_block(m):
        raw = m.group(1)
        ids = re.findall(r"[a-z]{2,}\d+", raw, flags=re.IGNORECASE)
        if not ids:
            return m.group(0)
        seen = set()
        out = []
        for x in ids:
            k = x.lower()
            if k in seen:
                continue
            seen.add(k)
            out.append(k)
        return "[" + ",".join(out) + "]"

    text = re.sub(r"\[([^\]]+)\]", _norm_ref_block, text)
    return text


def fix_idea_ref_prefix(text: str, country_prefix: str) -> str:
    """アイデアdesc内の [xxNNN] 参照の国コードが間違っていたら正しいprefixに修正する。
    例: country_prefix='cn' のとき [jp506] → [cn506]
    """
    if not text or not country_prefix:
        return text
    # 国コード2文字+数字 の形式のみ対象
    def _fix(m):
        ids = re.findall(r"([a-z]{2})(\d+)", m.group(1), flags=re.IGNORECASE)
        if not ids:
            return m.group(0)
        fixed = []
        for prefix, num in ids:
            if prefix.lower() != country_prefix.lower():
                fixed.append(f"{country_prefix.lower()}{num}")
            else:
                fixed.append(f"{prefix.lower()}{num}")
        return "[" + ",".join(fixed) + "]"
    return re.sub(r"\[([a-z]{2}\d+(?:,[a-z]{2}\d+)*)\]", _fix, text, flags=re.IGNORECASE)


def strip_idea_refs(text: str) -> str:
    """Idea descriptions are standalone concepts; remove news-id reference marks."""
    if not text:
        return text
    text = re.sub(r"\s*\[[a-z]{2,5}\d+(?:\s*,\s*[a-z]{2,5}\d+)*\]", "", text, flags=re.IGNORECASE)
    # Remove malformed LLM variants such as "[jp eu1462]" before appending
    # the validated sourceNewsIds block.
    text = re.sub(
        r"\s*\[(?:[a-z]{2,5}\s+)?[a-z]{2,5}\d+(?:\s*,\s*[a-z]{2,5}\d+)*\]",
        "",
        text,
        flags=re.IGNORECASE,
    )
    return re.sub(r"\s{2,}", " ", text).strip()


def analysis_ref_coverage_ok(text: str):
    parts = [p.strip() for p in re.findall(r"[^。！？!?]+[。！？!?]?", text or "") if p.strip()]
    if not parts:
        return False
    ref_pat = re.compile(r"\[\s*[a-z]{2,}\d+(?:\s*,\s*[a-z]{2,}\d+)*\s*\]", re.IGNORECASE)
    covered = sum(1 for p in parts if ref_pat.search(p))
    return covered >= len(parts)


def build_allowed_news_ids(source_items: list):
    return {
        (it.get("newsId", "") or "").strip().lower()
        for it in (source_items or [])
        if (it.get("newsId", "") or "").strip()
    }


def filter_analysis_refs_to_allowed(text: str, allowed_ids: set[str]):
    if not text or not allowed_ids:
        return text

    def _filter_block(m):
        ids = re.findall(r"[a-z]{2,}\d+", m.group(1), flags=re.IGNORECASE)
        if not ids:
            return m.group(0)
        seen = set()
        kept = []
        for x in ids:
            k = x.lower()
            if k in seen:
                continue
            seen.add(k)
            if k in allowed_ids:
                kept.append(k)
        if not kept:
            return ""
        return "[" + ",".join(kept[:3]) + "]"

    out = re.sub(r"\[([^\]]+)\]", _filter_block, text)
    out = re.sub(r"\s{2,}", " ", out).strip()
    return out


def analysis_unique_refs(text: str) -> set[str]:
    ids = set()
    for block in re.findall(r"\[([^\]]+)\]", text or ""):
        for x in re.findall(r"[a-z]{2,}\d+", block, flags=re.IGNORECASE):
            ids.add(x.lower())
    return ids


def ensure_analysis_image_refs(text: str, source_items: list, min_image_refs: int = 3) -> str:
    """Ensure analysis references include enough image-backed news for the UI source strip."""
    if not text:
        return text
    image_ids = [
        (it.get("newsId", "") or "").strip().lower()
        for it in select_analysis_items(source_items, limit=8)
        if (it.get("newsId", "") or "").strip() and it.get("img")
    ]
    if not image_ids:
        return text
    existing = analysis_unique_refs(text)
    have = [nid for nid in image_ids if nid in existing]
    need = min(min_image_refs, len(image_ids))
    if len(have) >= need:
        return text
    missing = [nid for nid in image_ids if nid not in existing][: need - len(have)]
    if not missing:
        return text
    suffix = " 関連画像: " + " ".join(f"[{nid}]" for nid in missing)
    if text.endswith(("。", "！", "？", "!", "?")):
        return text + suffix
    return text + "。" + suffix


def bracket_bare_allowed_ids(text: str, allowed_ids: set[str]) -> str:
    """Convert bare news ids like eu1069 to [eu1069] so the HTML can link them."""
    if not text or not allowed_ids:
        return text
    out = text
    for nid in sorted(allowed_ids, key=len, reverse=True):
        # Python \w treats Japanese characters as word chars, so an ID next to
        # Japanese text (例: 技術cn123の進化) would not be detected. Restrict
        # boundaries to ASCII id characters instead.
        pat = re.compile(rf"(?<![\[A-Za-z0-9_]){re.escape(nid)}(?![\]A-Za-z0-9_])", flags=re.IGNORECASE)
        out = pat.sub(f"[{nid}]", out)
    return out


def rewrite_analysis_with_refs(endpoint: str, model: str, country: str, analysis_text: str, source_items: list):
    id_lines = []
    for it in source_items[:12]:
        nid = it.get("newsId", "")
        if not nid:
            continue
        id_lines.append(f"- {nid}: {it.get('title', '')}")
    if not id_lines:
        return analysis_text
    prompt = (
        "次の考察文を、文ごとに関連ニュースID参照を付けて書き直してください。\n"
        "重要ルール:\n"
        "1) 各文に必ず1つ以上の参照を付ける（利用可能ID一覧にあるIDのみ使用すること）\n"
        "2) 参照は [jp123,in332] 形式のみ（id:は禁止、[1][2]などの番号のみの参照は禁止）\n"
        "3) 参照は文末にまとめず、関連語の直後に自然に挿入する\n"
        "4) 参照はその文に関係するIDのみ（1文あたり1〜3件）\n"
        "5) 文章は日本語のまま、内容改変は最小限\n"
        "6) 最終的な考察文のみを返す。説明・解説・注釈・思考過程は一切含めない\n"
        "7) ---や###などの区切り文字の後に説明を追記しない\n\n"
        f"国: {country}\n"
        f"利用可能ID一覧:\n" + "\n".join(id_lines) + "\n\n"
        f"原文:\n{analysis_text}\n"
    )
    try:
        out = call_llm(endpoint, model, prompt)
        out = re.sub(r"^```(?:json)?\s*|\s*```$", "", out.strip(), flags=re.IGNORECASE | re.MULTILINE)
        # --- 以降の解説・メタ文を除去
        out = re.split(r"\s*---\s*", out)[0].strip()
        # [1] [2] などの番号のみ参照が残っていたら全削除
        out = re.sub(r"\[\d+\]", "", out).strip()
        out = normalize_analysis_refs_per_sentence(out)
        return out if out else analysis_text
    except Exception:
        return analysis_text


def ensure_analysis_ref_quality(
    endpoint: str,
    model: str,
    country: str,
    analysis_text: str,
    source_items: list,
    min_unique_refs: int = 4,
) -> str:
    if not analysis_text:
        return analysis_text
    allowed_ids = build_allowed_news_ids(source_items)
    selected_items = select_analysis_items(source_items, limit=6)
    selected_ids = [it.get("newsId", "").strip().lower() for it in selected_items if it.get("newsId")]
    required_unique = min(min_unique_refs, len(selected_ids))

    def _clean_candidate(value: str) -> str:
        value = re.sub(r"^```(?:json)?\s*|\s*```$", "", (value or "").strip(), flags=re.IGNORECASE | re.MULTILINE)
        value = re.split(r"\s*---\s*", value)[0].strip()
        value = re.sub(r"\[\d+\]", "", value).strip()
        value = bracket_bare_allowed_ids(value, allowed_ids)
        return filter_analysis_refs_to_allowed(normalize_analysis_refs_per_sentence(value), allowed_ids)

    def _quality_ok(value: str) -> bool:
        return analysis_ref_coverage_ok(value) and len(analysis_unique_refs(value)) >= required_unique

    text = _clean_candidate(analysis_text)
    if _quality_ok(text):
        return text
    if not selected_items:
        return text

    id_lines = "\n".join(
        f"- {it.get('newsId')}: {it.get('title', '')} / {it.get('desc', '')[:90]}"
        for it in selected_items
        if it.get("newsId")
    )
    prompt = (
        f"次の考察を、豊田合成の{EDITION.subject_name}開発向けの示唆として書き直してください。\n"
        f"目的はニュース要約ではなく、その国のトレンド・そこから考えられること・求められる{EDITION.subject_name}部品/素材/製品価値を明確にすることです。\n"
        "重要ルール:\n"
        f"1) 参照IDは必ず [jp123] 形式。裸のIDは禁止。国は {country}。\n"
        f"2) 可能な限り次の候補から{required_unique}件以上の異なるIDを使う。ただし文と直接関係するIDのみ使う。\n"
        "3) 各文に1〜3件のIDを関連語の直後に入れる。文末に大量にまとめない。\n"
        "4) 300〜420字程度。わかりやすい日本語。説明・注釈・コードフェンスは禁止。\n\n"
        f"候補ニュース:\n{id_lines}\n\n"
        f"元の考察:\n{analysis_text}\n"
    )
    try:
        repaired = call_llm(endpoint, model, prompt)
        repaired = _clean_candidate(repaired)
        if repaired:
            text = repaired
    except Exception:
        pass
    if _quality_ok(text):
        return text

    strict_prompt = (
        "以下の候補ニュースだけを根拠に、考察を最初から作り直してください。\n"
        "絶対条件:\n"
        f"- {required_unique}件以上の異なる候補IDを必ず使う\n"
        "- すべての参照は [jp123] 形式のみ。裸ID、id:、番号参照は禁止\n"
        "- 各文に1〜3件のIDを入れる。IDのない文は禁止\n"
        f"- 300〜420字程度。豊田合成の{EDITION.subject_name}開発向けに、トレンド・示唆・求められる{EDITION.subject_name}部品/素材/製品価値を書く。ニュースが少ない日は短くし一般化しない\n"
        "- 考察文のみ返す\n\n"
        f"国: {country}\n"
        f"候補ニュース:\n{id_lines}\n"
    )
    try:
        repaired = _clean_candidate(call_llm(endpoint, model, strict_prompt))
        if repaired:
            text = repaired
    except Exception:
        pass
    return text


def shorten_analysis_with_llm(endpoint: str, model: str, analysis_text: str, limit: int = ANALYSIS_CHAR_LIMIT) -> str:
    """analysis_text が limit 字を超えていたら LLM で圧縮して返す。"""
    if not analysis_text or len(analysis_text) <= limit:
        return analysis_text
    prompt = (
        f"次の考察文を{limit}字以内に圧縮してください。\n"
        "ルール:\n"
        "1) 文中のニュースID参照（例: [cn506]）はそのまま保持する\n"
        "2) 重要なキーワードと示唆だけ残し、冗長な説明は削る\n"
        "3) 日本語のまま。句点で終わること\n"
        f"4) 必ず{limit}字以内（ID参照の[...]も字数に含める）\n"
        "5) 考察文のみ返す。説明・注釈は不要\n\n"
        f"原文:\n{analysis_text}\n"
    )
    try:
        out = call_llm(endpoint, model, prompt).strip()
        out = re.sub(r"^```.*?\n|```$", "", out, flags=re.MULTILINE).strip()
        out = re.split(r"\s*---\s*", out)[0].strip()
        if out and len(out) <= limit:
            return out
    except Exception:
        pass
    # フォールバック: 文単位で切り詰め
    sentences = re.findall(r"[^。！？!?]+[。！？!?]", analysis_text)
    result = ""
    for s in sentences:
        if len(result) + len(s) <= limit:
            result += s
        else:
            break
    return result or analysis_text[:limit]


def preserve_analysis_citations(before_shortening: str, final_text: str, allowed_ids: set[str], limit: int = ANALYSIS_CHAR_LIMIT) -> str:
    """Keep a validated original if compression damaged citations; never invent refs."""
    def valid(text):
        refs = analysis_unique_refs(text)
        return bool(text and has_japanese_text(text) and analysis_ref_coverage_ok(text)
                    and refs and refs.issubset(allowed_ids))

    if valid(before_shortening) and not valid(final_text):
        print("[ANALYSIS] Shortened citation validation failed; retained the validated original "
              f"({len(before_shortening)} characters, target {limit}, over_target={len(before_shortening) > limit}).")
        return before_shortening
    return final_text


def insert_insight(js_text: str, new_entry: str):
    # insert after opening bracket
    return re.sub(r"window\.DAILY_INSIGHTS\s*=\s*\[\s*", f"window.DAILY_INSIGHTS = [\n{new_entry}\n", js_text, count=1)


def remove_insight_by_date(js_text: str, date_key: str):
    marker = f'date: "{date_key}"'
    pos = js_text.find(marker)
    if pos == -1:
        return js_text
    # find object start
    start = js_text.rfind("{", 0, pos)
    if start == -1:
        return js_text
    # find matching object end by brace depth (string-aware)
    depth = 0
    in_str = False
    esc = False
    end = -1
    for i in range(start, len(js_text)):
        ch = js_text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end == -1:
        return js_text
    # consume trailing comma/space/newline
    while end < len(js_text) and js_text[end] in " \t\r\n,":
        end += 1
    return js_text[:start] + js_text[end:]


def has_insight_for_date(js_text: str, date_key: str):
    return re.search(rf'\bdate:\s*"{re.escape(date_key)}"', js_text) is not None


def extract_insight_object_section(js_text: str, date_key: str, section_name: str) -> str:
    """Return a raw braced section such as analysis from one dated insight entry."""
    marker = f'date: "{date_key}"'
    date_pos = js_text.find(marker)
    if date_pos == -1:
        return ""
    section_match = re.search(rf'\b{re.escape(section_name)}\s*:\s*\{{', js_text[date_pos:])
    if not section_match:
        return ""
    start = date_pos + section_match.end() - 1
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(js_text)):
        ch = js_text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return js_text[start : i + 1]
    return ""


def js_escape(value: str):
    s = str(value or "")
    s = s.replace("\u2028", " ").replace("\u2029", " ")
    s = s.replace("\\", "\\\\")
    s = s.replace("\"", "\\\"")
    s = s.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n")
    return s


def load_idea_angles() -> list[str]:
    try:
        data = json.loads(IDEA_ANGLES_PATH.read_text(encoding="utf-8"))
        return data.get("angles", [])
    except Exception:
        return []


def load_tg_products() -> list[dict]:
    try:
        data = json.loads(TG_PRODUCTS_PATH.read_text(encoding="utf-8"))
        return data.get("products", [])
    except Exception:
        return []


def _item_for_prompt(it: dict) -> str:
    news_id = it.get("newsId", "")
    id_text = f"id={news_id} / " if news_id else ""
    score = it.get("interiorScore")
    score_text = f" / productScore={int(score)}" if score is not None else ""
    title = str(it.get("title", ""))[:80]
    desc = str(it.get("desc", ""))[:140]
    tags = it.get("tags", "")
    if isinstance(tags, list):
        tags = ",".join(tags[:5])
    else:
        tags = str(tags)[:80]
    img_text = " / image=available" if it.get("img") else " / image=missing"
    if it.get("imageInterior") is True:
        img_text += f"/{EDITION.id}"
    elif it.get("imageInterior") is False:
        img_text += "/not-target"
    return f"- {id_text}{title} / {desc} / {tags}{score_text}{img_text}"


def _non_passenger_vehicle_kind(item: dict) -> str:
    tags = " ".join(item.get("tags", []) if isinstance(item.get("tags"), list) else [str(item.get("tags", ""))])
    blob = f"{item.get('title', '')} {item.get('desc', '')} {tags}".lower()
    if any(term in blob for term in ["\u30d0\u30a4\u30af", "\u30aa\u30fc\u30c8\u30d0\u30a4", "\u4e8c\u8f2a\u8eca", "\u30b9\u30af\u30fc\u30bf\u30fc", "motorcycle", "motorbike", "two-wheeler"]):
        return "motorcycle"
    if any(term in blob for term in ["\u8def\u7dda\u30d0\u30b9", "\u89b3\u5149\u30d0\u30b9", "\u9ad8\u901f\u30d0\u30b9", "\u30b9\u30af\u30fc\u30eb\u30d0\u30b9"]):
        return "bus"
    if re.search(r"\b(?:buses|bus|coaches|coach)\b", blob) or ("\u30d0\u30b9" in blob and "\u30d0\u30b9\u30b1\u30c3\u30c8" not in blob):
        return "bus"
    if re.search(r"\b(?:trucks?|lorries|lorry)\b", blob) or ("\u30c8\u30e9\u30c3\u30af" in blob and "\u30b5\u30a6\u30f3\u30c9\u30c8\u30e9\u30c3\u30af" not in blob):
        return "truck"
    return ""


def select_analysis_items(items: list, limit: int = 6) -> list[dict]:
    if EDITION.id == "exterior":
        return exterior_rules.select_items(items, limit)
    def _score(it: dict):
        tags = " ".join(it.get("tags", []) if isinstance(it.get("tags"), list) else [str(it.get("tags", ""))])
        interior_score = it.get("interiorScore")
        interior_score = float(interior_score) if interior_score is not None else 0.0
        blob = f"{it.get('title', '')} {it.get('desc', '')} {tags}".lower()
        keyword_bonus = 0
        for kw in ["シート", "ディスプレイ", "HMI", "HUD", "コックピット", "コンソール", "ステア", "イルミ", "安全", "新素材", "音響", "快適", "操作"]:
            if kw.lower() in blob:
                keyword_bonus += 4
        image_bonus = 18 if it.get("imageInterior") is True else (8 if it.get("img") else -20)
        weak_penalty = 0
        for kw in ["不正", "調査", "投資", "株", "補助金", "販売台数", "工場", "生産台数"]:
            if kw.lower() in blob:
                weak_penalty += 10
        if _non_passenger_vehicle_kind(it):
            weak_penalty += 80
        return (interior_score + keyword_bonus + image_bonus - weak_penalty, len(it.get("desc", "")))

    candidates = [
        it for it in items
        if it.get("newsId") and it.get("title") and it.get("desc")
    ]
    image_candidates = [
        it for it in candidates
        if it.get("img")
    ]
    preferred = [
        it for it in candidates
        if not _non_passenger_vehicle_kind(it)
        and (it.get("imageInterior") is True or (it.get("interiorScore") or 0) >= 55)
    ]
    # Prefer strong interior signals, but do not stop at 1-2 items. Country
    # analysis needs enough source breadth to explain a market trend.
    preferred.sort(key=_score, reverse=True)
    fallback = [it for it in image_candidates if it not in preferred]
    last_resort = [it for it in candidates if it not in preferred and it not in fallback]
    fallback.sort(key=_score, reverse=True)
    last_resort.sort(key=_score, reverse=True)
    return (preferred + fallback + last_resort)[:limit]


def select_idea_anchor_groups(items: list, need_count: int = 2) -> list[list[dict]]:
    if EDITION.id == "exterior":
        candidates = [item for item in exterior_rules.select_items(items, limit=len(items))
                      if (item.get("contentCategory") == "trend" and item.get("trendTopic") in exterior_rules.TREND_TOPICS)
                      or not _is_out_of_scope_idea(f"{item.get('title', '')} {item.get('desc', '')}")]
        # Different concepts may share the only available source article.
        return [[candidates[i % len(candidates)]] for i in range(max(0, need_count))] if candidates else []
    def _score(it: dict):
        tags = " ".join(it.get("tags", []) if isinstance(it.get("tags"), list) else [str(it.get("tags", ""))])
        interior_score = it.get("interiorScore")
        interior_score = float(interior_score) if interior_score is not None else 0.0
        blob = f"{it.get('title', '')} {it.get('desc', '')} {tags}".lower()
        keyword_bonus = 0
        for kw in ["ディスプレイ", "HMI", "HUD", "コックピット", "コンソール", "ステア", "イルミ", "安全", "新素材", "音響", "ドアトリム", "インパネ"]:
            if kw.lower() in blob:
                keyword_bonus += 5
        image_bonus = 8 if it.get("imageInterior") is True else 0
        weak_penalty = 0
        for kw in ["不正", "調査", "投資", "株", "補助金", "市場需要", "販売台数"]:
            if kw.lower() in blob:
                weak_penalty += 12
        return (interior_score + keyword_bonus + image_bonus - weak_penalty, len(it.get("desc", "")))

    all_candidates = [
        it for it in items
        if it.get("newsId")
        and it.get("title")
        and it.get("desc")
        and not _non_passenger_vehicle_kind(it)
        and not _is_out_of_scope_idea(f"{it.get('title', '')} {it.get('desc', '')}")
    ]
    preferred = [
        it
        for it in all_candidates
        if it.get("imageInterior") is True or (it.get("interiorScore") or 0) >= 65
    ]
    fallback = [it for it in all_candidates if it not in preferred]
    preferred.sort(key=_score, reverse=True)
    fallback.sort(key=_score, reverse=True)
    # Keep lower-scoring interior news available for the second idea rather
    # than assigning the same anchor twice when only one strong item exists.
    candidates = preferred + fallback
    if not candidates:
        return []
    groups = []
    used = set()
    for _ in range(max(1, need_count)):
        primary = next((it for it in candidates if it.get("newsId") not in used), candidates[0])
        used.add(primary.get("newsId"))
        groups.append([primary])
    return groups


def prepare_exterior_idea_sources(ideas: list, source_items: list) -> list:
    """Keep valid citations per idea, including citations shared by other ideas."""
    allowed_ids = build_allowed_news_ids(source_items)
    prepared = []
    for original in ideas:
        idea = dict(original)
        raw_ids = idea.get("sourceNewsIds") or []
        if not isinstance(raw_ids, list):
            raise RuntimeError("Exterior idea sourceNewsIds must be a list")
        source_ids = list(dict.fromkeys(str(value).strip().lower() for value in raw_ids))
        unknown = [value for value in source_ids if value not in allowed_ids]
        if unknown:
            raise RuntimeError("Exterior idea references unknown news IDs: " + ", ".join(unknown))
        if not source_ids:
            # Recover only references already written by the model. Assigning an
            # arbitrary anchor here can disguise a genuinely unsourced idea.
            source_ids = sorted(analysis_unique_refs(idea.get("desc", "")))
            if set(source_ids) - allowed_ids:
                raise RuntimeError("Exterior idea references unknown news IDs")
        if not source_ids:
            raise RuntimeError("Exterior idea has no valid source article")
        if analysis_unique_refs(idea.get("desc", "")) - set(source_ids):
            raise RuntimeError("Exterior idea description disagrees with sourceNewsIds")
        idea["sourceNewsIds"] = source_ids[:2]
        desc = strip_idea_refs(idea.get("desc", ""))
        numbers = {re.sub(r"^[a-z]+", "", value) for value in idea["sourceNewsIds"]}
        # [50] is a malformed duplicate of the explicitly supplied jp50. Do not
        # infer a country for unknown numeric references or remove measurements.
        desc = re.sub(r"\[\s*(\d+)\s*\]", lambda m: "" if m.group(1) in numbers else m.group(0), desc)
        if re.search(r"\[\s*\d+(?:\s*,\s*\d+)*\s*\]", desc):
            raise RuntimeError("Exterior idea has an unresolved numeric news reference")
        idea["desc"] = f"{desc.strip()} [{','.join(idea['sourceNewsIds'])}]"
        prepared.append(idea)
    return prepared


def validated_exterior_ideas(raw_ideas, source_items, history_ideas=(), retained=()):
    """Keep independent valid ideas when another generated idea is unusable."""
    kept = list(retained)
    for candidate in raw_ideas if isinstance(raw_ideas, list) else []:
        if len(kept) >= 2:
            break
        if not isinstance(candidate, dict):
            continue
        picked = dedupe_ideas([candidate], list(history_ideas), limit=1)
        if not picked or not all(has_japanese_text(picked[0].get(field, "")) for field in ("title", "desc")):
            continue
        text = f"{picked[0]['title']} {picked[0]['desc']}"
        if any(_similarity(text, f"{idea.get('title', '')} {idea.get('desc', '')}") >= 0.78 for idea in kept):
            continue
        try:
            kept.extend(prepare_exterior_idea_sources(picked, source_items))
        except RuntimeError as error:
            print(f"[IDEAS] rejected invalid source references: {error}")
    return kept


def checkpoint_exterior_progress(checkpoint, date_key, country, source_items, analysis, ideas, dry_run=False):
    """Save accepted components before any further model call can fail."""
    valid_analysis = analysis if exterior_analysis_complete(analysis, source_items) else ""
    if not valid_analysis and not ideas:
        return
    checkpoint["countries"][country] = {
        "fingerprint": exterior_checkpoint_fingerprint(date_key, source_items),
        "analysis": valid_analysis, "ideas": ideas,
    }
    if not dry_run:
        write_exterior_checkpoint(date_key, checkpoint)


def make_country_prompt(
    date_key: str,
    country: str,
    items: list,
    prompt_template: str,
    history_ideas: list | None = None,
    need_count: int = 2,
    idea_anchor_groups: list[list[dict]] | None = None,
):
    if EDITION.id == "exterior":
        return exterior_rules.make_country_prompt(date_key, country, items, prompt_template, history_ideas, need_count, idea_anchor_groups, _item_for_prompt)
    summary_lines = [f"[{country}] 件数: {len(items)}"]
    analysis_items = select_analysis_items(items, limit=6)
    for it in analysis_items:
        summary_lines.append(_item_for_prompt(it))
    summary = "\n".join(summary_lines)
    idea_anchor_groups = idea_anchor_groups or select_idea_anchor_groups(items, need_count=need_count)
    anchor_lines = []
    for idx, group in enumerate(idea_anchor_groups[:need_count], start=1):
        ids = ",".join([it.get("newsId", "") for it in group if it.get("newsId")])
        anchor_lines.append(f"ideas[{idx - 1}] anchor IDs: {ids}")
        for it in group[:2]:
            anchor_lines.append(_item_for_prompt(it))
    anchors_text = "\n".join(anchor_lines) if anchor_lines else "なし"
    analysis_ids = [it.get("newsId", "") for it in analysis_items if it.get("newsId")]
    analysis_image_ids = [it.get("newsId", "") for it in analysis_items if it.get("newsId") and it.get("img")]
    duplicate_guard = build_duplicate_guard_text(history_ideas or [], max_items=12)
    angles = load_idea_angles()
    angle = random.choice(angles) if angles else ""
    angle_instruction = f"    - 【今回の発想切り口】1件目は「{angle}」の視点で発想すること（ただしニュース内容と関連させること）\n" if angle else ""
    tg_products = [
        product
        for product in load_tg_products()
        if not _is_out_of_scope_idea(f"{product.get('name', '')} {product.get('desc', '')}")
    ]
    tg_product = random.choice(tg_products) if tg_products else None
    tg_constraint = ""
    if tg_product:
        tg_constraint = (
            f"    - ideas[1]（2件目）は豊田合成の既存製品「{tg_product['name']}」（{tg_product['desc'][:40]}…）を起点に、ニュース内容と絡めて発展させること\n"
        )
    extra = textwrap.dedent(f"""

    【対象日】{date_key}
    【対象国】{country}
    【ニュース概要】
    {summary}
    【アイデア用アンカーニュース】
    {anchors_text}
    {duplicate_guard}
    出力は必ずJSONのみで返してください。
    JSON以外の文字や説明、コードフェンスは一切出力しないでください。
    形式:
    {{
      "analysis": "...",
      "ideas": [
        {{"title": "...", "desc": "(120〜180文字・うれしさを含む)", "imagePrompt": "...", "sourceNewsIds": ["..."]}},
        {{"title": "...", "desc": "(120〜180文字・うれしさを含む)", "imagePrompt": "...", "sourceNewsIds": ["..."]}}
      ]
    }}

    制約:
    - {need_count}件提案
{angle_instruction}{tg_constraint}    - 過去アイデアの言い換え・焼き直しは禁止
    - 各ideasは、対応する【アイデア用アンカーニュース】だけを根拠にする
    - 1つのideasが参照してよいニュースは最大2件まで。アンカー外のニュースや市場全体の一般論を根拠にしない
    - アンカーニュースの主題となる部品・材料・操作上の課題を企画の中核にする。無関係な技術を足して別ジャンルの製品へ飛躍しない
    - 各ideasのdescには、アンカーニュース固有の車名・部品名・技術名・数値のいずれかを必ず1つ以上入れる
    - descの第1文で、対応するアンカーニュース固有の車名または技術名を明記する
    - sourceNewsIdsには、対応するanchor IDsのみを入れる
    - シート、座席、座面、背もたれ、ヘッドレストなどの座席製品は企画対象外。ニュースに含まれていてもideasでは提案しない
    - フロントグリル、バンパー、フェンダーなどの外装製品も企画対象外
    - 企画対象はインパネ、センターコンソール、ドアトリム、ステアリング/HMI、照明、安全表示、内装加飾・材料、音響・静粛、ウェザーストリップ等を優先する
    - うれしさを必ず明記
    - titleは日本語を基本に20文字以内の短い名称のみ（英語のみは禁止、説明・括弧書き・句点を含めない）
    - descは120〜180文字程度。長い背景説明ではなく、何を作るか・誰がうれしいかを端的に書く
    - imagePromptは必須。英語で、1枚の画像として何を見せるかを具体化する
    - imagePromptはアイデアごとに構図・対象物・素材・光・色を変え、似た画像にならないようにする
    - titleとdescにマークダウン記法（**太字**等）を使用しない
    - analysisは300〜420字程度。単なるニュース要約ではなく、豊田合成の内装開発室向けの示唆として書く
    - analysisは新聞の短い解説記事のように、見出しのある材料をつなぎ、読みやすい自然な文章にする
    - analysisに「以下に提示します」「考察を提示します」「豊田合成内装開発室向けのトレンド考察」などの前置き・メタ説明は禁止
    - analysisは「その国で何がトレンドか」「そこから何が考えられるか」「今後どんな内装部品・素材・操作体験が求められるか」を、わかりやすい言葉で書く
    - analysisでは具体ニュースをできるだけ幅広く使う。利用可能なら4〜6件の異なるニュースIDを取り上げる。候補ID: {",".join(analysis_ids) or "なし"}
    - analysisの参照IDは、できるだけ画像がある候補IDから選ぶ。画像あり候補ID: {",".join(analysis_image_ids) or "なし"}
    - 画像がある候補IDが3件以上ある場合、analysisでは最低3件以上の画像あり候補IDを参照する
    - analysisは開発者が次に検討できる言葉にする（例: 低価格EV向けの触感品質、後席快適、物理操作と大画面の両立、環境材、照明、安全表示など）
    - analysisは文ごとに関連ニュースID参照を付ける（例: ...素材[jp123]...）
    - 参照は文末にまとめず、関連語の直後に入れる
    - 参照IDはその文に直接関係するIDのみ（1文あたり1〜3件）
    - id: という文字は書かない
    - 「画像のように」「写真の通り」「上の画像」など、画像だけに依存する表現は禁止。必ず何が写っているか、何が示唆かを文章で説明する
    - 中国・インドなど海外ニュースでも、画像だけで説明せず、車内の部品・素材・表示・操作体験を文章で具体化する
    - ideasのdesc末尾にはsourceNewsIdsと同じID参照を [jp123] の形式で付ける
    - analysisに説明・解説・注釈・思考過程を含めない。考察文のみ出力する
    """)
    return extra


def write_exterior_publication_status(items, dry_run=False, require_empty_collection=False):
    """Publish a zero count only with a matching, completed collection receipt."""
    if EDITION.id != "exterior":
        return
    dates = sorted({str(item.get("date", "")) for item in items if item.get("date")})
    receipt_path = EDITION.runtime_dir / "collection_result.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8-sig")) if receipt_path.exists() else {}
    from dailynews.digest import validated_issue_context, selected_news_ids
    issue_context = validated_issue_context(receipt, items)
    expected_dates = [date.strip() for date in os.environ.get("TARGET_DATES", "").split(",") if date.strip()]
    receipt_dates = receipt.get("target_dates", [])
    receipt_matches = (receipt.get("edition_id") == "exterior" and receipt.get("completed") is True
                       and bool(receipt_dates) and (not expected_dates or sorted(receipt_dates) == sorted(expected_dates)))
    if require_empty_collection:
        if not receipt_matches or receipt.get("selected_count") != 0 or not receipt.get("source_count"):
            raise RuntimeError("Empty exterior publication has no matching completed zero-news collection receipt")
        dates = receipt_dates
    elif issue_context:
        if not receipt_matches:
            raise RuntimeError("Exterior issue does not match requested processing dates")
        dates = receipt_dates
    elif receipt_matches and set(dates).issubset(set(receipt_dates)) and receipt.get("selected_count") == len(items):
        # A completed collection may have no matching articles on its final date.
        dates = receipt_dates
    if not dates:
        raise RuntimeError("Exterior publication has no processed date")
    status = {"edition_id": "exterior", "processed_through": max(dates), "target_dates": dates,
              "selected_count": len(items), "updated_at": datetime.now().astimezone().isoformat(),
              "status": "no_matching_news" if not items else "published"}
    if issue_context:
        status.update(issue_context, selected_news_ids=selected_news_ids(items))
    if dry_run:
        return status
    for target, initial in ((NEWS_PATH, 'window.NEWS_UPDATED_AT = "";\nwindow.LOADED_NEWS_DATA = [\n];\n'),
                            (INSIGHTS_PATH, 'window.DAILY_INSIGHTS = [\n];\n')):
        if not target.exists():
            target.write_text(initial, encoding="utf-8")
    (EDITION.content_dir / "publication_status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return status


def exterior_analysis_failure_reasons(analysis, source_items):
    """Reference checks are structural; source support must still be reviewed."""
    text = str(analysis or "").strip()
    if not text:
        return ["EMPTY_ANALYSIS"]
    reasons = []
    if not has_japanese_text(text):
        reasons.append("NOT_JAPANESE")
    if not analysis_ref_coverage_ok(text):
        reasons.append("UNCITED_SENTENCES")
    refs = analysis_unique_refs(text)
    allowed = build_allowed_news_ids(source_items)
    if not refs & allowed:
        reasons.append("NO_VALID_CITATIONS")
    if refs - allowed:
        reasons.append("UNKNOWN_CITATIONS")
    return reasons


def exterior_analysis_complete(analysis, source_items):
    """A completed region must have Japanese analysis tied to its own articles."""
    return not exterior_analysis_failure_reasons(analysis, source_items)


def cited_exterior_analysis_prefix(analysis, source_items):
    """Only omit an uncited closing inference, never a caveat or a middle sentence."""
    text = str(analysis or "").strip()
    parts = [part.strip() for part in re.findall(r"[^。！？!?]+[。！？!?]?", text) if part.strip()]
    # The UI's optional source strip is not a cited analytical sentence.
    auxiliary = re.compile(r"^(?:関連画像|関連ニュース|参考(?:資料|記事)?|出典)\s*[:：]")
    substantive = [part for part in parts if not auxiliary.match(part)]
    uncited = [i for i, part in enumerate(substantive) if not analysis_unique_refs(part)]
    if not uncited:
        return ""
    first = uncited[0]
    if first < 2 or uncited != list(range(first, len(substantive))):
        return ""
    inference = re.compile(r"^(?:これら(?:から|を踏まえ|の動向から)|こうした(?:動向|変化|傾向)|"
                           r"このことから|以上(?:から|を踏まえ)|豊田合成(?:の|として)|開発(?:上|では|には))")
    caveat = re.compile(r"ただし|一方|しかし|なお|ものの|とは限ら|断定|未確認|不明|保証|注意|制約|例外")
    if any(not inference.match(part) or caveat.search(part) for part in substantive[first:]):
        return ""
    kept = substantive[:first]
    if not all(has_japanese_text(part) for part in kept):
        return ""
    result = "".join(kept)
    allowed = build_allowed_news_ids(source_items)
    if (not exterior_analysis_complete(result, source_items)
            or len(analysis_unique_refs(result)) < min(3, len(allowed))):
        return ""
    return result


def write_exterior_analysis_failure(date_key, country, source_items, candidates, repair_error=""):
    """Keep failed generated text privately, without HTTP errors, prompts or secrets."""
    def safe_text(value):
        text = str(value or "")
        for name, secret in os.environ.items():
            if re.search(r"(?:API_KEY|TOKEN|SECRET|PASSWORD)", name, re.IGNORECASE) and len(secret) >= 8:
                text = text.replace(secret, "[REDACTED]")
        return text[:12000]

    safe_date = re.sub(r"[^0-9_-]", "_", str(date_key))[:32]
    safe_country = country if country in {"jp", "cn", "in", "us", "eu"} else "unknown"
    target = EDITION.runtime_dir / f"insights_analysis_failure_{safe_date}_{safe_country}.json"
    payload = {
        "schema_version": 1, "edition_id": "exterior", "date": safe_date, "country": safe_country,
        "source_ids": sorted(build_allowed_news_ids(source_items)),
        "fingerprint": exterior_checkpoint_fingerprint(date_key, source_items),
        "repair_error": repair_error if repair_error == "LLM_UNAVAILABLE" else "",
        "candidates": [{"stage": stage, "text": safe_text(text),
                        "reasons": exterior_analysis_failure_reasons(text, source_items)}
                       for stage, text in candidates],
    }
    temporary = target.with_suffix(".json.tmp")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, target)
    except OSError:
        print(f"[ANALYSIS] {safe_country}: private diagnostic could not be saved.")


def finalize_exterior_analysis(endpoint, model, country, date_key, analysis, source_items,
                               prior_candidates=(), dry_run=False, max_attempts=1):
    """Bounded repair with conservative reuse; never invent citation IDs."""
    if exterior_analysis_complete(analysis, source_items):
        return analysis
    candidates = [("final", analysis)] + [(f"prior_{i}", text) for i, text in enumerate(prior_candidates)]
    for _, previous in reversed(candidates[1:]):
        if exterior_analysis_complete(previous, source_items):
            print(f"[ANALYSIS] {country}: retained an earlier citation-validated analysis.")
            return previous
    allowed = build_allowed_news_ids(source_items)
    evidence = "\n".join(
        f"- {str(item['newsId']).lower()}: {str(item.get('title', ''))[:180]} / {str(item.get('desc', ''))[:600]}"
        for item in source_items if str(item.get("newsId", "")).lower() in allowed
    )
    prompt = (
        "次の外装開発向け考察を、記事本文の要約に照らして最後に一度だけ修正してください。\n"
        "各文（最後の示唆文も含む）に、その文を直接支える候補記事IDを [eu123] 形式で付ける。\n"
        "引用を付けるためだけに無関係なIDを割り当てない。根拠のない主張は削除する。\n"
        "事実と開発上の仮説を区別し、予測・開発車・市場の対象範囲や留保を維持する。\n"
        "内装操作の話を外装部品の採用事実へ変えない。新しい数値・性能・採用実績を作らない。\n"
        "300〜420字程度を目安とし、記事が少なければ短くする。根拠と引用の正確さを優先する。\n"
        "日本語の考察本文だけを返す。各文の引用は句点より前に置く。説明・注釈・関連画像一覧は禁止。\n"
        f"地域: {country}。使用可能ID: {','.join(sorted(allowed))}\n"
        f"候補記事:\n{evidence}\n\n修正対象:\n{str(analysis or '')[:6000]}\n"
    )
    repair_error = ""
    if allowed:
        try:
            repaired = call_llm(endpoint, model, prompt).strip()
            repaired = re.sub(r"^```(?:text|markdown)?\s*|\s*```$", "", repaired, flags=re.IGNORECASE)
            repaired = normalize_analysis_refs_per_sentence(bracket_bare_allowed_ids(repaired, allowed))
            candidates.append(("final_repair", repaired))
            if exterior_analysis_complete(repaired, source_items):
                print(f"[ANALYSIS] {country}: final citation repair accepted.")
                return repaired
        except Exception:
            repair_error = "LLM_UNAVAILABLE"
    # Only reuse original text, never trim a failed repair that may have added claims.
    for _, original in candidates[:1 + len(prior_candidates)]:
        prefix = cited_exterior_analysis_prefix(original, source_items)
        if prefix:
            print(f"[ANALYSIS] {country}: omitted an uncited closing inference; "
                  f"retained {len(analysis_unique_refs(prefix))} source references.")
            return prefix
    # A second, shorter response is useful when the model keeps adding uncited
    # conclusions. Revalidate the full text; never attach citations in code.
    if allowed and max_attempts > 1 and repair_error != "LLM_UNAVAILABLE":
        retry_prompt = prompt + (
            "\n前回も引用のない文が残りました。今回は短い日本語3文以内とし、"
            "各文を直接支える候補記事IDを必ず句点より前に付けてください。"
            "根拠を示せない結論は書かない。事実と仮説の区別や留保は残す。\n"
        )
        try:
            repaired = call_llm(endpoint, model, retry_prompt).strip()
            repaired = re.sub(r"^```(?:text|markdown)?\s*|\s*```$", "", repaired, flags=re.IGNORECASE)
            repaired = normalize_analysis_refs_per_sentence(bracket_bare_allowed_ids(repaired, allowed))
            candidates.append(("final_repair_2", repaired))
            if exterior_analysis_complete(repaired, source_items):
                print(f"[ANALYSIS] {country}: second bounded citation repair accepted.")
                return repaired
        except Exception:
            repair_error = "LLM_UNAVAILABLE"
    reasons = ",".join(exterior_analysis_failure_reasons(analysis, source_items))
    print(f"[ANALYSIS] {country}: final validation failed ({reasons}).")
    if not dry_run:
        write_exterior_analysis_failure(date_key, country, source_items, candidates, repair_error)
    return analysis


def exterior_existing_insights_complete(insights_text, date_key, items, published_articles=()):
    """Never report a complete issue while an existing region lacks its two ideas."""
    from dailynews.exabase import select_ideas, string_field
    # Editorial consolidation retains alias records so already published
    # analyses/images remain attributable. Only that issue's valid aliases
    # can support existing insights; future generation still uses unique items.
    items = list(items)
    by_id = {article["id"]: article for article in reversed(list(published_articles))}
    ids = {item.get("newsId") for item in items}
    for article in published_articles:
        if (not article.get("duplicateOf") or article.get("digestDate", article.get("date")) != date_key
                or article.get("id") in ids):
            continue
        target = article
        visited = set()
        while target and target.get("duplicateOf"):
            if target["id"] in visited:
                target = None
                break
            visited.add(target["id"])
            target = by_id.get(target["duplicateOf"])
        if target and target.get("date", "9999") <= date_key:
            items.append({**article, "newsId": article["id"]})
            ids.add(article["id"])
    analysis = extract_insight_object_section(insights_text, date_key, "analysis")
    ideas = select_ideas(insights_text, date_key)
    for country in {item["country"] for item in items}:
        sources = [item for item in items if item["country"] == country]
        allowed = build_allowed_news_ids(sources)
        text, _ = string_field(analysis, country)
        valid_ideas = [idea for idea in ideas if idea.sources and set(idea.sources).issubset(allowed)]
        if not exterior_analysis_complete(text, sources) or len(valid_ideas) != 2:
            return False
    return True


def exterior_checkpoint_fingerprint(date_key, source_items):
    fields = [{key: item.get(key) for key in ("newsId", "url", "date", "title", "desc")} for item in source_items]
    payload = json.dumps(["exterior", date_key, fields], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def exterior_checkpoint_path(date_key):
    safe_date = re.sub(r"[^0-9_-]", "_", str(date_key))
    return EDITION.runtime_dir / f"insights_checkpoint_{safe_date}.json"


def read_exterior_checkpoint(date_key):
    try:
        data = json.loads(exterior_checkpoint_path(date_key).read_text(encoding="utf-8"))
        if data.get("edition_id") == "exterior" and data.get("date") == date_key and isinstance(data.get("countries"), dict):
            return data
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return {"edition_id": "exterior", "date": date_key, "countries": {}}


def write_exterior_checkpoint(date_key, checkpoint):
    target = exterior_checkpoint_path(date_key)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, target)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--edition", choices=("interior", "exterior"), default=EDITION.id)
    ap.add_argument("--sheet", default=None)
    ap.add_argument("--skip-insights", action="store_true")
    ap.add_argument("--skip-images", action="store_true", help="Publish text without running optional image generation")
    ap.add_argument("--skip-html", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--replace-insights", action="store_true")
    ap.add_argument(
        "--replace-ideas-only",
        action="store_true",
        help="Regenerate ideas for the target date while preserving its existing analysis",
    )
    ap.add_argument("--fix-existing", action="store_true", help="Fix url/source for existing entries using CSV rows")
    ap.add_argument("--llm-endpoint", default=os.getenv("LLM_ENDPOINT", "http://127.0.0.1:1234/v1/chat/completions"))
    ap.add_argument("--llm-model", default=os.getenv("LLM_MODEL", "qwen/qwen3.5-9b"))
    args = ap.parse_args()
    if args.edition != EDITION.id:
        configure_edition(args.edition)
    if not args.dry_run:
        EDITION.ensure_directories()

    sheet_path = Path(args.sheet) if args.sheet else DEFAULT_SHEET
    if EDITION.id == "exterior" and sheet_path.resolve().parent != EDITION.runtime_dir.resolve():
        raise ValueError("Exterior publication CSV must be inside runtime/exterior; refusing an interior or shared input")
    if not sheet_path.exists():
        print(f"sheet not found: {sheet_path}")
        sys.exit(1)

    header, rows, enc = read_csv_any(sheet_path)
    header = normalize_header(header)

    idx_country = find_col(header, "国")
    idx_date = find_col(header, "日付")
    idx_title = find_col(header, "タイトル（日本語）")
    if idx_title is None:
        idx_title = find_col(header, "タイトル")
    idx_desc = find_col(header, "内容（日本語）")
    if idx_desc is None:
        idx_desc = find_col(header, "内容")
    idx_image = find_col_exact(header, "画像URL") or find_col(header, "画像URL")
    idx_url = find_col_exact(header, "URL")
    if idx_url is None:
        idx_url = find_col(header, "URL")
        if idx_url is not None and "画像" in header[idx_url]:
            idx_url = find_col_exact(header, "URL")
    idx_source = find_col(header, "ソース")
    if idx_source is None:
        idx_source = find_col(header, "出典サイト", "出展サイト")
    idx_llm = find_col(header, "LLM判定")
    idx_img判定 = find_col(header, "画像判定")
    idx_interior_score = find_col(header, "製品関連度", "外装関連度", "内装関連度", "関連度スコア")
    idx_interior_reason = find_col(header, "製品判定理由", "外装判定理由", "内装判定理由")
    idx_original_title = find_col_exact(header, "タイトル")
    idx_original_desc = find_col_exact(header, "内容")
    idx_content_category = find_col_exact(header, "記事区分")
    idx_trend_topic = find_col_exact(header, "トレンド分類")
    idx_related_urls = find_col_exact(header, "関連URL")
    evidence_indices = {key: find_col_exact(header, column) for key, column in EVIDENCE_COLUMNS.items()}

    def get(row, idx):
        if idx is None:
            return ""
        return row[idx].strip() if idx < len(row) else ""

    items = []
    non_paper_rows = 0
    rows_with_relevance_signal = 0
    for row in rows:
        country_raw = get(row, idx_country)
        date_val = get(row, idx_date)
        title = get(row, idx_title)
        desc = get(row, idx_desc)
        img = get(row, idx_image)
        url = get(row, idx_url)
        source = get(row, idx_source)
        llm_val = get(row, idx_llm)
        img_val = get(row, idx_img判定)
        interior_score = parse_score_0_100(get(row, idx_interior_score))
        interior_reason = get(row, idx_interior_reason)
        content_category = get(row, idx_content_category) or "product"
        trend_topic = get(row, idx_trend_topic) if content_category == "trend" else ""
        if EDITION.id == "exterior" and (content_category not in ("product", "trend")
                                          or (content_category == "trend" and trend_topic not in exterior_rules.TREND_TOPICS)):
            raise RuntimeError(f"Invalid exterior editorial category: {url}")
        country = map_country(country_raw) or "jp"
        # Also guard resumed CSV publication, which does not run the summarizer.
        original = f"{get(row, idx_original_title)} {get(row, idx_original_desc)}"
        title, title_prices = repair_indian_price_units(title, original, country)
        desc, desc_prices = repair_indian_price_units(desc, original, country)
        for before, after in title_prices + desc_prices:
            print(f"[CURRENCY_UNIT_FIXED] {before} -> {after}: {url}")
        if country != "paper":
            non_paper_rows += 1
            if ("対象" in llm_val) or interior_score is not None:
                rows_with_relevance_signal += 1

        llm_is_target = llm_val.strip() == "対象"
        if EDITION.id == "exterior" and (not llm_is_target or interior_score is None or interior_score < EDITION.config.get("selection", {}).get("minimum_score", 60)):
            continue
        if EDITION.id == "exterior" and content_category == "trend" and interior_score < EDITION.config.get("selection", {}).get("trend_minimum_score", 65):
            continue
        # sheet2_llm_targets.csv is the final country-quota selection. Do not
        # drop selected target/paper rows only because the thumbnail itself was
        # judged as non-interior; the article can still be relevant.
        if (
            idx_img判定 is not None
            and img_val
            and "あり" not in img_val
            and not llm_is_target
            and country != "paper"
            and (interior_score is None or interior_score < 55)
        ):
            continue
        if not img and EDITION.id == "interior":
            continue
        if not title or not url:
            continue
        if is_bad_generated_text(title) or is_bad_generated_text(desc):
            print(f"Skip placeholder summary: {url}")
            continue
        tags = generate_tags(f"{title} {desc}")
        items.append(apply_item_overrides({
            "edition": EDITION.id,
            "country": country,
            "date": date_val,
            "title": title,
            "desc": desc,
            "img": img,
            "url": url,
            "source": source,
            "tags": tags,
            "contentCategory": content_category,
            "trendTopic": trend_topic,
            "relatedUrls": related_source_urls(get(row, idx_related_urls), url),
            "interiorScore": interior_score,
            "interiorReason": interior_reason,
            "llmDecision": llm_val.strip(),
            "originalTitle": get(row, idx_original_title),
            "originalDesc": get(row, idx_original_desc),
            "evidence": {key: get(row, idx) for key, idx in evidence_indices.items()},
            "imageInterior": True if img_val and "あり" in img_val else (False if img_val and "なし" in img_val else None),
        }))

    news_text = read_text_any(NEWS_PATH) if NEWS_PATH.exists() else 'window.NEWS_UPDATED_AT = "";\nwindow.LOADED_NEWS_DATA = [\n];\n'
    existing_urls, max_ids = parse_existing_news(news_text)
    existing_url_keys = set(publication_url_id_map(news_text))
    items = validate_editorial_publication(items, existing_url_keys, load_feedback_snapshot(EDITION), EDITION.id)
    items = unique_publication_items(items)
    validate_japanese_news_items(items)
    issue_context = None
    if EDITION.id == "exterior":
        from dailynews.digest import validated_issue_context
        receipt_path = EDITION.runtime_dir / "collection_result.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8-sig")) if receipt_path.exists() else {}
        issue_context = validated_issue_context(receipt, items)
        if issue_context:
            expected_dates = [value.strip() for value in os.environ.get("TARGET_DATES", "").split(",") if value.strip()]
            if expected_dates and sorted(expected_dates) != sorted(receipt["target_dates"]):
                raise RuntimeError("Exterior issue does not match requested processing dates")
            for item in items:
                item["digestDate"] = issue_context["issue_date"]

    if non_paper_rows and idx_llm is not None and rows_with_relevance_signal == 0:
        raise RuntimeError(
            "sheet2 has no LLM/interior relevance signals. Abort to avoid publishing weak non-interior articles."
        )

    if not items:
        if EDITION.id == "exterior":
            write_exterior_publication_status([], args.dry_run, require_empty_collection=True)
        print("No items to append after filtering.")
        return
    dates_in_items = sorted({it.get("date") for it in items if it.get("date")})
    if dates_in_items:
        print(f"Loaded {len(items)} items from sheet: {sheet_path} (dates: {dates_in_items[0]} ~ {dates_in_items[-1]})")
    else:
        print(f"Loaded {len(items)} items from sheet: {sheet_path} (date: unknown)")

    if not args.dry_run:
        from ニュース収集.source_highlights import enrich_items
        # Only newly published rows: never re-fetch the entire news archive.
        highlight_targets = [it for it in items if not existing_url_keys.intersection(publication_item_url_keys(it))]
        if highlight_targets:
            if EDITION.id == "exterior":
                enrich_items(highlight_targets, cache_path=EDITION.runtime_dir / "source_highlights.json")
            else:
                enrich_items(highlight_targets)

    new_items = []
    for it in items:
        if existing_url_keys.intersection(publication_item_url_keys(it)):
            continue
        prefix = it["country"]
        next_id = max_ids.get(prefix, 0) + 1
        max_ids[prefix] = next_id
        it_id = f"{prefix}{next_id}" if prefix != "paper" else f"paper{next_id}"
        text_blob = f"{it['title']} {it['desc']}"
        tags = generate_tags(text_blob)
        source = derive_source(it["url"], it["source"])
        note = ""
        if any(k in it["img"] for k in ["unsplash", "placeholder", "thumb_default"]):
            note = "※イメージ画像"
        extra_lines = []
        if it.get("relatedUrls"):
            extra_lines.append(f'                relatedUrls: {json.dumps(it["relatedUrls"], ensure_ascii=False)},')
        if EDITION.id == "exterior":
            extra_lines.append(f'                edition: "exterior", productScore: {int(it["interiorScore"])}, exteriorScore: {int(it["interiorScore"])},')
            if it.get("digestDate"):
                extra_lines.append(f'                digestDate: "{js_escape(it["digestDate"])}",')
            extra_lines.append(f'                contentCategory: "{js_escape(it["contentCategory"])}", trendTopic: "{js_escape(it["trendTopic"])}",')
        for field in ("sourceExcerpt", "sourceExcerptEnd", *SELECTION_FIELDS.values(), "selectionPolicyVersion"):
            if it.get(field):
                extra_lines.append(f'                {field}: "{js_escape(it[field])}",')
        if it.get("interiorScore") is not None:
            extra_lines.append(f'                interiorScore: {int(it["interiorScore"])},')
        if it.get("interiorReason"):
            extra_lines.append(f'                interiorReason: "{js_escape(it["interiorReason"])}",')
        if it.get("imageInterior") is not None:
            extra_lines.append(f'                imageInterior: {str(bool(it["imageInterior"])).lower()},')
        extra_block = "\n".join(extra_lines)
        if extra_block:
            extra_block = "\n" + extra_block
        item_block = textwrap.dedent(f"""
            {{
                id: "{js_escape(it_id)}",
                title: "{js_escape(it['title'])}",
                desc: "{js_escape(it['desc'])}",
                url: "{js_escape(it['url'])}",
                source: "{js_escape(source)}",
                date: "{js_escape(it['date'])}",
                tags: {json.dumps(tags, ensure_ascii=False)},
{extra_block}
                country: "{js_escape(it['country'])}",
                img: "{js_escape(it['img'])}",
                note: "{js_escape(note)}"
            }},
        """).strip("\n")
        new_items.append(item_block)
        existing_url_keys.update(publication_item_url_keys(it))

    if not new_items and not args.fix_existing:
        print("No new items to append (all URLs exist). Continue for insights if enabled.")
        if items:
            print(f"Sample incoming URL: {items[0].get('url')}")
        print(f"Existing URL count: {len(existing_urls)}")
    else:
        print(f"New items to append: {len(new_items)}")

    # group by date
    items_by_date = {}
    new_dates = []
    for block in new_items:
        m = re.search(r"date:\s*\"([^\"]+)\"", block)
        if m:
            date_key = m.group(1)
            new_dates.append(date_key)
        else:
            date_key = "unknown"
        items_by_date.setdefault(date_key, []).append("    " + block.replace("\n", "\n    "))
    all_dates = sorted({it.get("date") for it in items if it.get("date")})

    updated_news_text = update_news_updated_at(news_text)
    if new_items:
        updated_news_text = append_news_items(updated_news_text, items_by_date)
    if args.fix_existing:
        updated_news_text = fix_existing_entries(updated_news_text, items)
    updated_news_text = merge_related_sources(updated_news_text, items)
    news_id_map = publication_url_id_map(updated_news_text)
    for it in items:
        it["newsId"] = news_id_map.get(normalize_article_url(it.get("url", "")), "")

    if not args.dry_run:
        NEWS_PATH.write_text(updated_news_text, encoding="utf-8")

    # Update NEW date range
    if not args.skip_html:
        html_text = read_text_any(HTML_PATH if HTML_PATH.exists() else ROOT / "内装製品デイリーニュース.html")
        if new_dates:
            start = min(new_dates)
            end = max(new_dates)
            html_text = update_new_date_range(html_text, start, end)
            if not args.dry_run:
                HTML_PATH.write_text(html_text, encoding="utf-8")

    # Insights generation
    insight_dates = ([issue_context["issue_date"]] if issue_context else (new_dates if new_dates else all_dates))
    insight_start = min(insight_dates) if insight_dates else None
    latest_date = max(insight_dates) if insight_dates else None
    insight_date_label = (
        f"{insight_start}〜{latest_date}"
        if insight_start and latest_date and insight_start != latest_date
        else latest_date
    )
    if not args.skip_insights:
        insights_text = read_text_any(INSIGHTS_PATH) if INSIGHTS_PATH.exists() else 'window.DAILY_INSIGHTS = [\n];\n'
        insight_exists = (
            has_insight_for_date(insights_text, insight_date_label)
            or has_insight_for_date(insights_text, latest_date)
            if latest_date
            else False
        )
        if insight_date_label and insight_exists and not (args.replace_insights or args.replace_ideas_only):
            if EDITION.id == "exterior" and not exterior_existing_insights_complete(
                    insights_text, insight_date_label, items, parse_published_news(updated_news_text)):
                raise RuntimeError(f"Existing exterior insights for {insight_date_label} lack regional analysis or two sourced ideas. Use --replace-insights to rebuild the issue.")
            print(f"Insights for {insight_date_label} already exists. Use --replace-insights to overwrite.")
        elif insight_date_label:
            preserved_analysis = ""
            if args.replace_ideas_only:
                preserved_analysis = extract_insight_object_section(
                    insights_text,
                    insight_date_label,
                    "analysis",
                )
                if not preserved_analysis:
                    raise RuntimeError(
                        f"Cannot replace ideas only: analysis for {insight_date_label} was not found."
                    )
            grouped = {"jp": [], "cn": [], "in": [], "us": [], "eu": []}
            for it in items:
                if it["country"] in grouped:
                    grouped[it["country"]].append(it)
            prompt_template = read_text_any(PROMPT_PATH) if PROMPT_PATH.exists() else ""
            analysis_out = {}
            ideas_out = {}
            draft_parts = []
            attempted_insight_countries = 0
            use_checkpoint = EDITION.id == "exterior" and not args.replace_ideas_only
            checkpoint = (read_exterior_checkpoint(insight_date_label) if use_checkpoint and not args.replace_insights
                          else {"edition_id": "exterior", "date": insight_date_label, "countries": {}})
            for key in ["jp", "cn", "in", "us", "eu"]:
                if not grouped.get(key):
                    continue
                attempted_insight_countries += 1
                retained_analysis = ""
                retained_ideas = []
                if use_checkpoint:
                    previous = checkpoint["countries"].get(key, {})
                    if (isinstance(previous, dict)
                            and previous.get("fingerprint") == exterior_checkpoint_fingerprint(insight_date_label, grouped[key])):
                        if exterior_analysis_complete(previous.get("analysis"), grouped[key]):
                            retained_analysis = previous["analysis"]
                        retained_ideas = validated_exterior_ideas(previous.get("ideas", []), grouped[key])
                        analysis_out[key] = retained_analysis
                        ideas_out[key] = retained_ideas
                        checkpoint_exterior_progress(checkpoint, insight_date_label, key, grouped[key],
                                                     retained_analysis, retained_ideas, args.dry_run)
                        if retained_analysis and len(retained_ideas) == 2:
                            print(f"[IDEAS] {key}: reused completed exterior checkpoint")
                            continue
                        print(f"[IDEAS] {key}: resumed partial checkpoint "
                              f"(analysis={bool(retained_analysis)}, ideas={len(retained_ideas)}/2)")
                history_ideas = extract_recent_ideas_by_country(insights_text, key, limit=60)
                idea_anchor_groups = select_idea_anchor_groups(grouped[key], need_count=2)
                prompt = make_country_prompt(
                    insight_date_label,
                    key,
                    grouped[key],
                    prompt_template,
                    history_ideas=history_ideas + retained_ideas,
                    need_count=2 - len(retained_ideas),
                    idea_anchor_groups=idea_anchor_groups[len(retained_ideas):],
                )
                if retained_analysis:
                    prompt += "\n【最優先】考察は検証済みなのでanalysisは空文字。不足しているideasだけを生成すること。\n"
                elif len(retained_ideas) == 2:
                    prompt += "\n【最優先】2案は検証済みなのでideasは空配列。analysisだけを生成すること。\n"
                if args.replace_ideas_only:
                    prompt += (
                        "\n【最優先】今回は既存の考察を保持してideasだけを差し替える。"
                        "analysisは空文字にし、ideasの生成にのみ集中すること。\n"
                    )
                print(f"[IDEAS] {key}: generating with {args.llm_model}...")
                llm_text = ""
                try:
                    llm_text = call_llm(args.llm_endpoint, args.llm_model, prompt)
                    data = extract_json_block(llm_text)
                    if not data:
                        data = repair_json_with_llm(args.llm_endpoint, args.llm_model, llm_text)
                except Exception as e:
                    data = None
                    print(f"LLM error ({key}): {e}")
                if data and isinstance(data, dict):
                    if use_checkpoint:
                        deduped = validated_exterior_ideas(data.get("ideas", []), grouped[key], history_ideas, retained_ideas)
                        initial_analysis = retained_analysis or normalize_analysis_refs_per_sentence(data.get("analysis", ""))
                        checkpoint_exterior_progress(checkpoint, insight_date_label, key, grouped[key],
                                                     initial_analysis, deduped, args.dry_run)
                    if not args.replace_ideas_only and not retained_analysis:
                        analysis_text = normalize_analysis_refs_per_sentence(data.get("analysis", ""))
                        allowed_ids = build_allowed_news_ids(grouped[key])
                        analysis_text = filter_analysis_refs_to_allowed(analysis_text, allowed_ids)
                        analysis_initial = analysis_text
                        if analysis_text and not analysis_ref_coverage_ok(analysis_text):
                            analysis_text = rewrite_analysis_with_refs(
                                args.llm_endpoint,
                                args.llm_model,
                                key,
                                analysis_text,
                                grouped[key],
                            )
                        analysis_text = ensure_analysis_ref_quality(
                            args.llm_endpoint,
                            args.llm_model,
                            key,
                            analysis_text,
                            grouped[key],
                        )
                        analysis_final = filter_analysis_refs_to_allowed(
                            normalize_analysis_refs_per_sentence(analysis_text),
                            allowed_ids,
                        )
                        analysis_before_shortening = analysis_final
                        analysis_final = shorten_analysis_with_llm(
                            args.llm_endpoint, args.llm_model, analysis_final
                        )
                        analysis_final = filter_analysis_refs_to_allowed(
                            normalize_analysis_refs_per_sentence(
                                bracket_bare_allowed_ids(analysis_final, allowed_ids)
                            ),
                            allowed_ids,
                        )
                        analysis_final = filter_analysis_refs_to_allowed(
                            normalize_analysis_refs_per_sentence(
                                ensure_analysis_image_refs(analysis_final, grouped[key])
                            ),
                            allowed_ids,
                        )
                        analysis_final = preserve_analysis_citations(analysis_before_shortening, analysis_final, allowed_ids)
                        if EDITION.id == "exterior":
                            analysis_final = finalize_exterior_analysis(
                                args.llm_endpoint, args.llm_model, key, insight_date_label,
                                analysis_final, grouped[key],
                                prior_candidates=(analysis_initial, analysis_before_shortening),
                                dry_run=args.dry_run,
                                max_attempts=2,
                            )
                        analysis_out[key] = analysis_final
                    if not use_checkpoint:
                        deduped = dedupe_ideas(data.get("ideas", []), history_ideas, limit=2)
                    else:
                        checkpoint_exterior_progress(checkpoint, insight_date_label, key, grouped[key],
                                                     analysis_out.get(key), deduped, args.dry_run)
                    for retry_index in range(2 if use_checkpoint else 1):
                        if len(deduped) >= 2:
                            break
                        retry_prompt = make_country_prompt(
                            insight_date_label,
                            key,
                            grouped[key],
                            prompt_template,
                            history_ideas=(history_ideas + deduped),
                            need_count=(2 - len(deduped)),
                            idea_anchor_groups=idea_anchor_groups[len(deduped):],
                        )
                        if args.replace_ideas_only or use_checkpoint:
                            retry_prompt += (
                                "\n【最優先】analysisは空文字にし、不足しているideasだけを生成すること。\n"
                            )
                        try:
                            retry_text = call_llm(args.llm_endpoint, args.llm_model, retry_prompt)
                            retry_data = extract_json_block(retry_text)
                            if not retry_data:
                                retry_data = repair_json_with_llm(args.llm_endpoint, args.llm_model, retry_text)
                        except Exception as e:
                            retry_data = None
                            print(f"LLM retry error ({key}): {e}")
                        if retry_data and isinstance(retry_data, dict):
                            if use_checkpoint:
                                deduped = validated_exterior_ideas(retry_data.get("ideas", []), grouped[key], history_ideas, deduped)
                                checkpoint_exterior_progress(checkpoint, insight_date_label, key, grouped[key],
                                                             analysis_out.get(key), deduped, args.dry_run)
                            else:
                                add_ideas = dedupe_ideas(
                                    retry_data.get("ideas", []),
                                    history_ideas + deduped,
                                    limit=(2 - len(deduped)),
                                )
                                deduped.extend(add_ideas)
                    allowed_ids = build_allowed_news_ids(grouped[key])
                    if EDITION.id == "exterior":
                        deduped = prepare_exterior_idea_sources(deduped[:2], grouped[key])
                    else:
                        for i, idea in enumerate(deduped[:2]):
                            anchor_ids = []
                            if i < len(idea_anchor_groups):
                                anchor_ids = [x.get("newsId", "").lower() for x in idea_anchor_groups[i] if x.get("newsId")]
                            raw_ids = [
                                str(x).strip().lower()
                                for x in (idea.get("sourceNewsIds") or [])
                                if str(x).strip().lower() in anchor_ids
                            ]
                            source_ids = raw_ids[:2] if raw_ids else anchor_ids[:2]
                            idea["sourceNewsIds"] = source_ids
                            if source_ids and not re.search(r"\[[a-z]{2,5}\d+(?:\s*,\s*[a-z]{2,5}\d+)*\]", idea.get("desc", ""), flags=re.IGNORECASE):
                                idea["desc"] = f"{strip_idea_refs(idea.get('desc', ''))} [{','.join(source_ids)}]"
                    ideas_out[key] = deduped[:2]
                    print(f"[IDEAS] {key}: accepted {len(ideas_out[key])}/2")
                    if use_checkpoint:
                        checkpoint_exterior_progress(checkpoint, insight_date_label, key, grouped[key],
                                                     analysis_out.get(key), ideas_out[key], args.dry_run)
                else:
                    draft_parts.append(f"[{key}]\n{llm_text.strip() if llm_text else 'LLM出力に失敗しました。'}\n")
            if use_checkpoint:
                incomplete = [key for key, source_items in grouped.items()
                              if source_items and (not exterior_analysis_complete(analysis_out.get(key), source_items)
                                                   or len(ideas_out.get(key, [])) != 2)]
                if incomplete:
                    raise RuntimeError(
                        "Exterior insights incomplete for: " + ", ".join(incomplete)
                        + "; accepted regional components are checkpointed, publication marker was not advanced."
                    )
            if args.replace_ideas_only:
                missing_ideas = [
                    key
                    for key in ["jp", "cn", "in", "us", "eu"]
                    if grouped.get(key) and len(ideas_out.get(key, [])) < 2
                ]
                if missing_ideas:
                    raise RuntimeError(
                        "Ideas-only replacement aborted; fewer than two ideas were generated for: "
                        + ", ".join(missing_ideas)
                    )
            if analysis_out or ideas_out:
                max_id = parse_insights_max_id(insights_text)
                entry_lines = ["    {", f"        date: \"{insight_date_label}\","]
                if preserved_analysis:
                    entry_lines.append(f"        analysis: {preserved_analysis},")
                else:
                    entry_lines.append("        analysis: {")
                    for key in ["jp", "cn", "in", "us", "eu"]:
                        val = analysis_out.get(key, "")
                        if val:
                            entry_lines.append(f"            {key}: \"{js_escape(val)}\",")
                    entry_lines.append("        },")
                entry_lines.append("        ideas: {")
                for key in ["jp", "cn", "in", "us", "eu"]:
                    idea_list = ideas_out.get(key, [])
                    if not idea_list:
                        continue
                    entry_lines.append(f"            {key}: [")
                    for idea in idea_list[:2]:
                        max_id += 1
                        title = js_escape(idea.get("title", ""))
                        source_ids = [
                            str(x).strip().lower()
                            for x in (idea.get("sourceNewsIds") or [])
                            if re.fullmatch(r"[a-z]{2,5}\d+", str(x).strip(), flags=re.IGNORECASE)
                        ][:2]
                        if EDITION.id == "exterior" and (not source_ids or not set(source_ids).issubset(build_allowed_news_ids(grouped[key]))):
                            raise RuntimeError(f"Exterior idea cannot be published without valid source articles: {key}")
                        desc_text = strip_idea_refs(fix_idea_ref_prefix(idea.get("desc", ""), key))
                        if source_ids:
                            desc_text = f"{desc_text} [{','.join(source_ids)}]"
                        desc = js_escape(desc_text)
                        image_prompt = js_escape(idea.get("imagePrompt", ""))
                        source_ids_js = json.dumps(source_ids, ensure_ascii=False)
                        if EDITION.id == "exterior":
                            entry_lines.append(f'                {{ id: {max_id}, img: "", title: "{title}", desc: "{desc}", sourceNewsIds: {source_ids_js} }},')
                        else:
                            entry_lines.append(
                                f"                {{ id: {max_id}, img: \"{PLACEHOLDER_IMG}\", title: \"{title}\", desc: \"{desc}\", imagePrompt: \"{image_prompt}\", sourceNewsIds: {source_ids_js} }},"
                            )
                    entry_lines.append("            ],")
                entry_lines.append("        }")
                entry_lines.append("    },")
                new_entry = "\n".join(entry_lines)
                updated_insights = insights_text
                if (args.replace_insights or args.replace_ideas_only) and insight_exists:
                    updated_insights = remove_insight_by_date(updated_insights, insight_date_label)
                    if latest_date and latest_date != insight_date_label:
                        updated_insights = remove_insight_by_date(updated_insights, latest_date)
                updated_insights = insert_insight(updated_insights, new_entry)
                if not args.dry_run:
                    INSIGHTS_PATH.write_text(updated_insights, encoding="utf-8")
            elif attempted_insight_countries:
                raise RuntimeError(
                    f"Insights generation failed for {insight_date_label}: no valid LLM output for any country."
                )
            if draft_parts:
                draft_key = str(insight_date_label).replace("〜", "_").replace("～", "_").replace("~", "_")
                draft_path = (EDITION.runtime_dir if EDITION.id == "exterior" else ROOT) / f"insights_draft_{draft_key}.txt"
                if not args.dry_run:
                    draft_path.write_text("\n".join(draft_parts), encoding="utf-8")
                print(f"Insights draft saved: {draft_path}")

    if EDITION.id == "exterior":
        if not args.dry_run and not INSIGHTS_PATH.exists():
            INSIGHTS_PATH.write_text('window.DAILY_INSIGHTS = [\n];\n', encoding="utf-8")
        write_exterior_publication_status(items, args.dry_run)
    if not args.dry_run and not args.skip_images and insight_date_label:
        from dailynews.idea_images import optional_images
        image_result = optional_images(EDITION, issue_date=insight_date_label)
        print(f"[IMAGES] {EDITION.id}: " + json.dumps({
            "status": image_result["status"],
            "generated": image_result.get("generated", 0),
            "cached": image_result.get("cached", 0),
            "providers": image_result.get("providers", {}),
            "errors": image_result.get("errors", []),
        }, ensure_ascii=False))
    print("Done.")


if __name__ == "__main__":
    main()
