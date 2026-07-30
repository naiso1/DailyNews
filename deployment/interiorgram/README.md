# Interiorgram

車室内装の企画アイデアと生成画像を蓄積・共有する社内向けWebアプリです。

- 公開URL: `http://IEWEB01/interiorgram/`
- サーバー配置先: `C:\Users\Administrator\Desktop\Interiorgram`
- Web: IIS子アプリケーションから `127.0.0.1:8083` へリバースプロキシ
- API: Node.js標準機能
- データ: SQLite (`data\interiorgram.sqlite`)
- コンテンツ原本: `content\posts.json`
- 画像原本: `content\images`

## Antigravityから追加

Antigravityでは `.agents/workflows/interiorgram.md` の手順を使用します。企画文と画像を生成した後、次を実行すると、ローカルのコンテンツ更新からIEWEB01への再配置まで自動で行います。

```powershell
python -u .\deployment\interiorgram\tools\add_post.py `
  --manifest "生成したJSONのパス" `
  --image "生成した画像のパス"
```

JSONの項目は `content\post-template.json` を参照してください。同じIDを修正して再公開する場合は `--replace` を付けます。サーバーへ公開せずローカルだけ更新する場合は `--no-publish` を付けます。

## 手動公開

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\deployment\interiorgram\publish.ps1
```

配置後は画面とヘルスチェックを確認します。

```powershell
Invoke-WebRequest -UseBasicParsing http://IEWEB01/interiorgram/ |
  Select-Object StatusCode

Invoke-RestMethod http://IEWEB01/interiorgram/health
```

## サーバー運用

- `InteriorgramServer`: Windows起動時にNodeサーバーを起動
- `InteriorgramBackup`: 毎日4:40にSQLiteをバックアップ
- バックアップ先: `C:\Users\Administrator\Desktop\Interiorgram\backups`
- 保持期間: 35日
- サーバーログ: `C:\Users\Administrator\Desktop\Interiorgram\logs\server.log`

コンテンツとプログラムの更新時も、SQLiteの反応データとバックアップは上書きしません。
