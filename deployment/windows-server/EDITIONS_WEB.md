# 共通アカウントと版別Webアプリ・メール受信設定

同じ `server.js` と画面を、版ごとのプロセス・ルート・SQLite DBで実行する。共通認証を有効にすると、既存内装DBをアカウント・パスワード・セッションの正本にする。記事・反応・アクセス集計・購読は各版DBを継続する。

| 設定 | 内装 | 外装 |
| --- | --- | --- |
| `DAILYNEWS_EDITION` | `interior`（既定） | `exterior` |
| `DAILYNEWS_ROOT` | 既存のルートを維持 | 外装専用の絶対パスを必ず指定 |
| 公開パス | `/` | `/exterior/` |
| API | `/api/` | `/exterior/api/` |
| 共通認証時のCookie名 | `dailynews_session` | `dailynews_session` |
| 共通認証時のCookie Path | `/` | `/` |
| ブラウザ保存キー | 従来どおり | `dailynews_exterior:` を付加 |
| 閲覧 | 従来のログイン必須 | 許可された社内クライアントはログイン不要 |
| 新規登録のメール | 内装ONを画面に明示し、変更可能 | 両版OFFを初期値とし、変更可能 |

外装用ルートを省略した場合も内装DBを開かないよう、サーバースクリプトの親ディレクトリの `exterior` を使用する。運用では必ず絶対パスを指定する。各ルートに `data/dailynews.sqlite`、`releases/`、`active-release.txt`、`logs/` を保持する。外装の操作履歴には外装DB内のuser IDを使い、共通identity IDをそのまま流用しない。

IISは `/exterior/` を外装プロセスに転送する。上流に転送するときの `/exterior` 接頭辞の保持・除去の両方に対応する。共通認証は同じホスト名の両版で使い、共通CookieにはHttpOnlyとSameSite=Laxを設定する（HTTPSではSecureも付与）。

## 共通認証の移行・設定

両版の `app/shared-identity.json` に同一の設定を置く。通常のdeploy/installはこのファイルを上書きしない。環境変数 `DAILYNEWS_IDENTITY_DB` / `DAILYNEWS_EXTERIOR_DB` でも指定でき、環境変数が優先する。

```json
{
  "identityDb": "C:\\Users\\Administrator\\Desktop\\DailyNews\\data\\dailynews.sqlite",
  "exteriorDb": "C:\\Users\\Administrator\\Desktop\\DailyNewsExterior\\data\\dailynews.sqlite"
}
```

両方とも既存ファイルの絶対パスが必要。設定した版DBと `DAILYNEWS_ROOT` が不一致、同じDBを両版に指定、移行完了印がない場合は起動を止める。設定がないサーバーは従来の版別認証として起動し、既存運用を壊さない。

適用順序：

1. 両版の最新server/module/画面をdeployする（この時点では従来認証）。配信先件数を記録する。
2. サーバーの内装 `app` で `./enable-shared-identity.ps1` を実行し、アカウント重複数と配信先数を確認する。既定は読み取りのみ。
3. `./enable-shared-identity.ps1 -Apply` を実行する。両server task停止→各DBのSQLite整合バックアップ→移行→両app設定→両task開始を行う。失敗時は混在状態で再開せず、taskを停止したまま確認する。
4. 両版のhealthと `/api/config` の `sharedIdentity:true`、既存配信先件数、共通ログイン・版別集計を確認する。

移行の規則：

- 内装usersのID・パスワードhash・既存セッションと全操作履歴を維持する。既存の内装ログインは外装でも使える。
- 外装だけに存在するアカウントは、そのパスワードを保持して内装の正本へ追加する。追加によって内装メールを自動購読しない。
- 同一メールで両版にアカウントがある場合、内装パスワードを使う。外装の旧パスワード・旧Cookieは共通認証に使わない。外装の操作履歴と明示購読は既存local user IDに残す。
- 移行時に外装旧セッションを失効させる。外装だけのアカウントは再ログインが必要。
- 既存購読のenabledを変更しない。再実行は移行完了印を確認し、設定を再初期化しない。
- 共通パスワード変更は現在のパスワードを確認後、全共通セッションを失効させ、変更を実行した端末だけ新しいセッションを発行する。ログアウトは現在の共通セッションを両版から無効にする。

