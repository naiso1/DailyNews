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

## RSS追加前の取得テスト

`tests/verify_rss_sources.py` で候補のRSS・記事本文・画像を少数だけ確認できます。
DailyNewsフォルダから実行します。ニュース収集本体、LLM、画像生成、メール配信、公開処理は実行しません。

```powershell
python -B -u tests/verify_rss_sources.py --windows-proxy --feed "Automotive Interiors World" "https://www.automotiveinteriorsworld.com/feed" --report "ニュース収集/logs/rss-verification.json"
```

- 既定で直近5記事を検査します。`--feed "媒体名" "RSS URL"` は複数指定可能です。
- `--windows-proxy` は保存済みのWindowsプロキシをこのテスト内だけで使用します。OSの設定は変更しません。環境変数のプロキシを使う場合は省略します。
- 本番と同じRSS画像抽出・本文抽出関数を使い、日付、本文500文字以上、画像の実デコード、600×300px以上、単色でないことを検査します。
- 文字数だけでは別記事やメニューを誤取得している場合を見抜けないため、レポートの本文冒頭と原文の照合も必要です。画像は実際のブラウザでも確認してから追加します。
- 2026-09-08の追加4媒体は各5記事で本文・画像を確認済みです。検証記録は `rss_verification_20260908.json` に保存しています。将来の媒体側の変更やすべての記事の取得を保証するものではありません。
- 設定の正本は `department_settings.json` の `interior.rss_feeds` です。`rss_feed_list.csv` と `source_list_data.js` も同じ一覧に更新します。

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
