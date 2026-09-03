"use strict";

const SOURCE_COUNTRIES = {
  all: { label: "すべて", icon: "🌐" },
  jp: { label: "日本", icon: "🇯🇵" },
  cn: { label: "中国", icon: "🇨🇳" },
  in: { label: "インド", icon: "🇮🇳" },
  us: { label: "米国", icon: "🇺🇸" },
  eu: { label: "欧州", icon: "🇪🇺" },
  paper: { label: "論文", icon: "📄" },
};

const SOURCE_COUNTRY_CODES = {
  日本: "jp",
  中国: "cn",
  インド: "in",
  米国: "us",
  欧州: "eu",
  論文: "paper",
};

function sourceEscape(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  })[character]);
}

function normalizeSource(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[\s\-_–—・!！()（）.]/g, "");
}

function sourceHost(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch (_) {
    return "";
  }
}

function sourcesMatch(left, right) {
  const a = normalizeSource(left);
  const b = normalizeSource(right);
  return Boolean(a && b && (a === b || a.startsWith(b) || b.startsWith(a)));
}

function buildSourceData() {
  const news = Array.isArray(window.LOADED_NEWS_DATA)
    ? window.LOADED_NEWS_DATA
    : [];
  const configured = Array.isArray(window.DAILYNEWS_CONFIGURED_SOURCES)
    ? window.DAILYNEWS_CONFIGURED_SOURCES
    : [];
  const publishedMap = new Map();

  for (const item of news) {
    const name = String(item.source || "不明").trim() || "不明";
    const country = String(item.country || "all");
    const key = `${country}|${normalizeSource(name)}`;
    const row = publishedMap.get(key) || {
      country,
      name,
      count: 0,
      latest: "",
      url: "",
    };
    row.count += 1;
    if (String(item.date || "") >= row.latest) {
      row.latest = String(item.date || "");
      row.url = String(item.url || "");
    }
    publishedMap.set(key, row);
  }

  const published = [...publishedMap.values()].sort(
    (left, right) => right.latest.localeCompare(left.latest)
      || right.count - left.count
      || left.name.localeCompare(right.name, "ja"),
  );
  const feeds = configured.map((feed) => {
    const country = SOURCE_COUNTRY_CODES[feed.country] || "all";
    const matches = published.filter(
      (item) => item.country === country && sourcesMatch(item.name, feed.name),
    );
    return {
      ...feed,
      country,
      count: matches.reduce((sum, item) => sum + item.count, 0),
      latest: matches.reduce(
        (latest, item) => (item.latest > latest ? item.latest : latest),
        "",
      ),
    };
  });
  return { news, feeds, published };
}

