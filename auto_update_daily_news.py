import argparse
import csv
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

ROOT = Path(__file__).resolve().parent
NEWS_PATH = ROOT / "news_data.js"
INSIGHTS_PATH = ROOT / "insights_data.js"
HTML_PATH = ROOT / "内装製品デイリーニュース.html"
PROMPT_PATH = ROOT / ".agent" / "prompts" / "insights_generation_prompt.md"
DEFAULT_SHEET = ROOT / "ニュース収集" / "sheet2_llm_targets.csv"
IDEA_ANGLES_PATH = ROOT / "ニュース収集" / "idea_angles.json"
TG_PRODUCTS_PATH = ROOT / "ニュース収集" / "tg_products.json"

ENCODINGS = ["utf-8-sig", "utf-8", "cp932", "utf-16"]
ANALYSIS_CHAR_LIMIT = 300

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


def apply_item_overrides(item: dict):
    override = ITEM_OVERRIDES.get(item.get("url", ""))
    if not override:
        return item
    out = dict(item)
    for key, value in override.items():
        if value:
            out[key] = value
    return out


def generate_tags(text: str):
    tags = []
    for pattern, tag in TAG_RULES:
        if re.search(pattern, text, flags=re.IGNORECASE):
            if tag not in tags:
                tags.append(tag)
    return tags[:6]


def has_japanese_text(text: str):
    return bool(re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", str(text or "")))


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
    updated = js_text
    for it in items:
        title = it.get("title", "")
        img = it.get("img", "")
        url = it.get("url", "")
        source = derive_source(url, it.get("source", ""))
        if not title or not img or not url:
            continue
        esc_title = re.escape(title)
        # Fix url within the entry that matches title
        pattern_url = rf'(title:\s*"{esc_title}"[\s\S]*?url:\s*")([^"]*)(")'
        def repl_url(m):
            return f'{m.group(1)}{url}{m.group(3)}'
        updated = re.sub(pattern_url, repl_url, updated, count=1)
        # Fix source within the same entry
        pattern_source = rf'(title:\s*"{esc_title}"[\s\S]*?source:\s*")([^"]*)(")'
        def repl_source(m):
            return f'{m.group(1)}{source}{m.group(3)}'
        updated = re.sub(pattern_source, repl_source, updated, count=1)
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


def _pick_model(endpoint: str, fallback: str):
    try:
        resp = requests.get(_models_endpoint(endpoint), timeout=15)
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
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": "<think>\n</think>\n"},
        ],
        "temperature": 0.7,
        "max_tokens": 1200,
    }
    resp = requests.post(endpoint, json=payload, timeout=180)
    if resp.status_code >= 400:
        # retry with auto-selected model
        alt_model = _pick_model(endpoint, chosen_model)
        if alt_model and alt_model != chosen_model:
            payload["model"] = alt_model
            resp = requests.post(endpoint, json=payload, timeout=180)
    if resp.status_code >= 400:
        # Try /v1/responses as fallback
        responses_endpoint = re.sub(r"/chat/completions$", "/responses", endpoint)
        responses_payload = {
            "model": payload["model"],
            "input": prompt,
            "temperature": 0.7,
            "max_output_tokens": 1200,
        }
        resp = requests.post(responses_endpoint, json=responses_payload, timeout=180)
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
    ideas = []
    pattern_country = re.compile(rf"{re.escape(country)}\s*:\s*\[(.*?)\]\s*,", flags=re.DOTALL)
    pattern_idea = re.compile(
        r'title:\s*"([^"]*)"\s*,\s*desc:\s*"([^"]*)"(?:\s*,\s*imagePrompt:\s*"([^"]*)")?',
        flags=re.DOTALL,
    )
    for cm in pattern_country.finditer(insights_text):
        block = cm.group(1)
        for im in pattern_idea.finditer(block):
            ideas.append(
                {
                    "title": (im.group(1) or "").strip(),
                    "desc": (im.group(2) or "").strip(),
                    "imagePrompt": (im.group(3) or "").strip(),
                }
            )
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
    score_text = f" / interiorScore={int(score)}" if score is not None else ""
    title = str(it.get("title", ""))[:80]
    desc = str(it.get("desc", ""))[:140]
    tags = it.get("tags", "")
    if isinstance(tags, list):
        tags = ",".join(tags[:5])
    else:
        tags = str(tags)[:80]
    return f"- {id_text}{title} / {desc} / {tags}{score_text}"


