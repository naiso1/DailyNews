# DailyNews：内装・外装ニュース

ニュース収集・日本語要約・考察・企画アイデアを共通の処理で作成します。アカウントは内装・外装で共通とし、公開先・アクセス集計・記事への反応・メール購読は版ごとに分離します。

## 普段見る場所

| 場所 | 用途 |
| --- | --- |
| `editions/exterior/` | 外装の対象製品、検索条件、採用基準、AIへの指示 |
| `content/exterior/` | 外装の公開用記事・考察・画像。配信名簿・認証情報を置かない |
| `runtime/exterior/` | 外装の収集中間CSV、キャッシュ、ログ、配備準備。Git対象外 |
| `dailynews/` | 共通の版設定・外装判定など |
| `ニュース収集/` | 共通収集処理と既存内装設定・中間ファイル |
| `deployment/workstation/` | 処理PCの起動・GPU順次実行 |
| `deployment/windows-server/` | 共通Web APIと版別公開 |
| `deployment/notifications/` | 外装のPower Automate通知設定 |
| `docs/` | 外装試用の運用説明・メンバーヒアリング |
| `tests/` | 収集・要約・運用の検査 |

内装の既存 `news_data.js`、`insights_data.js`、HTML、画像は、現在の自動処理や公開経路との互換性のためルートに維持しています。外装のデータはルートに追加しません。旧レビュー・一時作業用スクリプトは日次運用の入口ではありません。

## 外装版の初期方針

- 社内URLから閲覧可能。書き込み・お気に入り同期・メール設定は内装・外装共通のアカウントで操作。既存の内装ID・パスワードを使える。
- マイページの2つのチェック欄で内装だけ・外装だけ・両方・受信なしを選ぶ。外装からの新規登録は両方オフ。既存の購読設定は維持する。
- 初期の手動配信先は管理者1名。名簿はWebサーバーのDBと業務OneDriveで管理。
- 5地域。製品・技術に加え、外装開発の判断に役立つデザイン・市場・規制・材料・競合のトレンドを選定。当日分を優先し直近7日の未掲載記事で各地域10件を目指す。製品6・トレンド4を目安に柔軟に補完する。画面で記事区分を切り替えられる。
- 元記事の画像は利用する。外装の企画画像はexaBaseで最新号の各地域2案、既存画像を含めて最大10枚を生成する。有料画像APIへの代替は行わない。内装は2026-09-15より後の最新号からexaBaseを優先し、失敗案だけ既存Gemini APIへ代替する。画面には画像ごとにexaBase／APIの生成元を表示する。既存画像・過去号は再生成せず、画像が得られない場合も文章を公開する。詳しくは[画像生成の運用手順](deployment/workstation/exabase/README.md)を参照。
- 外装と内装で同じ原記事を採用してよい。採用履歴・関連度・要約・公開状態は分離。

## 処理の入口

運用Pythonは `%LOCALAPPDATA%\DailyNewsRuntime\venv\Scripts\python.exe`。`google_search_script.py --help` は収集開始の副作用があるため、確認目的で実行しないでください。

```powershell
# 外装だけを作成。Git、サーバー公開、配信状態の更新をしない。
& "$env:LOCALAPPDATA\DailyNewsRuntime\venv\Scripts\python.exe" -B deployment/workstation/run.py --edition exterior --build-only

# 外装だけを通常処理（公開・通知用状態更新を含む）。メール自体は8時フローが送信。
& "$env:LOCALAPPDATA\DailyNewsRuntime\venv\Scripts\python.exe" -B deployment/workstation/run.py --edition exterior
```

定期実行は既存タスクから私有 `workstation.json` の `editions` 順に実行します。1本のロックで同時GPU処理を防ぎ、片方が失敗しても次の版へ進みます。旧PCは再有効化しません。

日本語化に失敗した記事は原文と失敗状態を保存して保留し、正常な記事の更新を続けます。全記事が未翻訳の場合は公開を止めます。[保留記事の確認・復旧手順](docs/summary-quarantine.md)を参照してください。

考察の短縮で参照が欠けた場合は、検査を通った短縮前の文章を保持します。[考察を短くするときの引用保持](docs/analysis-citation-preservation.md)を参照してください。

詳細：[外装試用ガイド](docs/exterior-pilot.md)、[Webと購読](deployment/windows-server/EDITIONS_WEB.md)、[処理PC](deployment/workstation/README.md)。
