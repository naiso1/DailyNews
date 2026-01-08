# 考察・企画アイデア生成プロンプト

このファイルは、ニュースダッシュボードの「考察」および「企画アイデア例」を生成する際に使用するプロンプトテンプレートです。

---

## 考察（Analysis）生成プロンプト

### 目的
各国・地域のニュースから、自動車内装製品開発に関連するトレンドや示唆を抽出し、簡潔にまとめる。

### プロンプトテンプレート

```
以下の{国名}の自動車内装関連ニュース{件数}件を分析し、内装製品開発の観点から考察を生成してください。

【対象ニュース】
{ニュース一覧（タイトル、概要）}

【生成ルール】
1. 200〜300文字程度で簡潔にまとめる
2. 重要なキーワードは**太字**で強調する
3. 以下の観点を意識する：
   - 技術トレンド（HMI、素材、センサー等）
   - 消費者ニーズの変化
   - 競合他社の動向
   - 規制・政策の影響
   - サプライチェーンの動向
4. 自社の内装製品開発への示唆を含める
5. 日本語で出力する

【出力形式】
考察テキストのみ（マークダウン形式）
```

---

## 企画アイデア例（Ideas）生成プロンプト

### 目的
考察を踏まえ、具体的な内装製品の企画アイデアを提案する。各国・地域ごとに2件程度。

### プロンプトテンプレート

```
以下の考察を踏まえ、{国名}市場向けの内装製品企画アイデアを2件提案してください。

【考察】
{考察テキスト}

【対象ニュース】
{ニュース一覧（タイトル、概要）}

【生成ルール】
1. 各アイデアには以下を含める：
   - タイトル（20〜40文字）：製品コンセプトを端的に表現
   - 説明（100〜150文字）：製品の特徴、ターゲット、差別化ポイント
2. 実現可能性を考慮しつつ、革新性も追求する
3. 関連するニュースのトレンドを反映させる
4. 日本語で出力する
5. 画像生成用のプロンプトも併記する（英語、50〜100 words）

【出力形式（JSON）】
{
  "ideas": [
    {
      "title": "タイトル",
      "desc": "説明文",
      "imagePrompt": "English prompt for AI image generation: description of the product concept visualization, automotive interior design, photorealistic rendering"
    }
  ]
}
```

---

## 画像生成プロンプト（Image Prompt）テンプレート

### 目的
企画アイデアのコンセプト画像をAI（generate_image）で生成する。

### プロンプト構造

```
{Product description}, automotive interior design concept, {specific features}, 
modern vehicle cockpit, {materials and colors}, premium quality, 
photorealistic rendering, professional product visualization, 
cinematic lighting, high detail, 4K quality
```

### 例
- コンソール一体型香りディフューザー:
  `Integrated aromatherapy diffuser built into center console, ambient lighting effects, luxury car interior, brushed aluminum and leather materials, subtle mist effect, warm ambient glow, photorealistic 3D render, premium automotive design`

- AIアシスタント搭載HUD:
  `Advanced augmented reality head-up display in premium vehicle, holographic interface floating above dashboard, AI assistant visualization, futuristic cockpit design, night driving scene, blue accent lighting, photorealistic render`

---

## 使用方法

1. **ニュース追加時**: `news_data.js` に新しいニュースを追加した日付に対応
2. **考察生成**: 上記の考察プロンプトを使用し、各国のニュースを分析
3. **アイデア生成**: 考察を踏まえてアイデアプロンプトを実行
4. **画像生成**: 各アイデアのimagePromptを使用してgenerate_imageツールで画像作成
5. **データ反映**: `insights_data.js` に考察とアイデアを追加

---

## ID採番ルール

- アイデアIDは全日付を通じて連番管理
- 既存の最大ID + 1 から開始
- 各国2件ずつ、1日あたり計10件（jp, cn, in, us, eu × 2）

---

## ファイル命名規則（画像）

| 形式 | 例 |
|-----|-----|
| `{国コード}_{内容}_{日付}.png` | `jp_console_diffuser_0106.png` |
| `{国コード}_{内容}_{連番}.png` | `cn_hud_display_01.png` |

---

最終更新: 2026-01-08
