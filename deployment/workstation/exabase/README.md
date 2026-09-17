# 内装・外装アイデア画像：exaBase連携

`dailynews/exabase.py` がアイデア1件からプロンプト1件を作り、`worker.js` が専用のEdgeコンテキストでexaBaseを操作します。固定ハッシュで検証した共有ツールの `generateOnPage(count: 1)` を利用し、画像を版・アイデアID・`sourceNewsIds` に対応づけます。ブラウザの開始・終了はworkerが担当し、生成エンジン本体は変更しません。

- 外装はexaBaseのみ。最新号の5地域各2案、既存画像を含めて最大10枚を対象とし、有料画像APIへ代替しません。
- 内装は2026-09-15より後の最新号からexaBaseを優先します。exaBaseで画像が得られなかった案だけ既存Gemini APIへ代替します。既存画像を含む上限は10枚です。
- 両版とも既存画像を再生成せず、過去号の欠損画像を一括生成しません。画像が得られない場合もニュース本文・考察を公開します。

## 処理PCの準備

Windows、Edge、Node.js、DailyNewsのPython環境（Pillowを含む）が必要です。定時処理と同じWindowsユーザーで実行します。

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File deployment/workstation/exabase/install.ps1
node deployment/workstation/exabase/worker.js --login
node deployment/workstation/exabase/worker.js --check-session
```

`install.ps1` は指定共有フォルダの軽量版1.1.4エンジンをSHA-256で確認し、`%LOCALAPPDATA%\DailyNewsRuntime\exabase` にコピーします。共有側は変更せず、`playwright-core` は `1.55.0` に固定します。共有ツール更新時には内容の確認とハッシュ更新が必要です。

`--login` で開いた専用Edgeに手動でログインします。最大10分待機し、完了時は `SESSION_SAVED` を返します。普段使うブラウザのプロファイルや共有ツールのセッションは流用しません。`--check-session` は生成を行わず、保存済み認証で会話画面に到達できるか確認します。`--status` は保存有無のみの確認で、認証期限は検証しません。

認証状態は同じWindowsユーザーのDPAPIで暗号化して `auth.bin` に保存します。保存フォルダのアクセス権は実行ユーザー、SYSTEM、Administratorsに限定します。復号した状態は生成プロセス内でブラウザへ渡し、新しい平文セッションJSONは作成しません。認証ファイルを別PC・別ユーザーへ配布したり、Gitや公開フォルダに置いたりしません。

手動ログイン・認証確認・画像生成終了時に、有効な会話画面で更新された状態を暗号化して原子的に保存します。cookie・localStorage・IndexedDBを保存し、Playwrightが対象としないsessionStorageは保存しません。保存直前にも認証画面が有効か確認し、キャンセル・閉じた画面・認証失効では既存の `auth.bin` を上書きしません。画像完成後の認証保存だけが失敗した場合は `SESSION_REFRESH_FAILED` 警告を返し、完成画像を失敗扱いにしてAPIへ代替しません。保存も既存のworkerロック内で実行します。

## 30分ごとの認証確認

処理PCで次のインストーラーを実行します。既存の同名タスクは更新し、重複登録しません。

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File deployment/workstation/exabase/install-session-maintenance.ps1
```

- タスク名: `DailyNews_ExaBaseSessionMaintenance`。毎時10分・40分に、定時処理と同じサインイン中のWindowsユーザーで実行します。
- `maintain-session.py` は有効な処理PC・リポジトリ・設定を確認し、`worker.js --check-session` だけを呼びます。画像生成、API利用、記事更新、メール送信は行いません。
- 通常のニュース処理が実行中なら共通の `run.lock` により見送ります。workerもログイン・生成との同時実行を防ぎます。主処理の0時開始と重ならない時刻に設定しています。
- PCが起動し、Windowsユーザーがサインインしている間に動きます。画面ロック中も動きますが、スリープ・サインアウト・電源OFF中は動きません。PCを起こしたり、会社・exaBase・SSO/MFAの再認証期限を変更したりはしません。
- 認証確認は最大180秒、終了処理を含むタスク上限は4分。タイムアウトでは自分が起動したworkerのプロセスツリーを停止・回収し、回収を確認できない場合は `CHECK_CLEANUP_FAILED` を記録します。
- 状態は `%LOCALAPPDATA%\DailyNewsRuntime\exabase\session-health.json` に、安全な状態コード・最終確認時刻・最後の認証成功時刻だけを保存します。`authenticated` は成功、`skipped` は主処理等との競合、`action_required / AUTH_REQUIRED` は本人の再ログインが必要な状態です。認証値やブラウザの生エラーは保存しません。

これは通常の認証更新を維持する仕組みです。サービス側が再認証を要求した場合は、従来どおり `--login` で本人がログインする必要があります。無期限の認証を保証するものではありません。

## 最初は1案だけ確認

自動生成の設定が `enabled: false, provider: "none"` でも、日時とIDを明示した試験を1件だけ実行できます。IDと日付は対象版の `insights_data.js` に合わせます（外装は `content/exterior/`、内装はルート）。直接実行するCLIはexaBase単体の試験です。内装のAPI代替まで含む通常処理とは分けて確認します。

```powershell
$runtimePython = Join-Path $env:LOCALAPPDATA 'DailyNewsRuntime\venv\Scripts\python.exe'
& $runtimePython -B -m dailynews.exabase --edition exterior --pilot-idea-id 5 --date 2026-09-15
```

この時点では作業フォルダに保存するだけです。`runtime/exterior/exabase-last-result.json` の画像を開き、企画との対応や生成結果を確認します。ローカル掲載データへ反映する場合は、同じ引数に `--publish` を追加します。

