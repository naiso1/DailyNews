# Copilotの画像生成

2026-11-10から内装・外装とも `dailynews.idea_images.optional_images` がCopilotを優先します。
`dailynews/copilot.py` と専用の `worker.js` が、1案1会話のEdgeを非表示で起動し、
画像のダウンロードと完了記録を保存します。普段のEdgeには接続しません。

通常の設定は `provider: "copilot"`、`fallback_provider: "exabase"` です。
Copilotの初回認証情報がない・期限切れなどで利用できない場合、未生成案だけをexaBaseで補完します。
exaBaseは引き続きGPT-image、次いでNano Bananaを選択します。有料画像APIは呼びません。
Copilotモードでは誤ってGemini代替を設定してもAPIを呼びません。

Copilotは1案あたり生成待ち180秒、両サービス合計のバッチは各版1800秒を上限とします。
認証・ブラウザの終了用の時間もバッチの残り時間から差し引きます。
失敗時には文章の公開を続け、復旧処理は当日処理した最新号の未生成画像だけを対象とします。

## 認証

既存のexaBaseランタイムの固定版Playwrightを使用します。初回は次を実行し、会社アカウントで本人がサインインします。

```powershell
node deployment/workstation/copilot/worker.js --login
node deployment/workstation/copilot/worker.js --check-session
```

保存先は `%LOCALAPPDATA%\DailyNewsRuntime\copilot\auth.bin`。Windows DPAPIのCurrentUserで暗号化し、
Cookie・IndexedDB等の平文をディスクやログに残しません。生成と接続確認で認証を更新します。
専用ブラウザ内の既存SSOは利用しますが、パスワード入力・MFA・初回設定の自動操作は行いません。
実行ユーザーが変わる場合は、そのユーザーで改めて認証が必要です。

## 画像と二重送信防止

- `copilot-jobs/<key>/` に案・日付・出典ID・生成指示と送信段階、完成画像・SHA-256を記録します。
- 送信ボタンを押す前に `phase.json` を保存。送信以後の結果が不明ならその案を自動再送せず、exaBase代替からも除外します。
- 指示が変更された場合も同じ版・号・案の未解決記録を調べます。完了画像は再利用します。
- 掲載直前に案の本文と既存画像を再確認し、他の変更を上書きしません。
- 掲載先は `images/copilot_<版>_<案ID>_<hash16桁>.<拡張子>`。`imageProvider: "copilot"` を記録します。
- Copilotの内部画像モデルは画面から確認できないため、モデル名を推定して保存しません。表示は「AI生成イメージ（Copilot）」です。
- 1:1を指示し、保存画像も正方形を検証します。構造の工学的な正しさは生成画像だけでは保証できません。

## 元の優先順へ戻す

両版の `image_generation.provider` を `exabase`、`fallback_provider` を `none` に変更すると、
既存のexaBase経路に戻せます。認証情報・掲載済み画像を削除する必要はありません。
表示・生成動作の変更時は通常どおり `release_history.js` を更新してください。
