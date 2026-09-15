# 版別Webアプリとメール受信設定

同じ `server.js` と画面を、版ごとのプロセス・ルート・SQLite DBで実行する。

| 設定 | 内装 | 外装 |
| --- | --- | --- |
| `DAILYNEWS_EDITION` | `interior`（既定） | `exterior` |
| `DAILYNEWS_ROOT` | 既存のルートを維持 | 外装専用の絶対パスを必ず指定 |
| 公開パス | `/` | `/exterior/` |
| API | `/api/` | `/exterior/api/` |
| Cookie名 | `dailynews_session` | `dailynews_exterior_session` |
| Cookie Path | `/` | `/exterior/` |
| ブラウザ保存キー | 従来どおり | `dailynews_exterior:` を付加 |
| 閲覧 | 従来のログイン必須 | 許可された社内クライアントはログイン不要 |
| 新規登録のメール | 従来の自動登録 | 初期値OFF・明示的な受信希望でON |

外装用ルートを省略した場合も内装DBを開かないよう、サーバースクリプトの親ディレクトリの `exterior` を使用する。運用では必ず絶対パスを指定する。各ルートに `data/dailynews.sqlite`、`releases/`、`active-release.txt`、`logs/` を保持する。内装DBやセッション、パスワードを外装にコピーしない。

IISは `/exterior/` を外装プロセスに転送する。上流に転送するときの `/exterior` 接頭辞の保持・除去の両方に対応する。ブラウザに公開するURLとCookie Pathは常に `/exterior/` を使用する。

## 画面の設定

`GET /api/config` と `GET /dailynews_config.js` は、版の `id`、`name`、`basePath`、`apiBase`、`allowGuestRead`、`imageGenerationEnabled` を返す。外装の画像生成設定はfalse。静的プレビュー用に `dailynews_config.js` も共通配布する。

共通HTMLが設定を読み、タイトル・リンク・検索の関連度・タグ・保存キーを切り替える。外装は記事・考察をURLから閲覧でき、いいね・コメント・お気に入り・自分への通知・メール設定には外装版へのログインが必要。内装と外装は初期導入時点では別アカウント。

外装は公開された `publication_status.json` の処理済み対象日と採用件数を表示する。対象記事ゼロの日も収集完了日を明示し、過去記事を閲覧できる。複数日処理では最終日に記事がなくても処理済み期間を表示し、New表示に反映する。初回作成中は `status: "building", processed_through: ""` を表示し、収集成功として扱わない。状態ファイルを確認できないときはその旨を表示する。

## メール受信設定

- 新規登録 `POST /api/auth/register` は `mailSubscribed: true` を明示した場合に受信を有効にする。外装画面のチェックは初期状態OFF。
- `GET /api/me/subscription` は本人の `{edition, enabled}` を返す。
- `PUT /api/me/subscription` に `{ "enabled": true }` またはfalseを送ると本人の設定だけを更新する。ログイン必須で、送信されたメールアドレスによる他人の変更はできない。
- マイページで「外装版のメールを受信する」を変更して保存できる。
- 再ログイン・サーバー再起動によって受信停止を解除しない。
- 外装DBの `mail_subscriptions.enabled` のスキーマ既定値も0。初期配信先の投入では `enabled=1` を明示する。
- 管理者の手動追加は明示的な配信操作としてONになる。初期配信先の投入と実際のメール送信・スケジュールは別の運用処理が担当する。Webアプリ自体はメールを送信しない。

## 検証

`node deployment/windows-server/test_editions.js` と `node deployment/windows-server/test_auth.js` を実行する。前者は一時ルートで実際のHTTPサーバー・SQLiteを起動し、ゲスト閲覧、受信初期値と停止の永続化、本人認証、Cookie・アクセス数・いいね・ブラウザ保存キーの分離、内装版の既存動作を検証する。実データやメールにはアクセスしない。