```powershell
& $runtimePython -B -m dailynews.exabase --edition exterior --pilot-idea-id 5 --date 2026-09-15 --publish
```

完了済み画像はキャッシュから再利用するため、再生成しません。公開先への配備は別の通常デプロイ手順で行います。掲載画像名は `images/exabase_<版>_<ideaID>_<hash16桁>.<拡張子>` です。画像ごとに `imageProvider: "exabase"` または `"api"` を記録し、画面では「AI生成イメージ（exaBase）」または「AI生成イメージ（API）」と表示します。API画像には実際に使用したモデルを `imageModel` に保存します。exaBase側のモデル名は未確認のため空にします。生成元が確認できない旧画像は「AI生成イメージ」のみ表示します。

## 定時処理で有効にする条件

認証・1枚生成・画像の内容・掲載表示を確認してから、版ごとの `image_generation` を設定します。外装は `editions/exterior/settings.json` の `exterior`、内装は `ニュース収集/department_settings.json` の `interior` が対象です。

外装の設定：

```json
{
  "enabled": true,
  "provider": "exabase",
  "timeout_seconds": 420,
  "batch_seconds": 6000,
  "max_images": 10
}
```

内装は同じ設定に以下を加えます：

```json
{
  "fallback_provider": "gemini",
  "start_after_date": "2026-09-15"
}
```

最新号の既存画像を上限から差し引き、残りの枠だけ未生成の案を順番に処理します。同じ号の再実行やアイデアの並び替えでも上限を超えません。1画像の待機と全体の時間予算を制限し、認証切れや実行環境の不足が判明したら残りのexaBase処理を中止します。`provider: "none"` の間は通常処理からexaBaseを呼びません。

内装はexaBase処理後、最新号の欠損案だけAPIで生成します。認証切れ・時間切れ・結果不明も代替の対象ですが、同じプロバイダーへの結果不明ジョブの自動再送は行いません。外装はAPI代替を設定しても実行しません。通常処理の `image-generation-last-result.json` で号の日付、生成元別の結果、未生成案、エラーを確認できます。内装の作業先は `ニュース収集/`、外装は `runtime/exterior/` です。

exaBaseの最終応答に失敗しても、画像ファイルと完了記録が保存済みなら回収して利用し、APIへの代替を避けます。他の画像処理が進行中の `BUSY` はAPIへ代替せず保留します。APIの5xx・408など送信後の結果を確定できないエラーは `API_NEEDS_REVIEW` として自動再送を止め、明確に拒否された要求だけを再試行可能とします。

## 再実行と障害対応

| 状態 | 対応 |
| --- | --- |
| `AUTH_REQUIRED` | 定時処理と同じユーザーで `--login`、続いて `--check-session` |
| `BUSY` | APIへ代替せず保留。ログインまたは画像生成が終了してから再実行 |
| `ENGINE_CHANGED` | 共有エンジン変更内容を確認。確認せずハッシュを置き換えない |
| `NEEDS_REVIEW` | 送信開始後に完了を確認できない。exaBaseの履歴を人が確認するまで再送しない |
| `INVALID_SOURCE_IDS` | アイデアの出典IDと対象版の記事データを確認 |
| `CONTENT_CHANGED` | 生成中に企画が変更された。現行企画を確認してから実行 |
| `API_NEEDS_REVIEW` | API送信後に結果を確認できない。自動再送せず、APIの処理記録を確認 |

対象版の作業先の `exabase-jobs/<key>/` に、入力、状態、アイデアと出典ID、画像ダイジェスト、完了結果を保存します。生成完了後に処理が途切れても、完了記録と画像を確認して再利用します。送信済みか不明なジョブはexaBaseへ自動再送しません。exaBase側の履歴を確認し、再生成が必要と判断した場合だけ、対象IDを明示して `--retry-uncertain` を追加します。これは新たな生成を実行する場合があります。

ブラウザの原文エラー、プロンプト、認証値を通常ログに流さず、安全な状態コードのみを返します。ジョブの入力・画像・結果は非公開作業データであり、公開するのは検証済み画像と掲載データだけです。

## 現在の範囲と検証

- 参照情報は企画文と元記事のタイトル・要約です。現行軽量エンジンには添付画像の引数がなく、元記事の写真は送信しません。
- 専用セッション、1案単位の処理、キャッシュ、送信後の不明状態、出典ID照合、画像形式とダイジェスト検証を実装しています。
- オフライン検証は `tests/test_exabase.py`。有料APIもexaBaseも呼ばず、無効化・対応関係・キャッシュ・異常終了後の復旧・認証失敗・キャッシュ改変を確認します。
- 2026-09-16に専用セッションの保存・認証を確認し、2026-09-15号の外装企画ID5〜14、5地域各2枚の計10枚をexaBaseで実生成・目視確認しました。先に確認したID5〜8の4枚を保持し、欧州・中国・インドの6枚を追加しました。ID10は内容を確認して再生成し、最終画像を採用しています。今回の追加生成に画像APIは使用していません。
- 2026-09-17の復旧では、9月16日号の内装・外装各10枚をすべてexaBaseで生成し公開しました。API代替の呼出しはありません。
- 認証更新の検証は `tests/test_exabase_session.cjs`、`tests/test_exabase_generation_session.cjs`、定期確認は `tests/test_exabase_maintenance.py` です。生成中の更新保存はオフラインのブラウザ代替テストで検証し、定期タスクの実接続は画像生成なしで確認します。
