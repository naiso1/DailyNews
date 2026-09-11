const { test } = require("node:test");
const assert = require("node:assert/strict");
const { extractPrices, renderCurrency, articleUrl } = require("../dailynews_annotations.js");

test("Indian scales, grouping, ranges, and duplicate title/description prices", () => {
  assert.equal(extractPrices("₹6.10 Lakh", "in")[0].amount, 610000);
  assert.equal(extractPrices("INR 1.2 crore", "in")[0].amount, 12000000);
  assert.equal(extractPrices("₹6,10,000", "in")[0].amount, 610000);
  assert.equal(extractPrices("10万ルピー", "in")[0].amount, 100000);
  for (const raw of ["₹10.66〜18.49Lakh", "₹10.66 - ₹18.49 Lakhs", "10.66〜18.49万ルピー"]) {
    const p = extractPrices(raw, "in")[0];
    const scale = raw.includes("万") ? 1e4 : 1e5;
    assert.equal(p.amount, 10.66 * scale, raw);
    assert.equal(p.end, 18.49 * scale, raw);
  }
  assert.equal(extractPrices("₹6.10 Lakh。価格は₹6.10 Lakh。", "in").length, 1);
});

test("explicit currencies and regional ambiguity", () => {
  for (const [raw, code, amount] of [
    ["29.98万元", "CNY", 299800], ["USD 42,000", "USD", 42000],
    ["€38,500", "EUR", 38500], ["£100", "GBP", 100],
    ["2億ウォン", "KRW", 2e8], ["A$35,000", "AUD", 35000],
    ["1.5 million USD", "USD", 1.5e6], ["US$100", "USD", 100],
  ]) {
    assert.equal(extractPrices(raw)[0]?.code, code, raw);
    assert.equal(extractPrices(raw)[0]?.amount, amount, raw);
  }
  assert.equal(extractPrices("$100", "us")[0].inferred, true);
  for (const raw of ["$100", "10ドル", "¥100", "￥100", "100円", "Rs 100", "ルピー100", "C$100と$200", "2次元", "€1.234,56", "€1,2", "ABCUSD123", "₹2 lakhsabc"]) {
    assert.ok(!extractPrices(raw, "jp").some(p => p.code === "USD" || p.code === "INR" || p.code === "EUR" || p.code === "JPY" || p.code === "CNY"), raw);
  }
  assert.equal(extractPrices("USD 100〜EUR 200").length, 0);
  for (const raw of ["-100ドル", "1 234ドル", "Rs 12,34", "€1.234"]) {
    assert.equal(extractPrices(raw, raw.startsWith("Rs") ? "in" : "us").length, 0, raw);
  }
});

test("compound Japanese money, complete ranges and invalid unit order", () => {
  for (const [raw, amount] of [
    ["31万3千ドル", 313000], ["３１万３千ドル", 313000],
    ["1億2000万ドル", 120000000], ["USD 31万3000", 313000],
    ["31万3千500米ドル", 313500], ["1億2万3千ドル", 100023000],
  ]) assert.equal(extractPrices(raw, "us")[0]?.amount, amount, raw);
  const range = extractPrices("31万3千〜32万ドル", "us")[0];
  assert.equal(range.amount, 313000);
  assert.equal(range.end, 320000);
  for (const raw of ["1千2万ドル", "1万2万ドル", "1.5万3千ドル", "1万10000ドル", "31万3千円", "31万3千", "31万3 thousandドル"]) {
    assert.equal(extractPrices(raw, "us").length, 0, raw);
  }
  assert.equal(extractPrices("31万3千ドル", "jp").length, 0);
});

test("September 11 INR corrections and us1620 yen conversion", () => {
  const snapshot = { base: "JPY", date: "2026-09-10", rates: { INR: 1.61539537, USD: 154.1752754821 } };
  const now = new Date("2026-09-11T12:00:00+09:00");
  for (const [amount, expected] of [["192.2", 1922000], ["192.1", 1921000], ["244.9", 2449000]]) {
    const item = { desc: `価格は${amount}万ルピーから。`, country: "in" };
    assert.equal(extractPrices(item.desc, "in")[0]?.amount, expected);
    assert.match(renderCurrency(item, snapshot, now), /円換算/);
  }
  const html = renderCurrency({ desc: "価格は31万3千ドル。", country: "us" }, snapshot, now);
  assert.match(html, /4,825\.7万円/);
  assert.match(html, /313,000 USD/);
});

test("rate age, missing rates, exact conversion, and escaped output", () => {
  const snapshot = { base: "JPY", date: "2026-09-07", rates: { INR: 1.72 } };
  const item = { title: "₹6.10 Lakh", country: "in" };
  const output = renderCurrency(item, snapshot, new Date("2026-09-08T12:00:00+09:00"));
  assert.match(output, /104\.9万円/);
  assert.match(output, /1,049,200円/);
  assert.match(output, /2026-09-07/);
  assert.match(renderCurrency(item, snapshot, new Date("2026-09-20")), /取得できていません/);
  assert.equal(renderCurrency({ title: "100円" }, snapshot), "");
  assert.match(renderCurrency(item, undefined), /取得できていません/);
  assert.equal(renderCurrency({title:"USD 100"}, snapshot, new Date("2026-09-08")), "");
});

test("verified text fragment preserves query and encodes delimiter characters", () => {
  const item = {url:"https://example.com/article?page=2#old", sourceExcerpt:"table-a, & b", sourceExcerptEnd:"欲しかった。"};
  const href = articleUrl(item);
  assert.equal(href, "https://example.com/article?page=2#:~:text=table%2Da%2C%20%26%20b," + encodeURIComponent(item.sourceExcerptEnd));
  assert.equal(item.url, "https://example.com/article?page=2#old");
  assert.equal(articleUrl({url:"https://example.com/a", sourceExcerpt:"exact quote"}), "https://example.com/a#:~:text=exact%20quote");
});

test("ordinary article URLs are unchanged and unsafe URLs are rejected", () => {
  const url = "https://example.com/article?source=rss&page=2#section";
  assert.equal(articleUrl({url}), url);
  assert.equal(articleUrl({url, sourceExcerpt:""}), url);
  for (const url of ["javascript:alert(1)", "data:text/html,test", "file:///C:/test", "not a URL", undefined]) {
    assert.equal(articleUrl({url, sourceExcerpt:"x"}), "");
  }
});