CLI単体は `node migrate-shared-identity.js --interior-db <絶対パス> --exterior-db <絶対パス>`。変更時だけ `--apply` を付ける。バックアップは各DBの隣に `.before-shared-identity-<日時>.bak` として作成する。復旧が必要な場合は両taskを停止し、両DB・設定を同じ移行前時点に揃える。移行後の書き込みがある場合は復元で失う変更を先に評価する。

## 画面の設定

`GET /api/config` と `GET /dailynews_config.js` は、版の `id`、`name`、`basePath`、`apiBase`、`allowGuestRead`、`imageGenerationEnabled`、`sharedIdentity` を返す。外装の画像生成設定はfalse。静的プレビュー用に `dailynews_config.js` も共通配布する。

共通HTMLが設定を読み、タイトル・リンク・検索の関連度・タグ・保存キーを切り替える。外装は記事・考察をURLから閲覧でき、いいね・コメント・お気に入り・自分への通知・メール設定には共通アカウントでログインする。お気に入り等のブラウザ保存キーとサーバー内の操作履歴は版別のまま。

外装は公開された `publication_status.json` の処理済み対象日と採用件数を表示する。対象記事ゼロの日も収集完了日を明示し、過去記事を閲覧できる。複数日処理では最終日に記事がなくても処理済み期間を表示し、New表示に反映する。初回作成中は `status: "building", processed_through: ""` を表示し、収集成功として扱わない。状態ファイルを確認できないときはその旨を表示する。

## メール受信設定・API

- 共通モードの新規登録 `POST /api/auth/register` は `subscriptions: {interior: boolean, exterior: boolean}` で画面の選択を送る。外装画面は両方OFF、内装画面は内装ON/外装OFFを明示する。未指定時は従来の入口版の既定値を維持し、外装を自動でONにしない。
- `GET /api/me/subscriptions` は `{subscriptions:{interior:boolean,exterior:boolean}}` を返す。
- `PUT /api/me/subscriptions` は同形式の本文で本人の両版購読を更新する。両booleanが必須で、両方OFFも有効。メールアドレスを本文で指定しても変更対象を切り替えられない。
- ログイン等の `user` には版内の `id` と共通 `identityId`、現在の `subscriptions` が返る。
- `PUT /api/auth/password` は `{currentPassword,newPassword}`。表示名は既存 `/api/auth/profile` で両版へ反映する。
- `GET /api/me/subscription` は本人の `{edition, enabled}` を返す。
- 従来の `PUT /api/me/subscription` に `{ "enabled": true }` またはfalseを送る場合は入口版だけを変更する（互換API）。購読操作はすべてログイン必須。
- マイページで内装・外装の受信を独立に選択して保存できる。
- 再ログイン・サーバー再起動によって受信停止を解除しない。
- 外装DBの `mail_subscriptions.enabled` のスキーマ既定値も0。初期配信先の投入では `enabled=1` を明示する。
- 管理者の手動追加は明示的な配信操作としてONになる。初期配信先の投入と実際のメール送信・スケジュールは別の運用処理が担当する。Webアプリ自体はメールを送信しない。
- 管理者の `/api/admin/mailing-list` と `manage-mailing-list.js export-json` は版別DBの現行enabledを出力する。export・ログインで購読を復活させない。

## 検証

`node deployment/windows-server/test_shared_identity.js` は一時DBで移行・旧内装session維持・ID衝突・共通ログイン/ログアウト/PW変更・4通りの購読・再起動後の停止保持・版別操作履歴/集計を実HTTPで検証する。`test_editions.js` と `test_auth.js` は共通設定なしの従来モードも引き続き検証する。実データやメールにはアクセスしない。