function injectSourceStyles() {
  if (document.getElementById("dailynewsSourceStyles")) return;
  const style = document.createElement("style");
  style.id = "dailynewsSourceStyles";
  style.textContent = `
    .source-list-button{display:inline-flex;min-height:38px;align-items:center;gap:7px;border:1px solid rgba(125,241,194,.27);border-radius:999px;padding:0 12px;background:rgba(125,241,194,.06);color:#dffbef;font-size:11px;font-weight:800;white-space:nowrap;cursor:pointer}.source-list-button:hover{background:rgba(125,241,194,.13)}.source-list-count{display:grid;min-width:19px;height:19px;padding:0 4px;place-items:center;border-radius:999px;background:rgba(125,241,194,.17);color:#7df1c2;font-size:9px}
    .source-list-overlay{position:fixed;inset:0;z-index:10060;display:none;place-items:center;padding:22px;background:rgba(1,5,10,.78);backdrop-filter:blur(7px)}.source-list-overlay.open{display:grid}.source-list-dialog{display:grid;width:min(1120px,100%);max-height:min(88vh,920px);grid-template-rows:auto auto auto minmax(0,1fr);overflow:hidden;border:1px solid rgba(125,241,194,.25);border-radius:22px;background:linear-gradient(145deg,#131e2b,#0b131f);color:#eaf1f8;box-shadow:0 35px 100px rgba(0,0,0,.62)}
    .source-list-head{display:flex;align-items:flex-start;justify-content:space-between;gap:20px;padding:22px 24px 16px}.source-list-kicker{color:#7df1c2;font-size:9px;font-weight:900;letter-spacing:.16em}.source-list-title{margin:4px 0 5px;font-size:24px}.source-list-description{max-width:700px;margin:0;color:#93a3b6;font-size:11px;line-height:1.7}.source-list-close{border:0;background:transparent;color:#aebbc9;font-size:28px;cursor:pointer}
    .source-list-summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:9px;padding:0 24px 16px}.source-list-stat{padding:11px 13px;border:1px solid rgba(255,255,255,.08);border-radius:12px;background:rgba(255,255,255,.025);color:#8192a8;font-size:9px}.source-list-stat strong{display:block;margin-top:2px;color:#eef5fb;font-size:17px}.source-list-stat.accent strong{color:#7df1c2}
    .source-list-tools{display:grid;grid-template-columns:auto minmax(180px,1fr) auto;gap:12px;align-items:center;padding:12px 24px;border-block:1px solid rgba(255,255,255,.075);background:rgba(4,10,18,.34)}.source-list-tabs,.source-list-countries{display:flex;gap:6px;overflow:auto}.source-list-tab,.source-list-country{flex:0 0 auto;border:1px solid rgba(255,255,255,.1);border-radius:999px;padding:7px 11px;background:transparent;color:#9aa9bb;font-size:10px;cursor:pointer}.source-list-tab.active{border-color:transparent;background:linear-gradient(135deg,#7df1c2,#6fa7ff);color:#07111d;font-weight:900}.source-list-country.active{border-color:rgba(125,241,194,.45);background:rgba(125,241,194,.1);color:#e9fff6}.source-list-search{width:220px;border:1px solid rgba(255,255,255,.11);border-radius:10px;padding:8px 11px;background:#09111c;color:#eef5fb;font-size:11px}
    .source-list-content{min-height:0;overflow:auto;padding:0 24px 22px}.source-list-table{width:100%;border-collapse:collapse;font-size:11px}.source-list-table th{position:sticky;top:0;z-index:1;padding:11px 9px;border-bottom:1px solid rgba(255,255,255,.1);background:#101a27;color:#8192a8;text-align:left;font-size:9px;letter-spacing:.05em}.source-list-table td{padding:11px 9px;border-bottom:1px solid rgba(255,255,255,.065);vertical-align:middle}.source-list-source{font-weight:800;color:#edf4fb}.source-list-sub{display:block;margin-top:3px;color:#718197;font-size:9px}.source-list-method{display:inline-flex;border-radius:999px;padding:3px 7px;background:rgba(125,241,194,.1);color:#7df1c2;font-size:9px;font-weight:800}.source-list-method.search{background:rgba(111,167,255,.1);color:#9dc0ff}.source-list-link{display:inline-flex;border:1px solid rgba(111,167,255,.22);border-radius:8px;padding:5px 8px;color:#a9c8ff;text-decoration:none;white-space:nowrap}.source-list-link:hover{background:rgba(111,167,255,.1)}.source-list-none{padding:40px;color:#8192a8;text-align:center}
    @media(max-width:860px){.source-list-overlay{padding:8px}.source-list-dialog{max-height:95vh}.source-list-summary{grid-template-columns:repeat(2,minmax(0,1fr));padding-inline:14px}.source-list-head{padding-inline:14px}.source-list-tools{grid-template-columns:1fr;padding-inline:14px}.source-list-search{width:100%}.source-list-content{padding-inline:14px}.source-list-table thead{display:none}.source-list-table,.source-list-table tbody,.source-list-table tr,.source-list-table td{display:block}.source-list-table tr{position:relative;padding:12px 88px 12px 0;border-bottom:1px solid rgba(255,255,255,.08)}.source-list-table td{padding:2px 0;border:0}.source-list-table td:last-child{position:absolute;top:14px;right:0}.source-list-button{padding-inline:9px}.source-list-button-label{display:none}}
  `;
  document.head.appendChild(style);
}

