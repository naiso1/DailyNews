# タイトル部分を従来表示に戻す

2026-10-16に採用したC案は、元のHTMLを残したまま表示時に組み替えています。
`dailynews_header.css` は `.header-visual` の中にだけ適用されます。

## 推奨：ヘッダーだけを戻す

1. ルートの `内装製品デイリーニュース.html` にある次の設定を変更します。

   ```html
   <meta name="dailynews-header-style" content="classic">
   ```

   C案を再び使う場合は `content="visual"` にします。
2. `release_history.js` の先頭へ、実際の変更日で「タイトルを従来表示へ戻しました」と追記します。
3. 上記2ファイルだけをコミットし、通常どおり内装・外装を公開します。

   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File deployment/windows-server/deploy.ps1 -Edition interior
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File deployment/windows-server/deploy.ps1 -Edition exterior
   ```

4. 両版を再読み込みし、PC幅・スマートフォン幅でタイトル、アカウント、通知、
   情報源、更新履歴、版の切り替え、アクセス分析を確認します。

この方法では最新の記事・コメント・いいね・閲覧記録・利用者設定を戻しません。
従来表示では従来どおり、狭い画面のタイトルが省略される場合があります。

## 実装前の参照点

- Git：`d3cbd6b39e575a6659887204d39d2c4f6a9c61b4`
- 変更前の保存タグ：`before-header-c-20261016`
- 内装の公開リリース：`d3cbd6b39e575a6659887204d39d2c4f6a9c61b4`
- 外装の公開リリース：`80f6821813a88274ad86c1cddb6dd8a1e9a01492`
- 作業端末の変更前HTML・更新履歴：`runtime/repairs/20261016/header-c-before/`

過去リリース全体への切り戻しは、その時点のニュースデータへも戻るため、
表示だけを戻したいときは上記の `classic` 設定を使ってください。
公開サーバー上の古いリリースは保持世代数により削除されるため、恒久的な復元元はGitです。
