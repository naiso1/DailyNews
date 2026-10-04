"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const root = path.join(__dirname, "..");
const html = fs.readFileSync(path.join(root, "内装製品デイリーニュース.html"), "utf8");
const rows = [
  {id: "jp1955", title: 'トレイ "新製品" <テスト>', img: 'https://images.test/tray.jpg?a=1&amp;b=2'},
  {id: "jp1956", duplicateOf: "jp1955"},
  {id: "cn1", title: "非表示の記事", img: "hidden.jpg"},
  {id: "cn2", duplicateOf: "cn1"},
  {id: "paper1", country: "paper", title: "画像のない論文"},
];
const map = new Map(rows.map(row => [row.id, row]));
for (const edition of ["interior", "exterior"]) {
  const ctx = vm.createContext({NEWS_DATA: rows, window: {DAILYNEWS_CONFIG: {id: edition},
    interactionsData: {cn1: {hidden: true}}}, rankingBackState: null,
    showNewsItem(id) { ctx.rankingBackState = {id}; }});
  for (const name of ["escapeHtml", "formatRichText", "normalizeAnalysisRefs", "getNewsLookup", "isGloballyHidden",
    "resolveNewsItem", "getNewsImageUrl", "getDisplayImageUrl", "renderIdeaDescription", "showNewsItemFromRef"]) {
    const start = html.indexOf(`        function ${name}(`);
    assert(start >= 0, name);
    const end = html.indexOf("\n        }", start) + "\n        }".length;
    vm.runInContext(html.slice(start, end), ctx);
  }
  const rendered = ctx.renderIdeaDescription({id: 1897,
    desc: '**収納トレイ**を提案します。 [id: jp1956, jp1955] [cn2] [missing1]\n次の文。',
    sourceNewsIds: ["jp1955", "paper1", "jp1956", "');alert(1)//"]}, map);
  assert.equal((rendered.match(/class="analysis-float-source idea-source-card/g) || []).length, 2, "Aliases and metadata citations are deduplicated");
  assert.match(rendered, /src="https:\/\/images.test\/tray.jpg\?a=1&amp;b=2"/);
  assert.match(rendered, /トレイ &quot;新製品&quot; &lt;テスト&gt;/);
  assert.match(rendered, /<strong>収納トレイ<\/strong>/);
  assert.match(rendered, /次の文。/);
  assert(!rendered.includes("非表示の記事") && !rendered.includes("hidden.jpg"));
  assert(!rendered.includes("[jp") && !rendered.includes(">jp1955<"));
  assert(!rendered.includes("alert(1)"));
  assert.match(rendered, /idea-source-noimage[^]*画像のない論文/);
  const onclick = rendered.match(/onclick="([^"]+)"/)[1];
  vm.runInContext(onclick, ctx);
  assert.equal(ctx.rankingBackState.id, "jp1956", "Original citation link still resolves through the existing article navigation");
  assert.equal(ctx.rankingBackState.scrollTarget, "idea-card-1897");
  ctx.showNewsItemFromRef("jp1955");
  assert.equal(ctx.rankingBackState.scrollTarget, "analysisSection", "Analysis return behavior stays intact");
  const classes = new Set();
  ctx.failedImage = {style: {}, parentElement: {classList: {add: value => classes.add(value)}}};
  const onerror = rendered.match(/onerror="([^"]+)"/)[1];
  vm.runInContext(`(function(){${onerror}}).call(failedImage)`, ctx);
  assert.equal(ctx.failedImage.style.display, "none");
  assert(classes.has("idea-source-noimage"), "Missing image preserves the clickable title with the text-only layout");
  const metadataOnly = ctx.renderIdeaDescription({id: 1, desc: "ID記載のない企画", sourceNewsIds: ["jp1955"]}, map);
  assert.match(metadataOnly, /参考ニュース/);
  assert(!ctx.renderIdeaDescription({id: 1, desc: "<script>テキスト</script>"}, map).includes("<script>"));
  assert.equal(ctx.renderIdeaDescription({id: 1, desc: "出典なし"}, map), '<p class="idea-desc">出典なし</p>');
  ctx.window.interactionsData.jp1955 = {imageUrlOverride: "images/corrected.jpg"};
  assert.match(ctx.renderIdeaDescription({id: 1, desc: "[jp1955]"}, map), /images\/corrected.jpg/);
}
// Parse every inline script and check the deployed shared renderer's call site.
for (const match of html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)) {
  if (match[1].trim()) new vm.Script(match[1]);
}
assert.match(html, /\$\{renderIdeaDescription\(idea, newsById\)\}/);
assert(!html.includes("formatInlineTextWithRefs"));
console.log("Idea references: both editions, images/titles, aliases, hidden/missing articles, metadata, fallback and return navigation PASS");