def select_idea_anchor_groups(items: list, need_count: int = 2) -> list[list[dict]]:
    def _score(it: dict):
        tags = " ".join(it.get("tags", []) if isinstance(it.get("tags"), list) else [str(it.get("tags", ""))])
        interior_score = it.get("interiorScore")
        interior_score = float(interior_score) if interior_score is not None else 0.0
        blob = f"{it.get('title', '')} {it.get('desc', '')} {tags}".lower()
        keyword_bonus = 0
        for kw in ["シート", "ディスプレイ", "HMI", "コックピット", "コンソール", "ステア", "イルミ", "安全", "新素材", "音響"]:
            if kw.lower() in blob:
                keyword_bonus += 5
        image_bonus = 8 if it.get("imageInterior") is True else 0
        weak_penalty = 0
        for kw in ["不正", "調査", "投資", "株", "補助金", "市場需要", "販売台数"]:
            if kw.lower() in blob:
                weak_penalty += 12
        return (interior_score + keyword_bonus + image_bonus - weak_penalty, len(it.get("desc", "")))

    candidates = [
        it for it in items
        if it.get("newsId")
        and it.get("title")
        and it.get("desc")
        and (it.get("imageInterior") is True or (it.get("interiorScore") or 0) >= 65)
    ]
    if not candidates:
        candidates = [it for it in items if it.get("newsId") and it.get("title") and it.get("desc")]
    candidates.sort(key=_score, reverse=True)
    if not candidates:
        return []
    groups = []
    used = set()
    for _ in range(max(1, need_count)):
        primary = next((it for it in candidates if it.get("newsId") not in used), candidates[0])
        used.add(primary.get("newsId"))
        groups.append([primary])
    return groups


