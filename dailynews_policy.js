"use strict";

// Use the same published article IDs, titles and sources for display and Copilot.
window.DailyNewsPolicy = (() => {
  const topics = [
    ["関税", /関税/], ["輸入枠", /輸入枠|輸入数量/], ["原産地", /原産地|日本製部品|欧州製/],
    ["補助金", /補助金|購入補助|リース補助/], ["自動運転", /自動運転|自動運行|無人シャトル/],
    ["シート", /シート|座席/], ["安全基準", /保安基準|安全基準/], ["サブスク", /定額課金|サブスク/],
    ["排出規制", /Euro\s*7|排出規制/i], ["EV", /EV|電動化|電気乗用車/],
    ["ハイブリッド", /ハイブリッド/], ["法人車両", /法人.*(?:車両|乗用車|リース)/],
    ["歩行者保護", /歩行者.{0,6}保護/], ["灯火", /灯火|前照灯|識別灯/],
    ["外装材料", /外装樹脂|外装材料|再生プラスチック/],
  ];
  let previousIssues, previousHighlights;
  let index = new Map();
  function articles() {
    const issues = window.DAILYNEWS_POLICY_ISSUES;
    const highlights = window.DAILYNEWS_POLICY_HIGHLIGHTS;
    if (issues === previousIssues && highlights === previousHighlights) return index;
    const daily = Object.entries(issues || {}).flatMap(([date, cards]) =>
      cards.map((card, i) => ({ ...card, date, id: card.id || `policy-${date}-${i + 1}` })));
    const next = new Map();
    for (const card of daily.concat(highlights?.cards || [])) {
      if (!/^policy-[a-z0-9][a-z0-9-]{0,92}$/.test(card.id)) continue;
      const [source, url] = card.links?.[0] || [];
      const text = [card.title, card.summary, card.question].join(" ");
      const tags = topics.filter(([, pattern]) => pattern.test(text)).map(([tag]) => tag);
      next.set(card.id, { ...card, country: "policy", source, url, desc: card.summary,
        tags: tags.length ? tags : ["法規・政策"] });
    }
    previousIssues = issues;
    previousHighlights = highlights;
    index = next;
    return index;
  }
  return { articles };
})();
