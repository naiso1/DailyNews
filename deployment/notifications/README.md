# 外装メール配信の設定と運用

## 現在の設定

2026-09-15 に外装専用フローを作成し、サイト公開、外装の成功RSS、初期配信先1名、配信条件を確認して有効化済み。現在は `Started`（稼働中）。実際のメール受信は次回の定時配信で確認する。

- 名前: 外装製品デイリーニュース 平日08時配信
- フローID: `21cc618b-ffb2-46d9-830f-9ba0444cfbef`
- [Power Automateの外装フロー](https://make.powerautomate.com/environments/Default-2113d5b5-fefb-4c1d-bc26-12d7f8c3581d/flows/21cc618b-ffb2-46d9-830f-9ba0444cfbef/details)
- 実行: 月～金 08:00、Tokyo Standard Time
- 判定RSS: `https://naiso1.github.io/DailyNews/content/exterior/automation_status.xml`
- 成功文字列: `DailyNews exterior success <東京時間の本日 yyyy-MM-dd>`
- 宛先: OneDrive の `/DailyNewsAutomation/exterior/mailing_list.json` にある `to`
- 案内先: `http://IEWEB01/exterior/`
- 異常通知: 設定済みの管理者1名

初期配信先は管理者1名。ほかの利用者は社内ネットワークから外装URLを開くだけで閲覧でき、メール購読は必須ではない。2026-09-16からログインは内装・外装共通とし、登録画面またはマイページのチェック欄で内装だけ・外装だけ・両方・受信なしを選ぶ。外装からの新規登録は両方オフ、既存の購読設定は維持する。配信名簿は引き続き版ごとに分ける。

## 購読変更の反映

Webの版別購読設定を正本とし、処理PCが内装・外装それぞれの有効な購読者を業務用OneDriveへ同期する。各Power Automateフローは朝8時の実行時に対応する宛先JSONを読み込む。

- 同期処理: [`sync-mailing-list.py`](../workstation/sync-mailing-list.py)
- タスク登録: [`install-mailing-list-sync.ps1`](../workstation/install-mailing-list-sync.ps1)
- タスク名: `DailyNews_ExteriorMailingListSync`
- 周期: 2分。ニュース収集やメール送信は行わず、内装・外装の宛先を各ファイルへ同期する。タスク名は重複登録を避けるため維持。
- 同期結果: 処理PCの `%LOCALAPPDATA%\DailyNewsRuntime\mailing-list-sync.json`

2026-09-15 に同期タスクを登録済み。同期処理を実行し、宛先JSONの `edition_id` が `exterior` であること、初期の有効宛先が管理者1名であることを確認済み。

同期タスク稼働後、購読のオン・オフは通常、次回同期まで最長約2分で宛先JSONに反映される。Power Automate側で使えるまでにはOneDriveの同期時間も加わるため、8時直前の変更は当日の配信に間に合わない場合がある。

処理PCの対象Windowsユーザーがサインインし、処理設定で外装が有効になっている必要がある。PC停止、サインアウト、通信障害などで同期が止まると、反映時間は延びる。障害確認には同期結果の日時とタスクの実行結果を使用する。

## 配信開始前の確認

1. `http://IEWEB01/exterior/` で外装記事を閲覧できることを確認する。
2. 公開確認を含む処理が完了し、外装RSSに当日の成功文字列があることを確認する。内装の成功RSSでは代用しない。
3. 宛先同期タスクを登録し、外装の宛先JSONがOneDriveに反映されることを確認する。初期の有効宛先は管理者1名とする。
4. 外装フローのID、平日08時、RSS URL、成功条件、宛先JSONパス、本文リンクを確認してから有効化する。
5. 最初の配信後、Power Automateの実行成功と実受信をそれぞれ確認する。

当日の成功を確認できない場合や宛先JSONの取得に失敗した場合は、購読者への更新メールを送らず管理者へ異常通知する。フローの有効化やメール送信成功だけでは、実受信まで確認したことにはならない。

## 再作成・保守

[`prepare-exterior-flow.ps1`](prepare-exterior-flow.ps1) は、内装フローの構成を読み取り、独立した外装フローを停止状態で作成するためのスクリプト。通常運用では上記の作成済み外装フローを使用する。再作成時には既存フローの有無を確認し、重複配信になるコピーを増やさない。

作成リクエストやフローIDの記録はGit対象外の `runtime/notifications/exterior` に保存する。購読者の氏名・メールアドレス、認証情報はこのREADMEや公開設定へ記載しない。内装フローIDは `94732731-b972-483b-b973-16dea2efa3fd`、環境は `Default-2113d5b5-fefb-4c1d-bc26-12d7f8c3581d`。

画像生成は外装の配信成功条件に含めない。exaBase画像が作れない場合も文章を公開し、画像APIへ代替しない。詳しくは[外装ニュースの試用手順](../../docs/exterior-pilot.md)を参照。

参考: [Microsoft公式 PowerShell手順](https://learn.microsoft.com/en-us/power-platform/admin/powerapps-powershell)、[RSSコネクタ](https://learn.microsoft.com/en-us/connectors/rss/)、[Power Automate Management](https://learn.microsoft.com/en-us/connectors/flowmanagement/)。
