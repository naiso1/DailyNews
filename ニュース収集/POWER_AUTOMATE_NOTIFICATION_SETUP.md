# Power Automateの配信判定

## 成否ファイル

DailyNewsは処理開始時に`running`、全工程の完了後にだけ`success`を書き込みます。
出力先は次の2か所です。

- ローカル: `ニュース収集/logs/latest_run_status.json`
- 業務用OneDrive: `DailyNewsAutomation/latest_run_status.json`
- Power Automate判定用RSS: `https://naiso1.github.io/DailyNews/automation_status.xml`

OneDriveへ出力するには、このPCのOneDriveへ業務アカウントでサインインしている必要があります。
未設定の場合はローカルだけへ出力し、ログにOneDriveのパスは表示されません。

ニュース生成、Git同期、IEWEB01への公開、公開日付の確認がすべて成功した場合だけ
`status`が`success`になります。電源断や強制終了では`running`または前日以前の
ファイルが残るため、成功扱いにはなりません。

Power Automate判定用RSSには成否、実行日、公開対象日だけを含め、ログのパスや
メールアドレスなどは公開しません。処理失敗時もRSSの更新を試みます。PC停止や
GitHub通信障害で更新できなかった場合は前日のRSSが残り、日付不一致により失敗扱いになります。

## 8:00のフロー

1. タイムゾーンを`Tokyo Standard Time`にして毎日8:00に実行する。
2. RSSの「すべてのRSSフィード項目を一覧表示する」で判定用RSSを読む。
3. RSS本文に`DailyNews success <東京時間の本日>`が含まれる場合だけ、関係者向けメールを送信する。
4. 成功表記がない、`failed`である、日付が古い、RSSを取得できない場合は管理者だけへ異常メールを送信する。

成功メールの宛先には別途作成するメーリングリストを設定します。失敗メールの宛先は
`yuki.nakamura@toyoda-gosei.co.jp`だけにします。

既存の無条件送信アクションは削除するか、成功側の分岐内へ移動してください。

業務用OneDriveのJSONは、障害調査用の詳細情報として引き続き保存します。

## JSON解析スキーマ

```json
{
  "type": "object",
  "properties": {
    "status": { "type": "string" },
    "run_date": { "type": "string" },
    "expected_news_date": { "type": "string" },
    "published_news_date": { "type": "string" },
    "updated_at": { "type": "string" },
    "error": { "type": "string" },
    "log_file": { "type": "string" },
    "site_url": { "type": "string" },
    "release": { "type": "string" }
  }
}
```
