# Power Automateの配信判定

## 成否ファイル

DailyNewsは処理開始時に`running`、全工程の完了後にだけ`success`を書き込みます。
出力先は次の2か所です。

- ローカル: `ニュース収集/logs/latest_run_status.json`
- 業務用OneDrive: `DailyNewsAutomation/latest_run_status.json`

OneDriveへ出力するには、このPCのOneDriveへ業務アカウントでサインインしている必要があります。
未設定の場合はローカルだけへ出力し、ログにOneDriveのパスは表示されません。

ニュース生成、Git同期、IEWEB01への公開、公開日付の確認がすべて成功した場合だけ
`status`が`success`になります。電源断や強制終了では`running`または前日以前の
ファイルが残るため、成功扱いにはなりません。

## 8:00のフロー

1. タイムゾーンを`Tokyo Standard Time`にして毎日8:00に実行する。
2. OneDrive for Businessの「ファイル コンテンツの取得」で
   `DailyNewsAutomation/latest_run_status.json`を読む。
3. 「JSONの解析」を追加する。
4. 次の全条件を満たす場合だけ、関係者向けメールを送信する。
   - `status`が`success`
   - `run_date`が東京時間の本日
   - `expected_news_date`が東京時間の昨日
   - `published_news_date`が`expected_news_date`以上
5. 条件を満たさない場合は管理者だけへ異常メールを送信する。
6. `status`が`paused`の場合は、どちらのメールも送らない。

成功メールの宛先には別途作成するメーリングリストを設定します。失敗メールの宛先は
`yuki.nakamura@toyoda-gosei.co.jp`だけにします。

既存の無条件送信アクションは削除するか、成功側の分岐内へ移動してください。

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
