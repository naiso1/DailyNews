# Interiorgram deployment

既存の「溢れ出す企画アイデア画像」プロジェクトを、社内サーバーのIIS配下へ公開します。画面・アイデアデータ・画像は既存プロジェクトを原本とし、DailyNews側では公開処理とサーバーAPIだけを管理します。

- 原本: `C:\Users\demo\Desktop\中村\溢れ出す企画アイデア画像`
- 原本GitHub: `naiso1/Idea-Image-Instagram`
- 公開URL: `http://IEWEB01/interiorgram/`
- サーバー配置先: `C:\Users\Administrator\Desktop\Interiorgram`
- Web: IIS子アプリケーションから `127.0.0.1:8083` へリバースプロキシ

## 公開する内容

- 既存の `index.html`、`style.css`、`script.js`
- `data.js` に登録されている全アイデア
- `images` フォルダー内の画像
- 既存の検索、フィルター、モーダル、複数画像表示
- 社内LAN利用者間で共有される、いいね数とコメント

公開時に `data.js` からサーバーAPI用の `data.json` を自動生成します。旧 `data.json` と内容がずれていても、画面と同じ `data.js` が基準になります。参照画像が欠けている場合は公開を中止します。

## Antigravityから追加

Antigravityでは、原本プロジェクトの `.agent\workflows` にある既存ワークフローを使います。企画文・画像・`data.js` の更新後、ワークフローから次のスクリプトを実行します。

```powershell
& "C:\Users\demo\Desktop\中村\溢れ出す企画アイデア画像\publish_to_ieweb01.ps1"
```

これにより、89件の既存コンテンツを含む最新状態がIEWEB01へ自動反映されます。

## 手動公開

DailyNews側から直接実行する場合:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\deployment\interiorgram\publish.ps1
```

確認:

```powershell
Invoke-WebRequest -UseBasicParsing http://IEWEB01/interiorgram/ |
  Select-Object StatusCode

Invoke-RestMethod http://IEWEB01/interiorgram/health
```

## サーバー運用

- `InteriorgramServer`: Windows起動時にNodeサーバーを起動
- `InteriorgramBackup`: 毎日4:40にアイデアデータと反応データをバックアップ
- 反応データ: `C:\Users\Administrator\Desktop\Interiorgram\data\reactions.json`
- バックアップ先: `C:\Users\Administrator\Desktop\Interiorgram\backups`
- 保持期間: 35日
- サーバーログ: `C:\Users\Administrator\Desktop\Interiorgram\logs\server.log`

サーバーへの再公開時も、いいねとコメントは上書きしません。