def make_country_prompt(
    date_key: str,
    country: str,
    items: list,
    prompt_template: str,
    history_ideas: list | None = None,
    need_count: int = 2,
    idea_anchor_groups: list[list[dict]] | None = None,
):
    summary_lines = [f"[{country}] 件数: {len(items)}"]
    for it in items[:5]:
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
    if anchor_lines:
        summary = anchors_text
    duplicate_guard = build_duplicate_guard_text(history_ideas or [], max_items=12)
    angles = load_idea_angles()
    angle = random.choice(angles) if angles else ""
    angle_instruction = f"    - 【今回の発想切り口】1件目は「{angle}」の視点で発想すること（ただしニュース内容と関連させること）\n" if angle else ""
    tg_products = load_tg_products()
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
    - 各ideasのdescには、アンカーニュース固有の車名・部品名・技術名・数値のいずれかを必ず1つ以上入れる
    - sourceNewsIdsには、対応するanchor IDsのみを入れる
    - うれしさを必ず明記
    - titleは日本語を基本に20文字以内の短い名称のみ（英語のみは禁止、説明・括弧書き・句点を含めない）
    - descは120〜180文字程度。長い背景説明ではなく、何を作るか・誰がうれしいかを端的に書く
    - imagePromptは必須。英語で、1枚の画像として何を見せるかを具体化する
    - imagePromptはアイデアごとに構図・対象物・素材・光・色を変え、似た画像にならないようにする
    - titleとdescにマークダウン記法（**太字**等）を使用しない
    - analysisは300字以内（厳守）。文ごとに関連ニュースID参照を付ける（例: ...素材[jp123]...）
    - 参照は文末にまとめず、関連語の直後に入れる
    - 参照IDはその文に直接関係するIDのみ（1文あたり1〜3件）
    - id: という文字は書かない
    - ideasのdesc末尾にはsourceNewsIdsと同じID参照を [jp123] の形式で付ける
    - analysisに説明・解説・注釈・思考過程を含めない。考察文のみ出力する
    """)
    return extra


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet", default=str(DEFAULT_SHEET))
    ap.add_argument("--skip-insights", action="store_true")
    ap.add_argument("--skip-html", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--replace-insights", action="store_true")
    ap.add_argument("--fix-existing", action="store_true", help="Fix url/source for existing entries using CSV rows")
    ap.add_argument("--llm-endpoint", default=os.getenv("LLM_ENDPOINT", "http://127.0.0.1:1234/v1/chat/completions"))
    ap.add_argument("--llm-model", default=os.getenv("LLM_MODEL", "qwen/qwen3.5-9b"))
    args = ap.parse_args()

    sheet_path = Path(args.sheet)
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
    idx_interior_score = find_col(header, "内装関連度", "関連度スコア")
    idx_interior_reason = find_col(header, "内装判定理由")

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
        country = map_country(country_raw) or "jp"
        if country != "paper":
            non_paper_rows += 1
            if ("対象" in llm_val) or interior_score is not None:
                rows_with_relevance_signal += 1

        llm_is_target = llm_val.strip() == "対象"
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
        if not img:
            continue
        if not title or not url:
            continue
        if is_bad_generated_text(title) or is_bad_generated_text(desc):
            print(f"Skip placeholder summary: {url}")
            continue
        if country != "paper" and (not has_japanese_text(title) or not has_japanese_text(desc)):
            print(f"Skip non-Japanese title/summary: {url}")
            continue

        tags = generate_tags(f"{title} {desc}")
        items.append(apply_item_overrides({
            "country": country,
            "date": date_val,
            "title": title,
            "desc": desc,
            "img": img,
            "url": url,
            "source": source,
            "tags": tags,
            "interiorScore": interior_score,
            "interiorReason": interior_reason,
            "imageInterior": True if img_val and "あり" in img_val else (False if img_val and "なし" in img_val else None),
        }))

    if non_paper_rows and idx_llm is not None and rows_with_relevance_signal == 0:
        raise RuntimeError(
            "sheet2 has no LLM/interior relevance signals. Abort to avoid publishing weak non-interior articles."
        )

    if not items:
        print("No items to append after filtering.")
        return
    dates_in_items = sorted({it.get("date") for it in items if it.get("date")})
    if dates_in_items:
        print(f"Loaded {len(items)} items from sheet: {sheet_path} (dates: {dates_in_items[0]} ~ {dates_in_items[-1]})")
    else:
        print(f"Loaded {len(items)} items from sheet: {sheet_path} (date: unknown)")

    news_text = read_text_any(NEWS_PATH)
    existing_urls, max_ids = parse_existing_news(news_text)

    new_items = []
    for it in items:
        if it["url"] in existing_urls:
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
    news_id_map = parse_news_id_map(updated_news_text)
    for it in items:
        it["newsId"] = news_id_map.get(it.get("url", ""), "")

    if not args.dry_run:
        NEWS_PATH.write_text(updated_news_text, encoding="utf-8")

    # Update NEW date range
    if not args.skip_html:
        html_text = read_text_any(HTML_PATH)
        if new_dates:
            start = min(new_dates)
            end = max(new_dates)
            html_text = update_new_date_range(html_text, start, end)
            if not args.dry_run:
                HTML_PATH.write_text(html_text, encoding="utf-8")

    # Insights generation
    if not args.skip_insights:
        insights_text = read_text_any(INSIGHTS_PATH)
        insight_dates = new_dates if new_dates else all_dates
        insight_start = min(insight_dates) if insight_dates else None
        latest_date = max(insight_dates) if insight_dates else None
        insight_date_label = (
            f"{insight_start}〜{latest_date}"
            if insight_start and latest_date and insight_start != latest_date
            else latest_date
        )
        insight_exists = (
            has_insight_for_date(insights_text, insight_date_label)
            or has_insight_for_date(insights_text, latest_date)
            if latest_date
            else False
        )
        if insight_date_label and insight_exists and not args.replace_insights:
            print(f"Insights for {insight_date_label} already exists. Use --replace-insights to overwrite.")
        elif insight_date_label:
            grouped = {"jp": [], "cn": [], "in": [], "us": [], "eu": []}
            for it in items:
                if it["country"] in grouped:
                    grouped[it["country"]].append(it)
            prompt_template = read_text_any(PROMPT_PATH) if PROMPT_PATH.exists() else ""
            analysis_out = {}
            ideas_out = {}
            draft_parts = []
            attempted_insight_countries = 0
            for key in ["jp", "cn", "in", "us", "eu"]:
                if not grouped.get(key):
                    continue
                attempted_insight_countries += 1
                history_ideas = extract_recent_ideas_by_country(insights_text, key, limit=60)
                idea_anchor_groups = select_idea_anchor_groups(grouped[key], need_count=2)
                prompt = make_country_prompt(
                    insight_date_label,
                    key,
                    grouped[key],
                    prompt_template,
                    history_ideas=history_ideas,
                    need_count=2,
                    idea_anchor_groups=idea_anchor_groups,
                )
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
                    analysis_text = normalize_analysis_refs_per_sentence(data.get("analysis", ""))
                    allowed_ids = build_allowed_news_ids(grouped[key])
                    analysis_text = filter_analysis_refs_to_allowed(analysis_text, allowed_ids)
                    if analysis_text and not analysis_ref_coverage_ok(analysis_text):
                        analysis_text = rewrite_analysis_with_refs(
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
                    analysis_final = shorten_analysis_with_llm(
                        args.llm_endpoint, args.llm_model, analysis_final
                    )
                    analysis_out[key] = analysis_final
                    deduped = dedupe_ideas(data.get("ideas", []), history_ideas, limit=2)
                    if len(deduped) < 2:
                        retry_prompt = make_country_prompt(
                            insight_date_label,
                            key,
                            grouped[key],
                            prompt_template,
                            history_ideas=(history_ideas + deduped),
                            need_count=(2 - len(deduped)),
                            idea_anchor_groups=idea_anchor_groups[len(deduped):],
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
                            add_ideas = dedupe_ideas(
                                retry_data.get("ideas", []),
                                history_ideas + deduped,
                                limit=(2 - len(deduped)),
                            )
                            deduped.extend(add_ideas)
                    allowed_ids = build_allowed_news_ids(grouped[key])
                    for i, idea in enumerate(deduped[:2]):
                        anchor_ids = []
                        if i < len(idea_anchor_groups):
                            anchor_ids = [x.get("newsId", "").lower() for x in idea_anchor_groups[i] if x.get("newsId")]
                        raw_ids = [
                            str(x).strip().lower()
                            for x in (idea.get("sourceNewsIds") or [])
                            if str(x).strip().lower() in allowed_ids
                        ]
                        source_ids = raw_ids[:2] if raw_ids else anchor_ids[:2]
                        idea["sourceNewsIds"] = source_ids
                        if source_ids and not re.search(r"\[[a-z]{2,5}\d+(?:\s*,\s*[a-z]{2,5}\d+)*\]", idea.get("desc", ""), flags=re.IGNORECASE):
                            idea["desc"] = f"{strip_idea_refs(idea.get('desc', ''))} [{','.join(source_ids)}]"
                    ideas_out[key] = deduped[:2]
                else:
                    draft_parts.append(f"[{key}]\n{llm_text.strip() if llm_text else 'LLM出力に失敗しました。'}\n")
            if analysis_out or ideas_out:
                max_id = parse_insights_max_id(insights_text)
                entry_lines = ["    {", f"        date: \"{insight_date_label}\",", "        analysis: {"]
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
                        desc_text = strip_idea_refs(fix_idea_ref_prefix(idea.get("desc", ""), key))
                        if source_ids:
                            desc_text = f"{desc_text} [{','.join(source_ids)}]"
                        desc = js_escape(desc_text)
                        image_prompt = js_escape(idea.get("imagePrompt", ""))
                        source_ids_js = json.dumps(source_ids, ensure_ascii=False)
                        entry_lines.append(
                            f"                {{ id: {max_id}, img: \"{PLACEHOLDER_IMG}\", title: \"{title}\", desc: \"{desc}\", imagePrompt: \"{image_prompt}\", sourceNewsIds: {source_ids_js} }},"
                        )
                    entry_lines.append("            ],")
                entry_lines.append("        }")
                entry_lines.append("    },")
                new_entry = "\n".join(entry_lines)
                updated_insights = insights_text
                if args.replace_insights and insight_exists:
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
                draft_path = ROOT / f"insights_draft_{draft_key}.txt"
                if not args.dry_run:
                    draft_path.write_text("\n".join(draft_parts), encoding="utf-8")
                print(f"Insights draft saved: {draft_path}")

    print("Done.")


if __name__ == "__main__":
    main()
