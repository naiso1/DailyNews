# 外装アイデア画像：exaBase連携

`dailynews/exabase.py` が外装アイデア1件からプロンプト1件を作り、`worker.js` が専用のEdgeコンテキストでexaBaseを操作します。共有ツールの `generateBatch(count: 1)` を利用し、画像をアイデアIDと `sourceNewsIds` に対応づけます。Geminiなどの画像APIへの代替呼び出しはありません。内装版の既存画像生成は変更しません。

## 処理PCの準備

Windows、Edge、Node.js、DailyNewsのPython環境（Pillowを含む）が必要です。定時処理と同じWindowsユーザーで実行します。

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File deployment/workstation/exabase/install.ps1
node deployment/workstation/exabase/worker.js --login
node deployment/workstation/exabase/worker.js --check-session
```

`install.ps1` は指定共有フォルダの軽量版1.1.4エンジンをSHA-256で確認し、`%LOCALAPPDATA%\DailyNewsRuntime\exabase` にコピーします。共有側は変更せず、`playwright-core` は `1.55.0` に固定します。共有ツール更新時には内容の確認とハッシュ更新が必要です。

`--login` で開いた専用Edgeに手動でログインします。最大10分待機し、完了時は `SESSION_SAVED` を返します。普段使うブラウザのプロファイルや共有ツールのセッションは流用しません。`--check-session` は生成を行わず、保存済み認証で会話画面に到達できるか確認します。`--status` は保存有無のみの確認で、認証期限は検証しません。

認証状態は同じWindowsユーザーのDPAPIで暗号化して `auth.bin` に保存します。保存フォルダのアクセス権は実行ユーザー、SYSTEM、Administratorsに限定します。生成時に必要な一時セッションJSONもこのフォルダに置き、終了時に削除します。認証ファイルを別PC・別ユーザーへ配布したり、Gitや公開フォルダに置いたりしません。

## 最初は1案だけ確認

自動生成の設定が `enabled: false, provider: "none"` でも、日時とIDを明示した試験を1件だけ実行できます。IDと日付は対象の `content/exterior/insights_data.js` に合わせます。

```powershell
$runtimePython = Join-Path $env:LOCALAPPDATA 'DailyNewsRuntime\venv\Scripts\python.exe'
& $runtimePython -B -m dailynews.exabase --pilot-idea-id 5 --date 2026-09-15
```

この時点では作業フォルダに保存するだけです。`runtime/exterior/exabase-last-result.json` の画像を開き、企画との対応や生成結果を確認します。ローカル掲載データへ反映する場合は、同じ引数に `--publish` を追加します。

```powershell
& $runtimePython -B -m dailynews.exabase --pilot-idea-id 5 --date 2026-09-15 --publish
```

完了済み画像はキャッシュから再利用するため、再生成しません。公開先への配備は別の通常デプロイ手順で行います。掲載画像名は `images/exabase_exterior_<ideaID>_<hash16桁>.<拡張子>` です。画面では原記事の写真と区別できる「AI生成イメージ」の注記を付けます。

## 定時処理で有効にする条件

認証・1枚生成・画像の内容・掲載表示を確認してから、`editions/exterior/settings.json` の `image_generation` を変更します。

```json
{
  "enabled": true,
  "provider": "exabase",
  "timeout_seconds": 420,
  "batch_seconds": 900,
  "max_images": 4
}
```

最新日の先頭最大4案を対象とし、そのうち画像のない案を順番に処理します。同じ日の再実行で生成対象を5案目以降へ広げません。過去日の一括生成は行いません。1画像の待機と全体の時間予算を制限し、画像生成が失敗してもニュース本文・考察の公開を継続します。認証切れや実行環境の不足が判明したら残りの画像処理を中止します。`provider: "none"` の間は通常処理からexaBaseを呼びません。

## 再実行と障害対応

| 状態 | 対応 |
| --- | --- |
| `AUTH_REQUIRED` | 定時処理と同じユーザーで `--login`、続いて `--check-session` |
| `BUSY` | ログインまたは画像生成が終了してから再実行 |
| `ENGINE_CHANGED` | 共有エンジン変更内容を確認。確認せずハッシュを置き換えない |
| `NEEDS_REVIEW` | 送信開始後に完了を確認できない。exaBaseの履歴を人が確認するまで再送しない |
| `INVALID_SOURCE_IDS` | アイデアの出典IDと外装記事データを確認 |
| `CONTENT_CHANGED` | 生成中に企画が変更された。現行企画を確認してから実行 |

`runtime/exterior/exabase-jobs/<key>/` に、入力、状態、アイデアと出典ID、画像ダイジェスト、完了結果を保存します。生成完了後に処理が途切れても、完了記録と画像を確認して再利用します。送信済みか不明なジョブは自動再送しません。exaBase側の履歴を確認し、再生成が必要と判断した場合だけ、対象IDを明示して `--retry-uncertain` を追加します。これは新たな生成を実行する場合があります。

ブラウザの原文エラー、プロンプト、認証値を通常ログに流さず、安全な状態コードのみを返します。ジョブの入力・画像・結果は非公開作業データであり、公開するのは検証済み画像と掲載データだけです。

## 現在の範囲と検証

- 参照情報は企画文と元記事のタイトル・要約です。現行軽量エンジンには添付画像の引数がなく、元記事の写真は送信しません。
- 専用セッション、1案単位の処理、キャッシュ、送信後の不明状態、出典ID照合、画像形式とダイジェスト検証を実装しています。
- オフライン検証は `tests/test_exabase.py`。有料APIもexaBaseも呼ばず、無効化・対応関係・キャッシュ・異常終了後の復旧・認証失敗・キャッシュ改変を確認します。
- 2026-09-16に専用セッションの保存・認証確認と、2026-09-15の企画ID5〜8に対応する4枚の実生成を確認しました。出典はID5・6が `jp2`、ID7・8が `us2`。各画像と企画の対応を目視確認済みです。自動生成の初期上限は最新日の先頭4案です。