function initializeSources() {
  if (document.documentElement.classList.contains("github-pages-migration")) return;
  if (document.getElementById("sourceListOverlay")) return;
  const data = buildSourceData();
  injectSourceStyles();

  const accountSlot = document.getElementById("accountHeaderSlot");
  const actionArea = accountSlot?.parentElement
    || document.querySelector(".header-top-actions");
  if (!actionArea) return;

  const trigger = document.createElement("button");
  trigger.id = "sourceListButton";
  trigger.className = "source-list-button";
  trigger.type = "button";
  trigger.title = "情報源一覧を開く";
  trigger.innerHTML = `<span aria-hidden="true">◎</span><span class="source-list-button-label">情報源</span><span class="source-list-count">${data.feeds.length}</span>`;
  actionArea.insertBefore(trigger, accountSlot || null);

  const overlay = document.createElement("div");
  overlay.id = "sourceListOverlay";
  overlay.className = "source-list-overlay";
  overlay.innerHTML = `
    <section class="source-list-dialog" role="dialog" aria-modal="true" aria-labelledby="sourceListTitle">
      <header class="source-list-head"><div><span class="source-list-kicker">SOURCES & COVERAGE</span><h2 class="source-list-title" id="sourceListTitle">情報源一覧</h2><p class="source-list-description">定期収集しているRSSと、デイリーニュースに実際に掲載された媒体を確認できます。収集後に内装関連度の判定、日本語要約、画像確認を行っています。</p></div><button class="source-list-close" type="button" aria-label="閉じる">&times;</button></header>
      <div class="source-list-summary" id="sourceListSummary"></div>
      <div class="source-list-tools"><div class="source-list-tabs"><button class="source-list-tab active" data-source-mode="feeds" type="button">定期収集RSS</button><button class="source-list-tab" data-source-mode="published" type="button">掲載実績</button></div><div class="source-list-countries" id="sourceListCountries"></div><input class="source-list-search" id="sourceListSearch" type="search" placeholder="媒体名・ドメインを検索…"></div>
      <div class="source-list-content" id="sourceListContent"></div>
    </section>`;
  document.body.appendChild(overlay);

  const latest = data.news.reduce(
    (value, item) => (String(item.date || "") > value ? String(item.date) : value),
    "",
  );
  overlay.querySelector("#sourceListSummary").innerHTML = `
    <div class="source-list-stat accent">定期収集RSS<strong>${data.feeds.length}</strong></div>
    <div class="source-list-stat">掲載媒体<strong>${data.published.length}</strong></div>
    <div class="source-list-stat">掲載記事<strong>${data.news.length.toLocaleString()}</strong></div>
    <div class="source-list-stat">最終掲載日<strong>${sourceEscape(latest || "-")}</strong></div>`;
  const countries = overlay.querySelector("#sourceListCountries");
  countries.innerHTML = Object.entries(SOURCE_COUNTRIES)
    .map(([key, value]) => `<button class="source-list-country${key === "all" ? " active" : ""}" data-source-country="${key}" type="button">${value.icon} ${value.label}</button>`)
    .join("");

  const state = { mode: "feeds", country: "all", query: "" };
  function render() {
    const query = normalizeSource(state.query);
    let rows = state.mode === "feeds" ? data.feeds : data.published;
    rows = rows.filter((row) => (
      (state.country === "all" || row.country === state.country)
      && (!query || normalizeSource(`${row.name} ${row.rssUrl || row.url || ""}`).includes(query))
    ));
    const body = rows.map((row) => {
      const meta = SOURCE_COUNTRIES[row.country] || SOURCE_COUNTRIES.all;
      if (state.mode === "feeds") {
        return `<tr><td><span class="source-list-source">${sourceEscape(row.name)}</span><span class="source-list-sub">${sourceEscape(sourceHost(row.rssUrl))}</span></td><td>${meta.icon} ${meta.label}</td><td><span class="source-list-method">RSS</span></td><td>${row.count ? `${row.count.toLocaleString()}件 / 最新 ${sourceEscape(row.latest)}` : "掲載実績なし"}</td><td><a class="source-list-link" href="${sourceEscape(row.rssUrl)}" target="_blank" rel="noopener">RSSを開く ↗</a></td></tr>`;
      }
      const registered = data.feeds.some(
        (feed) => feed.country === row.country && sourcesMatch(feed.name, row.name),
      );
      return `<tr><td><span class="source-list-source">${sourceEscape(row.name)}</span><span class="source-list-sub">${sourceEscape(sourceHost(row.url))}</span></td><td>${meta.icon} ${meta.label}</td><td><span class="source-list-method ${registered ? "" : "search"}">${registered ? "RSS登録" : "検索・その他"}</span></td><td>${row.count.toLocaleString()}件 / 最新 ${sourceEscape(row.latest || "-")}</td><td>${row.url ? `<a class="source-list-link" href="${sourceEscape(row.url)}" target="_blank" rel="noopener">記事例 ↗</a>` : "-"}</td></tr>`;
    }).join("");
    overlay.querySelector("#sourceListContent").innerHTML = body
      ? `<table class="source-list-table"><thead><tr><th>媒体名</th><th>地域</th><th>取得方法</th><th>掲載状況</th><th>リンク</th></tr></thead><tbody>${body}</tbody></table>`
      : '<div class="source-list-none">条件に一致する情報源はありません。</div>';
  }

  function open() {
    overlay.classList.add("open");
    document.body.dataset.sourceListOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
  }
  function close() {
    overlay.classList.remove("open");
    document.body.style.overflow = document.body.dataset.sourceListOverflow || "";
  }

  trigger.addEventListener("click", open);
  overlay.querySelector(".source-list-close").addEventListener("click", close);
  overlay.addEventListener("click", (event) => {
    if (event.target === overlay) close();
  });
  overlay.querySelectorAll("[data-source-mode]").forEach((button) => {
    button.addEventListener("click", () => {
      state.mode = button.dataset.sourceMode;
      overlay.querySelectorAll("[data-source-mode]").forEach((item) => {
        item.classList.toggle("active", item === button);
      });
      render();
    });
  });
  countries.addEventListener("click", (event) => {
    const button = event.target.closest("[data-source-country]");
    if (!button) return;
    state.country = button.dataset.sourceCountry;
    countries.querySelectorAll("[data-source-country]").forEach((item) => {
      item.classList.toggle("active", item === button);
    });
    render();
  });
  overlay.querySelector("#sourceListSearch").addEventListener("input", (event) => {
    state.query = event.target.value;
    render();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && overlay.classList.contains("open")) close();
  });
  render();
  window.dailyNewsSources = { open, close };
}

document.addEventListener("DOMContentLoaded", async () => {
  if (window.__dataScriptsReady) await window.__dataScriptsReady.catch(() => {});
  initializeSources();
});
