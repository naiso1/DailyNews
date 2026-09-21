# 画像URL付きRSSの追加（2026-09-21）

対象外記事で件数を補わず、画像付きの候補を増やすため、内装・外装へ各8本を追加した。設定総数は内装88本（論文1本を含む）、外装85本。既存媒体のカテゴリ違いを増やすのではなく、新しい発信元を選んだ。

## 追加した情報源

| 地域 | 配信元 | 主な用途 |
|---|---|---|
| 日本 | [AutoProve](https://autoprove.net/feed/) | 新車・装備・内外装の変更 |
| 米国 | [Ars Technica Cars](https://arstechnica.com/cars/feed/) | 車両レビュー、車室・操作性・技術 |
| 米国 | [Plastics Engineering / Automotive & Transportation](https://www.plasticsengineering.org/c/industry/automotive-transportation/feed/) | 樹脂材料、表面性能、循環性 |
| 欧州 | [Automotive Testing Technology International](https://www.automotivetestingtechnologyinternational.com/feed) | 車両・部品の評価、試験技術 |
| 中国 | [ChinaEVHome](https://chinaevhome.com/feed/) | 中国車の製品・装備・市場動向 |
| インド | [Car India](https://carindia.in/feed/) | 独自試乗、内外装レビュー（週次程度） |
| インド | [MotorOctane](https://motoroctane.com/feed) | 新車・装備情報 |
| インド | [Motoroids](https://www.motoroids.com/feed/) | 新車・装備・市場動向 |

## 収集条件

- 追加した8本はすべて `require_feed_image: true`。RSS内の画像URLがない記事は、記事ページやブラウザで画像を補う前に除外する。
- 画像はHTTP(S)のみ。動画、ロゴ、プレースホルダー等を除外する。相対URL・srcset・media thumbnail・enclosureも読み取る。
- 既存RSSの画像補完、対象日、版ごとの関連性、採用根拠、重複除去は維持する。
- 各国最大10件という掲載上限は維持する。対象外記事や重複で10件へ埋めない。内装のLLM前候補上限30件、外装60件も維持する。
- 日別に均等配分する処理は追加していない。RSSが返す過去記事の範囲も媒体ごとに異なる。

## 既存ソースの取りこぼし修正

Gasgooの記事写真は `imagecn.gasgoo.com/moblogo/News/UEditor/` にあり、`logo` の部分一致で誤って除外されていた。この既知のディレクトリ名だけ例外にし、ファイル名のロゴ・プレースホルダー判定は維持した。

Gasgoo本文は内装でもHTMLの文字コード指定を読み、`#ArticleContent` の本文だけを取得する。ナビゲーションや文字化けした保存本文を採用根拠にしない。追加した試験技術・樹脂媒体でも、記事本文より先にあるナビゲーションカードを拾わないよう抽出箇所を指定した。

## 確認結果と範囲

- 追加8媒体×3記事＝24記事でRSSの日付・画像URL、本文、画像のHTTP取得・デコードを確認。
- AutoProveのRSS画像は376×282px。記事サムネイルとして採用し、この媒体だけ検証下限を320×180pxとした。ほか7媒体は既存の600×300px基準を通過。
- Gasgooは実画像3枚、内装・外装それぞれ3本文で修正後の取得を確認。中国語の短報は285〜530文字で、ナビゲーション除去後の正常な原文である。
- RSS・本文取得・日付・重複・関連性の回帰テスト70件成功。
- 更新停止、RSS画像なし、取得拒否、本文や画像の取得不良がある候補は追加しなかった。

この確認は調査時点のサンプル取得であり、毎日各国10件の掲載を保証するものではない。次回定期収集から追加元を使い、対象内の記事の増加を確認する。

詳細な取得結果は非公開の `runtime/rss-expansion-20260921/` に保存。追加判断の再検証には `tests/verify_rss_sources.py` を使う（本文収集・AI判定・公開を一括実行しない）。
