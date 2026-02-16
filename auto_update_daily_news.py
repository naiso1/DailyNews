import argparse
import csv
import os
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

ENCODINGS = ["utf-8-sig", "cp932", "utf-16", "utf-8"]

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
    (r"安全|エアバッグ|ADAS|衝突|セーフティ", "安全"),
    (r"音響|スピーカー|オーディオ", "音響"),
    (r"カスタム|パーソナル|カスタマイズ", "カスタマイズ"),
]

PLACEHOLDER_IMG = "images/idea_dummy.svg"


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


def generate_tags(text: str):
    tags = []
    for pattern, tag in TAG_RULES:
        if re.search(pattern, text, flags=re.IGNORECASE):
            if tag not in tags:
                tags.append(tag)
    if not tags:
        tags.append("内装")
    return tags[:6]


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
    pattern = r"const NEW_DATE_RANGE_OVERRIDE = \{ start: \"[^\"]*\", end: \"[^\"]*\" \};"
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


def extract_json_block(text: str):
    if not text:
        return None
    cleaned = re.sub(r"```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    cleaned = cleaned.replace("```", "")
    m = re.search(r"\{[\s\S]*\}", cleaned)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


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


def dedupe_ideas(raw_ideas: list, history_ideas: list, limit: int = 2):
    history_texts = [f"{x.get('title', '')} {x.get('desc', '')}".strip() for x in history_ideas]
    picked = []
    picked_texts = []
    for idea in raw_ideas or []:
        title = str((idea or {}).get("title", "")).strip()
        desc = str((idea or {}).get("desc", "")).strip()
        image_prompt = str((idea or {}).get("imagePrompt", "")).strip()
        if not title or not desc:
            continue
        cand = f"{title} {desc}"
        duplicate = False
        for ht in history_texts:
            if _similarity(cand, ht) >= 0.72:
                duplicate = True
                break
        if not duplicate:
            for pt in picked_texts:
                if _similarity(cand, pt) >= 0.78:
                    duplicate = True
                    break
        if duplicate:
            continue
        picked.append({"title": title, "desc": desc, "imagePrompt": image_prompt})
        picked_texts.append(cand)
        if len(picked) >= limit:
            break
    return picked


def build_duplicate_guard_text(history_ideas: list, max_items: int = 20):
    if not history_ideas:
        return ""
    lines = []
    for x in history_ideas[:max_items]:
        t = (x.get("title", "") or "").strip()
        if t:
            lines.append(f"- {t}")
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
        "1) 各文に必ず1つ以上の参照を付ける\n"
        "2) 参照は [jp123,in332] 形式のみ（id:は禁止）\n"
        "3) 参照は文末にまとめず、関連語の直後に自然に挿入する\n"
        "4) 参照はその文に関係するIDのみ（1文あたり1〜3件）\n"
        "5) 文章は日本語のまま、内容改変は最小限\n"
        "6) ideas向けではなくanalysis文のみを返す\n\n"
        f"国: {country}\n"
        f"利用可能ID一覧:\n" + "\n".join(id_lines) + "\n\n"
        f"原文:\n{analysis_text}\n"
    )
    try:
        out = call_llm(endpoint, model, prompt)
        out = re.sub(r"^```(?:json)?\s*|\s*```$", "", out.strip(), flags=re.IGNORECASE | re.MULTILINE)
        out = normalize_analysis_refs_per_sentence(out)
        return out if out else analysis_text
    except Exception:
        return analysis_text


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


def js_escape(value: str):
    s = str(value or "")
    s = s.replace("\u2028", " ").replace("\u2029", " ")
    s = s.replace("\\", "\\\\")
    s = s.replace("\"", "\\\"")
    s = s.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n")
    return s


def make_country_prompt(
    date_key: str,
    country: str,
    items: list,
    prompt_template: str,
    history_ideas: list | None = None,
    need_count: int = 2,
):
    summary_lines = [f"[{country}] 件数: {len(items)}"]
    for it in items[:10]:
        news_id = it.get("newsId", "")
        id_text = f"id={news_id} / " if news_id else ""
        summary_lines.append(f"- {id_text}{it['title']} / {it['desc']} / {it.get('tags', '')}")
    summary = "\n".join(summary_lines)
    duplicate_guard = build_duplicate_guard_text(history_ideas or [], max_items=20)
    extra = textwrap.dedent(f"""

    【対象日】{date_key}
    【対象国】{country}
    【ニュース概要】
    {summary}
    {duplicate_guard}

    出力は必ずJSONのみで返してください。
    JSON以外の文字や説明、コードフェンスは一切出力しないでください。
    形式:
    {{
      "analysis": "...",
      "ideas": [
        {{"title": "...", "desc": "(200〜300文字・うれしさを含む)", "imagePrompt": "English prompt for image generation"}},
        {{"title": "...", "desc": "(200〜300文字・うれしさを含む)", "imagePrompt": "English prompt for image generation"}}
      ]
    }}

    制約:
    - {need_count}件提案
    - 2件の発想軸を明確に分ける（例: 1件は素材/ハード、もう1件はUI/ソフト/サービス）
    - 過去アイデアの言い換え・焼き直しは禁止
    - うれしさを必ず明記
    - 200〜300文字程度
    - imagePromptは構図・素材・配色を2件で明確に変える
    - analysisは文ごとに関連ニュースID参照を付ける（例: ...素材[jp123]...）
    - 参照は文末にまとめず、関連語の直後に入れる
    - 参照IDはその文に直接関係するIDのみ（1文あたり1〜3件）
    - id: という文字は書かない
    - ideasのdescにはID参照を書かない
    """)
    return prompt_template + "\n" + extra


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet", default=str(DEFAULT_SHEET))
    ap.add_argument("--skip-insights", action="store_true")
    ap.add_argument("--skip-html", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--replace-insights", action="store_true")
    ap.add_argument("--fix-existing", action="store_true", help="Fix url/source for existing entries using CSV rows")
    ap.add_argument("--llm-endpoint", default=os.getenv("LLM_ENDPOINT", "http://127.0.0.1:1234/v1/chat/completions"))
    ap.add_argument("--llm-model", default=os.getenv("LLM_MODEL", "qwen/qwen3-8b"))
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

    def get(row, idx):
        if idx is None:
            return ""
        return row[idx].strip() if idx < len(row) else ""

    items = []
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

        if idx_llm is not None and llm_val and "対象" not in llm_val:
            continue
        if idx_img判定 is not None and img_val and "あり" not in img_val:
            continue
        if not img:
            continue
        if not title or not url:
            continue

        country = map_country(country_raw) or "jp"
        tags = generate_tags(f"{title} {desc}")
        items.append({
            "country": country,
            "date": date_val,
            "title": title,
            "desc": desc,
            "img": img,
            "url": url,
            "source": source,
            "tags": tags,
        })

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
        item_block = textwrap.dedent(f"""
            {{
                id: "{it_id}",
                title: "{it['title']}",
                desc: "{it['desc']}",
                url: "{it['url']}",
                source: "{source}",
                date: "{it['date']}",
                tags: {json.dumps(tags, ensure_ascii=False)},
                country: "{it['country']}",
                img: "{it['img']}",
                note: "{note}"
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
        latest_date = max(new_dates) if new_dates else (all_dates[-1] if all_dates else None)
        if latest_date and latest_date in insights_text and not args.replace_insights:
            print(f"Insights for {latest_date} already exists. Use --replace-insights to overwrite.")
        elif latest_date:
            grouped = {"jp": [], "cn": [], "in": [], "us": [], "eu": []}
            for it in items:
                if it["country"] in grouped:
                    grouped[it["country"]].append(it)
            prompt_template = read_text_any(PROMPT_PATH) if PROMPT_PATH.exists() else ""
            analysis_out = {}
            ideas_out = {}
            draft_parts = []
            for key in ["jp", "cn", "in", "us", "eu"]:
                if not grouped.get(key):
                    continue
                history_ideas = extract_recent_ideas_by_country(insights_text, key, limit=60)
                prompt = make_country_prompt(
                    latest_date,
                    key,
                    grouped[key],
                    prompt_template,
                    history_ideas=history_ideas,
                    need_count=2,
                )
                llm_text = ""
                try:
                    llm_text = call_llm(args.llm_endpoint, args.llm_model, prompt)
                    data = extract_json_block(llm_text)
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
                    analysis_out[key] = filter_analysis_refs_to_allowed(
                        normalize_analysis_refs_per_sentence(analysis_text),
                        allowed_ids,
                    )
                    deduped = dedupe_ideas(data.get("ideas", []), history_ideas, limit=2)
                    if len(deduped) < 2:
                        retry_prompt = make_country_prompt(
                            latest_date,
                            key,
                            grouped[key],
                            prompt_template,
                            history_ideas=(history_ideas + deduped),
                            need_count=(2 - len(deduped)),
                        )
                        try:
                            retry_text = call_llm(args.llm_endpoint, args.llm_model, retry_prompt)
                            retry_data = extract_json_block(retry_text)
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
                    ideas_out[key] = deduped[:2]
                else:
                    draft_parts.append(f"[{key}]\n{llm_text.strip() if llm_text else 'LLM出力に失敗しました。'}\n")
            if analysis_out or ideas_out:
                max_id = parse_insights_max_id(insights_text)
                entry_lines = ["    {", f"        date: \"{latest_date}\",", "        analysis: {"]
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
                        desc = js_escape(idea.get("desc", ""))
                        image_prompt = js_escape(idea.get("imagePrompt", ""))
                        entry_lines.append(
                            f"                {{ id: {max_id}, img: \"{PLACEHOLDER_IMG}\", title: \"{title}\", desc: \"{desc}\", imagePrompt: \"{image_prompt}\" }},"
                        )
                    entry_lines.append("            ],")
                entry_lines.append("        }")
                entry_lines.append("    },")
                new_entry = "\n".join(entry_lines)
                updated_insights = insights_text
                if args.replace_insights and latest_date in insights_text:
                    updated_insights = remove_insight_by_date(updated_insights, latest_date)
                updated_insights = insert_insight(updated_insights, new_entry)
                if not args.dry_run:
                    INSIGHTS_PATH.write_text(updated_insights, encoding="utf-8")
            if draft_parts:
                draft_path = ROOT / f"insights_draft_{latest_date}.txt"
                if not args.dry_run:
                    draft_path.write_text("\n".join(draft_parts), encoding="utf-8")
                print(f"Insights draft saved: {draft_path}")

    print("Done.")


if __name__ == "__main__":
    main()
