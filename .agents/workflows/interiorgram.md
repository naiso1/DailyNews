---
description: 車室内製品の企画アイデアと画像を作成し、Interiorgramへ公開する
---

# Interiorgramへの企画追加

このワークフローでは、車室内製品の企画アイデアを1件作成し、イメージ画像とともに
`http://IEWEB01/interiorgram/`へ公開する。

## 必須方針

- 企画対象は、シート、インパネ、コンソール、ドアトリム、天井、照明、HMI、収納、
  表皮材、加飾、空調、車内センシングなど、具体的な車室内部品または体験にする。
- 抽象的な「AI内装」「快適空間」だけで終わらせず、対象ユーザー、利用場面、部品構成、
  提供価値、実現課題を具体化する。
- 過去の`deployment/interiorgram/content/posts.json`を確認し、既存企画と重複させない。
- 画像は車室内製品が主役だと一目で分かる構図にする。外観のみ、人物のみ、説明図のみは禁止。
- 画像内に読めない文字、企業ロゴ、既存ブランド名を描かない。
- 投稿文と画像の内容を一致させる。

## 手順

1. `deployment/interiorgram/content/posts.json`を読み、過去企画との重複を確認する。
2. 企画を作成し、`deployment/interiorgram/content/post-template.json`に従ったJSONを
   一時ファイルへUTF-8で保存する。
3. Antigravityの画像生成機能で、企画に対応する横長または正方形の画像を1枚生成する。
4. 次を実行する。IDは省略すれば日時から自動生成される。

```powershell
python -u .\deployment\interiorgram\tools\add_post.py `
  --manifest "生成したJSONのパス" `
  --image "生成した画像のパス"
```

5. コマンドは投稿追加後に自動でIEWEB01へ配布する。最後に次を確認する。

```powershell
Invoke-WebRequest -UseBasicParsing http://IEWEB01/interiorgram/ |
  Select-Object StatusCode

Invoke-RestMethod http://IEWEB01/interiorgram/health
```

## JSON品質

- `title`: 40文字程度まで。製品や体験が分かる具体名。
- `summary`: 120文字程度まで。カードだけで企画価値が分かる文章。
- `body`: 背景、対象ユーザー、構成、価値、実現課題を段落で記載。
- `category`: シート、コックピット、コンソール、素材、照明、HMI、収納など。
- `region`: 日本、中国、インド、米国、欧州、グローバルのいずれか。
- `tags`: 2～6個。
- `imageAlt`: 画像に写る部品、素材、利用場面を具体的に説明。
- `sourceIds`: DailyNewsを基にした場合はニュースIDを記載。
