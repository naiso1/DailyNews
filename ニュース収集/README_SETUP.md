# 内装ニュース収集のセットアップ

## 概要
RSS / 検索 / LLM を使ってニュースを収集し、`search_results.csv` と `sheet2_llm_targets.csv` を出力します。
他部門に横展開する場合は **設定ファイルのみ** 変更する方針です。

---

## 変更ポイント（他部門に横展開するとき）

### 1) `department_settings.json`
部門ごとの RSS・国別設定・キーワード・判定条件をまとめています。
- `rss_feeds`: RSS一覧（国/名前/URL）
- `country_settings`: 国別の検索設定
- `keywords`: 関連度スコア用の共通キーワード
- `synonym_groups`: 同義語グループ（例: `car` と `車` を二重カウントしない）
- `prompt_path`: LLMのプロンプトファイル

### 2) `プロンプト.md`
LLM判定・要約・翻訳の指示を記載するファイルです。

### 3) `api_keys.json`
外部APIのキーを保存します。

---

## 実行方法

### 1) 通常実行
```bat
run_search.bat
```

### 2) 部門を指定して実行
```bat
python -u google_search_script.py --dept interior
```
環境変数で指定する場合:
```bat
set DEPARTMENT=interior
python -u google_search_script.py
```

---

## 出力ファイル
- `search_results.csv` : 収集した全件
- `sheet2_llm_targets.csv` : LLM判定済み + 画像URLありの抽出結果
- `rss_feed_list.csv` : RSS一覧の確認用

---

## APIキー取得
### NewsAPI
1. https://newsapi.org/ でアカウント登録
2. 無料キーを取得
3. `api_keys.json` の `newsapi_key` に貼り付け

---

## Sheet2の選定ロジック（10件制限）
- 日付で対象を絞り込み
- 画像URLがない行は除外（一部例外あり）
- 国ごとに **関連度スコア降順** で並べ替え
- `LLM判定=対象` を優先して10件まで
- 10件に満たない場合は非対象も追加
- 類似記事は除外（類似度しきい値で判定）
