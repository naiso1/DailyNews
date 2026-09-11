"use strict";

// No per-visitor FX requests: all cards share the dated published snapshot.
((root) => {
  const escape = (value) => String(value ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]);
  const names = {
    USD: "米ドル", EUR: "ユーロ", GBP: "英ポンド", CNY: "人民元", INR: "インドルピー",
    KRW: "韓国ウォン", AUD: "豪ドル", CAD: "カナダドル", HKD: "香港ドル",
    TWD: "台湾ドル", SGD: "シンガポールドル", CHF: "スイスフラン",
  };
  const units = { lakh: 1e5, lakhs: 1e5, lac: 1e5, lacs: 1e5, crore: 1e7, crores: 1e7,
    ラック: 1e5, ラク: 1e5, クロール: 1e7, 千: 1e3, 万: 1e4, 百万: 1e6, 億: 1e8,
    billion: 1e9, million: 1e6, thousand: 1e3 };
  const currency = "US\\$|U\\.S\\.\\$|A\\$|C\\$|HK\\$|S\\$|NT\\$|USD|EUR|GBP|CNY|RMB|INR|KRW|AUD|CAD|HKD|SGD|TWD|CHF|Rs\\.?|₹|€|£|₩|\\$|米ドル|米国ドル|人民元|中国元|インドルピー|ルピー|ユーロ|英ポンド|ポンド|韓国ウォン|ウォン|豪ドル|豪州ドル|カナダドル|香港ドル|台湾ドル|シンガポールドル|スイスフラン|ドル|元";
  const number = "(?:\\d{1,3}(?:,\\d{3})+|\\d{1,2}(?:,\\d{2})*,\\d{3}|\\d+)(?:\\.\\d+)?";
  const quantity = `${number}(?:\\s*[億万千]\\s*${number})*`;
  const scale = "billion|million|thousand|lakhs?|lacs?|crores?|クロール|ラック|ラク|百万|千|万|億";
  const pricePattern = new RegExp(
    `(?:(?<prefix>${currency})\\s*)?(?<first>${quantity})\\s*(?<scale1>${scale})?` +
    `(?:\\s*(?<mid>${currency}))?` +
    `(?:\\s*(?:[~〜～–—-]|to|から)\\s*(?:(?<prefix2>${currency})\\s*)?(?<second>${quantity})\\s*(?<scale2>${scale})?)?` +
    `(?:\\s*(?<suffix>${currency}))?`, "gi",
  );

  function quantityValue(raw, ownScale, sharedScale) {
    if (!/[億万千]/.test(raw)) {
      return Number(raw.replaceAll(",", "")) * (units[(ownScale || sharedScale || "").toLowerCase()] || 1);
    }
    // Compound Japanese amounts are sums, not one number times its last unit.
    if (ownScale && !/^[億万千]$/.test(ownScale)) return NaN;
    const parts = [...`${raw}${ownScale || ""}`.matchAll(new RegExp(`(${number})\\s*([億万千])?`, "g"))];
    let total = 0, previousUnit = Infinity;
    for (const [index, part] of parts.entries()) {
      const factor = units[part[2]] || 1;
      const value = Number(part[1].replaceAll(",", ""));
      if (factor >= previousUnit || (index < parts.length - 1 && !Number.isInteger(value))) return NaN;
      if (index > 0 && value * factor >= previousUnit) return NaN;
      total += value * factor;
      previousUnit = factor;
    }
    return total;
  }

  function currencyCode(token, country, text) {
    if (!token) return null;
    const key = token.toUpperCase();
    if (names[key]) return { code: key, inferred: false };
    const symbols = { "US$": "USD", "U.S.$": "USD", "A$": "AUD", "C$": "CAD", "HK$": "HKD", "S$": "SGD", "NT$": "TWD", "RMB": "CNY", "₹": "INR", "€": "EUR", "£": "GBP", "₩": "KRW" };
    if (symbols[key]) return { code: symbols[key], inferred: false };
    const labels = {
      米ドル: "USD", 米国ドル: "USD", 人民元: "CNY", 中国元: "CNY", 元: "CNY",
      インドルピー: "INR", ユーロ: "EUR", 英ポンド: "GBP", ポンド: "GBP",
      韓国ウォン: "KRW", ウォン: "KRW", 豪ドル: "AUD", 豪州ドル: "AUD", カナダドル: "CAD",
      香港ドル: "HKD", 台湾ドル: "TWD", シンガポールドル: "SGD", スイスフラン: "CHF",
    };
    if (labels[token]) return { code: labels[token], inferred: false };
    if (/^(RS\.?|ルピー)$/.test(key) && country === "in") return { code: "INR", inferred: true };
    if (/^(\$|ドル)$/.test(key) && country === "us" && !/豪|カナダ|香港|台湾|シンガポール|AUD|CAD|HKD|SGD|TWD/i.test(text)) {
      return { code: "USD", inferred: true };
    }
    return null;
  }

  function extractPrices(value, country = "") {
    const text = String(value || "").normalize("NFKC");
    const prices = [];
    const seen = new Set();
    for (const match of text.matchAll(pricePattern)) {
      const g = match.groups;
      const before = text[match.index - 1] || "";
      const after = text[match.index + match[0].length] || "";
      // Do not partially interpret malformed grouping, decimal commas or JPY symbols.
      if (/[\d,.¥￥億万千兆京−-]/.test(before) || /[\d,.]/.test(after)) continue;
      if (/\d\s+$/.test(text.slice(0, match.index))) continue;
      if (/[A-Za-z]/.test(before) || (/[A-Za-z]/.test(after) && (g.scale1 || g.scale2 || g.suffix))) continue;
      const tokens = [g.prefix, g.mid, g.prefix2, g.suffix].filter(Boolean);
      let currencies = tokens.map(t => currencyCode(t, country, text));
      if (!tokens.length && country === "in" && /lakh|lac|crore|ラック|ラク|クロール/i.test(g.scale1 || g.scale2 || "")) {
        currencies = [{ code: "INR", inferred: true }];
      }
      if (!currencies.length || currencies.some(c => !c) || new Set(currencies.map(c => c.code)).size !== 1) continue;
      const amount = quantityValue(g.first, g.scale1, g.scale2);
      const end = g.second ? quantityValue(g.second, g.scale2, g.scale1) : null;
      if (!Number.isFinite(amount) || amount < 0 || (end !== null && (!Number.isFinite(end) || end < amount))) continue;
      const code = currencies[0].code;
      // A European decimal point with three trailing digits can be a thousands separator.
      if (code === "EUR" && [g.first, g.second].some(n => n && /^\d+\.\d{3}$/.test(n))) continue;
      const key = `${code}:${amount}:${end}`;
      if (seen.has(key)) continue;
      seen.add(key);
      prices.push({ raw: match[0].trim(), code, amount, end, inferred: currencies.some(c => c.inferred) });
    }
    return prices;
  }

  function formatYen(value) {
    if (value >= 1e8) return `${(value / 1e8).toLocaleString("ja-JP", { maximumFractionDigits: 2 })}億円`;
    if (value >= 1e4) return `${(value / 1e4).toLocaleString("ja-JP", { maximumFractionDigits: 1 })}万円`;
    return `${Math.round(value).toLocaleString("ja-JP")}円`;
  }

  function renderCurrency(item, snapshot = root.DAILYNEWS_EXCHANGE_RATES, now = new Date()) {
    const prices = extractPrices(`${item.title || ""}。${item.desc || ""}。${item.summary || ""}`, item.country);
    if (!prices.length) return "";
    const age = snapshot?.date ? (now - new Date(`${snapshot.date}T00:00:00+09:00`)) / 86400000 : NaN;
    if (snapshot?.base !== "JPY" || !Number.isFinite(age) || age < -1 || age > 10) {
      return '<p class="currency-unavailable">円換算：有効な為替レートを取得できていません。</p>';
    }
    return prices.map(p => {
      const rate = snapshot.rates?.[p.code];
      if (!Number.isFinite(rate) || rate <= 0) return "";
      const yen = p.amount * rate;
      const result = p.end === null ? formatYen(yen) : `${formatYen(yen)}〜${formatYen(p.end * rate)}`;
      const exact = value => Math.round(value).toLocaleString("ja-JP");
      return `<details class="currency-conversion">
        <summary><span class="currency-label">円換算</span><strong>約${result}</strong><span class="currency-original">${escape(p.raw)}</span></summary>
        <div class="currency-detail"><span>現地金額：${p.amount.toLocaleString("ja-JP")}${p.end === null ? "" : `〜${p.end.toLocaleString("ja-JP")}`} ${p.code}</span>
        <span>1 ${p.code} = ${rate.toLocaleString("ja-JP", { maximumFractionDigits: 4 })}円 ／ ${escape(snapshot.date)} 基準${age > 4 ? "（前回取得分）" : ""}</span>
        <span>換算結果：${exact(yen)}${p.end === null ? "" : `〜${exact(p.end * rate)}`}円${p.inferred ? ` ／ ${names[p.code]}として換算` : ""}</span>
        <span>為替出典：<a href="https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html" target="_blank" rel="noopener">欧州中央銀行（ECB）</a></span>
        <small>掲載時点の為替ではなく、上記基準日のレートによる概算です。現地の金額をそのまま換算し、税・送料等は追加計算していません。</small></div>
      </details>`;
    }).join("");
  }

  function articleUrl(item) {
    try {
      const url = new URL(item.url);
      if (!/^https?:$/.test(url.protocol)) return "";
      // Only verified source excerpts are eligible; never infer a quote from the summary.
      if (item.sourceExcerpt) {
        const encode = text => encodeURIComponent(text).replace(/-/g, "%2D");
        url.hash = `:~:text=${encode(item.sourceExcerpt)}${item.sourceExcerptEnd ? `,${encode(item.sourceExcerptEnd)}` : ""}`;
      }
      return url.href;
    } catch (_) { return ""; }
  }

  root.DailyNewsAnnotations = { extractPrices, formatYen, renderCurrency, articleUrl };
  if (typeof module !== "undefined") module.exports = root.DailyNewsAnnotations;
})(typeof window === "undefined" ? globalThis : window);
