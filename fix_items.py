"""
cn493, jp670, cn506, cn509, cn507 を再翻訳して news_data.js を修正する。
"""
import json, re, requests
from bs4 import BeautifulSoup

LLM_ENDPOINT = "http://127.0.0.1:1234/v1/chat/completions"
LLM_MODEL    = "qwen/qwen3.5-9b"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

ITEMS = {
    "cn506": {"url": "https://www.sohu.com/a/996218027_121987930", "country": "中国"},
    "cn509": {"url": "https://news.qq.com/rain/a/20260313A03BN600", "country": "中国"},
    "cn507": {"url": "https://www.autohome.com.cn/news/202603/1312944.html", "country": "中国"},
}

def fetch_text(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return ""
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script","style","noscript"]):
            tag.decompose()
        return soup.get_text(" ", strip=True)[:6000]
    except:
        return ""

def call_llm(prompt):
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": "<think>\n</think>\n{\"title\":\""},
        ],
        "temperature": 0.2,
        "max_tokens": 300,
    }
    try:
        r = requests.post(LLM_ENDPOINT, json=payload, timeout=120)
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"  LLMエラー: {e}")
        return ""

def parse_json(text, key):
    m = re.search(r'"' + key + r'"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
    return m.group(1).replace("\\n","").strip() if m else ""

def summarize(item_id, url, country, body_text):
    print(f"  [{item_id}] LLM呼び出し中...")
    if country == "中国":
        prompt = (
            "IMPORTANT: You MUST write the output in JAPANESE only. Do NOT use Chinese characters for the title or summary values.\n\n"
            "以下の中国語記事を【日本語】で要約してください。\n"
            "【絶対条件】titleとsummaryの値は必ず日本語で書くこと。中国語での出力は禁止。\n"
            "条件1: タイトルは50字以内、文を途中で切らない。\n"
            "条件2: 内容は150字以内、文を途中で切らない。\n"
            "条件3: 事実ベースで簡潔に。\n"
            "条件4: 固有名詞/数値/企業名など具体情報を2つ以上含める。\n"
            "条件5: 内容は必ず句点で終える。\n"
            "条件6: 中国固有名詞は英字か一般的な日本語表記を使う（例: Huawei=ファーウェイ）。\n"
            "条件7: 出力はJSONのみ。形式: {\"title\":\"日本語タイトル\",\"summary\":\"日本語内容\"}\n\n"
            f"本文: {body_text}\nURL: {url}"
        )
    else:
        prompt = (
            "以下の記事を日本語で要約してください。\n"
            "条件1: タイトルは50字以内（文を途中で切らない）。\n"
            "条件2: 内容は150字以内（文を途中で切らない）。\n"
            "条件3: 事実ベースで簡潔に。\n"
            "条件4: 固有名詞/数値/企業名など具体情報を1つ以上含める。\n"
            "条件5: 内容は必ず句点で終える。\n"
            "条件6: 出力はJSONのみ。形式: {\"title\":\"...\",\"summary\":\"...\"}\n\n"
            f"本文: {body_text}\nURL: {url}"
        )
    raw = call_llm(prompt)
    # pre-fillで {"title":" まで入力済みなので補完する
    out = '{"title":"' + raw
    title = parse_json(out, "title")
    summary = parse_json(out, "summary")
    print(f"  [{item_id}] title: {title.encode('cp932','replace').decode('cp932')}")
    print(f"  [{item_id}] summary: {summary[:60].encode('cp932','replace').decode('cp932')}...")
    return title, summary

def main():
    # news_data.js 読み込み
    js_path = r"c:\Users\demo\Desktop\中村\DailyNews\news_data.js"
    with open(js_path, encoding="utf-8") as f:
        js = f.read()

    results = {}
    for item_id, info in ITEMS.items():
        print(f"\n=== {item_id} ===")
        print(f"  URL取得中: {info['url']}")
        body = fetch_text(info["url"])
        if not body:
            print(f"  本文取得失敗 - スキップ")
            continue
        print(f"  本文取得: {len(body)}文字")
        title, summary = summarize(item_id, info["url"], info["country"], body)
        if title and summary:
            results[item_id] = (title, summary)
        else:
            print(f"  LLM出力不正 - スキップ")

    if not results:
        print("\n修正対象なし。終了。")
        return

    # news_data.js 更新
    print("\n=== news_data.js 更新 ===")
    new_js = js
    for item_id, (title, summary) in results.items():
        # id: "xxx", の次の title と desc を置換
        pattern = (
            r'(id:\s*"' + re.escape(item_id) + r'",\s*\n\s*title:\s*)"[^"]*"'
            r'(\s*,\s*\n\s*desc:\s*)"[^"]*"'
        )
        # titleのエスケープ
        t_esc = title.replace('\\','\\\\').replace('"','\\"')
        s_esc = summary.replace('\\','\\\\').replace('"','\\"')
        replacement = r'\g<1>"' + t_esc + r'"\g<2>"' + s_esc + '"'
        new_js_candidate = re.sub(pattern, replacement, new_js)
        if new_js_candidate == new_js:
            print(f"  [{item_id}] パターン不一致 - 手動確認必要")
        else:
            new_js = new_js_candidate
            print(f"  [{item_id}] 更新完了")

    with open(js_path, "w", encoding="utf-8") as f:
        f.write(new_js)
    print("\n完了。news_data.js を保存しました。")

if __name__ == "__main__":
    main()
