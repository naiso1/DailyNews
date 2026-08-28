"use strict";

const ACCOUNT_API_BASE = "/api";
const ACCOUNT_CLIENT_ID_KEY = "dailynews_client_id_v1";
const ACCOUNT_FAVORITES_KEY = "favorites_v1";
const ACCOUNT_FAVORITES_OWNER_KEY = "dailynews_favorites_owner_v1";

const accountState = {
  user: null,
  activity: null,
  mode: "welcome",
  activityTab: "favorites",
  admin: null,
};

function accountClientId() {
  if (window.getDailyNewsClientId) return window.getDailyNewsClientId();
  let value = localStorage.getItem(ACCOUNT_CLIENT_ID_KEY);
  if (!value) {
    value = crypto.randomUUID().replace(/-/g, "");
    localStorage.setItem(ACCOUNT_CLIENT_ID_KEY, value);
  }
  return value;
}

function localFavoriteIds() {
  try {
    const values = JSON.parse(localStorage.getItem(ACCOUNT_FAVORITES_KEY) || "[]");
    return Array.isArray(values) ? values.filter(Boolean) : [];
  } catch (_) {
    return [];
  }
}

async function accountApi(path, options = {}) {
  const request = {
    credentials: "same-origin",
    cache: "no-store",
    ...options,
    headers: {
      Accept: "application/json",
      ...(options.headers || {}),
    },
  };
  if (request.body && typeof request.body !== "string") {
    request.headers["Content-Type"] = "application/json";
    request.body = JSON.stringify(request.body);
  }
  const response = await fetch(`${ACCOUNT_API_BASE}${path}`, request);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(payload?.error?.message || `HTTP ${response.status}`);
    error.status = response.status;
    error.code = payload?.error?.code;
    throw error;
  }
  return payload;
}

function escapeAccountHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function accountStyles() {
  const style = document.createElement("style");
  style.textContent = `
    .account-bar { display:flex; justify-content:flex-end; margin:0; }
    .account-button { min-height:36px; border:1px solid rgba(125,241,194,.38); border-radius:999px; padding:0 14px; background:rgba(125,241,194,.08); color:#dffbef; font-weight:700; white-space:nowrap; cursor:pointer; }
    .account-button:hover { background:rgba(125,241,194,.16); }
    .account-overlay { position:fixed; inset:0; z-index:10020; display:none; align-items:center; justify-content:center; padding:18px; background:rgba(2,6,12,.78); backdrop-filter:blur(8px); }
    .account-overlay.open { display:flex; }
    .account-overlay.auth-required { background:#07111b; backdrop-filter:none; }
    .account-overlay.auth-required .account-close { display:none; }
    .account-dialog { width:min(980px,100%); max-height:min(88vh,900px); overflow:auto; border:1px solid rgba(125,241,194,.28); border-radius:22px; background:linear-gradient(145deg,#151f2c,#0c131f); color:#eef4fb; box-shadow:0 30px 90px rgba(0,0,0,.55); }
    .account-head { position:sticky; top:0; z-index:2; display:flex; align-items:center; justify-content:space-between; gap:12px; padding:18px 20px; border-bottom:1px solid rgba(255,255,255,.1); background:rgba(15,23,35,.96); }
    .account-head h2 { margin:0; font-size:20px; }
    .account-close { border:0; background:transparent; color:#c5cfdb; font-size:25px; cursor:pointer; }
    .account-body { padding:20px; }
    .account-note { margin:0 0 16px; color:#aab7c8; font-size:13px; line-height:1.7; }
    .account-form { display:grid; gap:13px; }
    .account-field { display:grid; gap:6px; color:#cbd5e1; font-size:13px; font-weight:700; }
    .account-field input,.account-field select,.account-field textarea { width:100%; border:1px solid rgba(255,255,255,.14); border-radius:11px; padding:11px 12px; background:#0a111c; color:#f8fafc; font:inherit; }
    .account-field textarea { min-height:130px; resize:vertical; }
    .account-primary { border:0; border-radius:12px; min-height:44px; padding:0 18px; background:linear-gradient(135deg,#7df1c2,#6fa7ff); color:#07111d; font-weight:900; cursor:pointer; }
    .account-secondary { border:1px solid rgba(255,255,255,.16); border-radius:11px; min-height:40px; padding:0 14px; background:rgba(255,255,255,.04); color:#e5edf7; font-weight:700; cursor:pointer; }
    .account-switch { margin-top:14px; color:#9fb1c7; font-size:13px; text-align:center; }
    .account-link { border:0; padding:0; background:none; color:#7df1c2; text-decoration:underline; cursor:pointer; }
    .account-welcome { display:grid; grid-template-columns:minmax(0,1.35fr) minmax(280px,.65fr); gap:24px; align-items:stretch; }
    .account-welcome-copy { padding:8px 4px; }
    .account-welcome-eyebrow { display:inline-flex; align-items:center; gap:7px; margin-bottom:13px; color:#7df1c2; font-size:12px; font-weight:900; letter-spacing:.08em; }
    .account-welcome-title { margin:0 0 14px; color:#f3f8fd; font-size:clamp(23px,3vw,34px); line-height:1.35; }
    .account-welcome-lead { margin:0; color:#b7c6d8; font-size:14px; line-height:1.9; }
    .account-welcome-points { display:grid; gap:10px; margin:21px 0 0; padding:0; list-style:none; }
    .account-welcome-points li { display:flex; gap:10px; align-items:flex-start; color:#d8e4ef; font-size:13px; line-height:1.65; }
    .account-welcome-points li::before { content:"✓"; display:grid; flex:0 0 22px; height:22px; place-items:center; border-radius:50%; background:rgba(125,241,194,.12); color:#7df1c2; font-weight:900; }
    .account-welcome-actions { display:grid; gap:12px; align-content:center; padding:20px; border:1px solid rgba(125,241,194,.18); border-radius:17px; background:rgba(6,13,23,.54); }
    .account-welcome-action { display:grid; gap:8px; padding:15px; border:1px solid rgba(255,255,255,.09); border-radius:14px; background:rgba(255,255,255,.025); }
    .account-welcome-action strong { color:#eef6fd; font-size:14px; }
    .account-welcome-action span { color:#8fa1b6; font-size:11px; line-height:1.55; }
    .account-welcome-actions .account-primary,.account-welcome-actions .account-secondary { width:100%; }
    .account-privacy-note { margin:3px 0 0; color:#74869c; font-size:10px; line-height:1.6; text-align:center; }
    .account-error { display:none; margin:0 0 13px; padding:10px 12px; border-radius:10px; background:rgba(255,92,112,.12); color:#ffb5c0; font-size:13px; }
    .account-error.show { display:block; }
    .account-tabs { display:flex; gap:8px; flex-wrap:wrap; margin:0 0 16px; }
    .account-tab { border:1px solid rgba(255,255,255,.13); border-radius:999px; padding:7px 12px; background:transparent; color:#b7c4d4; cursor:pointer; }
    .account-tab.active { border-color:#7df1c2; background:rgba(125,241,194,.12); color:#eafff7; }
    .account-list { display:grid; gap:14px; }
    .account-list-item { width:100%; border:1px solid rgba(255,255,255,.1); border-radius:13px; padding:12px 14px; background:rgba(255,255,255,.035); color:#e8eef7; text-align:left; cursor:pointer; }
    .account-list-title { display:block; font-weight:800; line-height:1.5; }
    .account-list-sub { display:block; margin-top:4px; color:#91a0b5; font-size:12px; line-height:1.5; }
    .account-section-title { display:flex; align-items:center; gap:8px; margin:10px 0 0; color:#dce9f7; font-size:14px; }
    .account-section-count { padding:2px 7px; border-radius:999px; background:rgba(125,241,194,.12); color:#7df1c2; font-size:11px; }
    .account-card-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; }
    .account-activity-card { display:grid; grid-template-columns:128px minmax(0,1fr); min-height:110px; overflow:hidden; border:1px solid rgba(255,255,255,.1); border-radius:15px; background:rgba(255,255,255,.035); color:#e8eef7; text-align:left; cursor:pointer; }
    .account-activity-card:hover { border-color:rgba(125,241,194,.42); transform:translateY(-1px); }
    .account-card-image { width:128px; height:100%; min-height:110px; object-fit:cover; background:linear-gradient(135deg,#223248,#101925); }
    .account-card-image-fallback { display:grid; width:128px; min-height:110px; place-items:center; background:linear-gradient(135deg,#223248,#101925); color:#70839a; font-size:23px; }
    .account-card-copy { min-width:0; padding:12px; }
    .account-card-meta { display:flex; flex-wrap:wrap; gap:6px; align-items:center; margin-bottom:6px; color:#8fa1b7; font-size:10px; }
    .account-card-kind { padding:2px 6px; border-radius:999px; background:rgba(111,167,255,.14); color:#a8c9ff; font-weight:800; }
    .account-card-kind.idea { background:rgba(255,174,87,.14); color:#ffd19d; }
    .account-card-title { display:-webkit-box; overflow:hidden; color:#f2f7fc; font-size:13px; font-weight:800; line-height:1.45; -webkit-box-orient:vertical; -webkit-line-clamp:2; }
    .account-card-desc { display:-webkit-box; overflow:hidden; margin-top:5px; color:#93a2b5; font-size:11px; line-height:1.5; -webkit-box-orient:vertical; -webkit-line-clamp:2; }
    .account-card-comment { margin-top:7px; padding:6px 8px; border-left:2px solid #7df1c2; background:rgba(125,241,194,.06); color:#bed0df; font-size:11px; line-height:1.45; }
    .account-empty { padding:30px 12px; color:#8291a6; text-align:center; }
    .account-profile { display:grid; grid-template-columns:1fr auto; gap:14px; align-items:end; margin-bottom:18px; }
    .account-email { color:#8ea0b6; font-size:12px; overflow-wrap:anywhere; }
    .account-feedback-status { color:#7df1c2; font-size:12px; }
    .admin-kpis { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:10px; margin-bottom:18px; }
    .admin-kpi { padding:13px; border:1px solid rgba(255,255,255,.09); border-radius:13px; background:rgba(255,255,255,.03); color:#91a2b7; font-size:11px; }
    .admin-kpi strong { display:block; margin-top:3px; color:#7df1c2; font-size:22px; }
    .admin-table-wrap { overflow:auto; border:1px solid rgba(255,255,255,.09); border-radius:13px; }
    .admin-table { width:100%; min-width:760px; border-collapse:collapse; font-size:11px; }
    .admin-table th,.admin-table td { padding:10px; border-bottom:1px solid rgba(255,255,255,.07); text-align:left; vertical-align:top; }
    .admin-table th { color:#91a2b7; font-weight:700; }
    .admin-table td { color:#dce6f1; }
    .comment-actions { display:flex; align-items:center; gap:8px; margin-top:8px; }
    .comment-like-btn { border:1px solid rgba(255,255,255,.12); border-radius:999px; padding:3px 8px; background:transparent; color:#9fb0c5; font-size:11px; cursor:pointer; }
    .comment-like-btn.liked { border-color:rgba(125,241,194,.45); background:rgba(125,241,194,.12); color:#7df1c2; }
    @media(max-width:720px) { .account-profile { grid-template-columns:1fr; } .account-dialog { max-height:94vh; } .account-card-grid { grid-template-columns:1fr; } .account-activity-card { grid-template-columns:96px minmax(0,1fr); } .account-card-image,.account-card-image-fallback { width:96px; } .admin-kpis { grid-template-columns:repeat(2,minmax(0,1fr)); } .account-welcome { grid-template-columns:1fr; gap:14px; } .account-welcome-actions { padding:14px; } }
  `;
  document.head.appendChild(style);
}

function injectAccountUi() {
  accountStyles();
  const header = document.querySelector("header#top") || document.body;
  const slot = document.getElementById("accountHeaderSlot") || header;
  const bar = document.createElement("div");
  bar.className = "account-bar";
  bar.innerHTML = '<button class="account-button" id="accountOpenButton" type="button">ログイン / 登録</button>';
  slot.appendChild(bar);

  const overlay = document.createElement("div");
  overlay.id = "accountOverlay";
  overlay.className = "account-overlay";
  overlay.innerHTML = `
    <section class="account-dialog" role="dialog" aria-modal="true" aria-labelledby="accountTitle">
      <div class="account-head"><h2 id="accountTitle">アカウント</h2><button class="account-close" type="button" aria-label="閉じる">&times;</button></div>
      <div class="account-body" id="accountBody"></div>
    </section>`;
  document.body.appendChild(overlay);

  bar.querySelector("button").addEventListener("click", () => openAccount());
  overlay.querySelector(".account-close").addEventListener("click", () => {
    if (accountState.user) closeAccount();
  });
  overlay.addEventListener("click", (event) => {
    if (event.target === overlay && accountState.user) closeAccount();
  });
}

function updateRegistrationPrompt() {
  const overlay = document.getElementById("accountOverlay");
  if (!overlay) return;
  const required = !accountState.user;
  overlay.classList.toggle("auth-required", required);
  if (required) {
    overlay.classList.add("open");
    document.body.style.overflow = "hidden";
    renderAuth("welcome");
  } else if (overlay.classList.contains("open")) {
    overlay.classList.remove("open");
    document.body.style.overflow = "";
  }
}

function setAccountError(message) {
  const element = document.getElementById("accountError");
  if (!element) return;
  element.textContent = message;
  element.classList.toggle("show", Boolean(message));
}

function authErrorMessage(error) {
  if (error.code === "email_in_use") return "このメールアドレスは登録済みです。ログインしてください。";
  if (error.code === "invalid_credentials") return "メールアドレスまたはパスワードが違います。";
  if (error.code === "too_many_attempts") return "試行回数が多すぎます。10分ほど待ってからお試しください。";
  if (error.code === "invalid_registration") return "入力内容を確認してください。パスワードは8文字以上です。";
  return "処理に失敗しました。通信状態を確認して、もう一度お試しください。";
}

function renderAuth(mode = accountState.mode, message = "") {
  accountState.mode = mode;
  const body = document.getElementById("accountBody");
  if (mode === "welcome") {
    document.getElementById("accountTitle").textContent = "デイリーニュースをご利用の方へ";
    body.innerHTML = `
      <div class="account-welcome">
        <section class="account-welcome-copy">
          <div class="account-welcome-eyebrow">TG社員向けサービス</div>
          <h3 class="account-welcome-title">より良いサービスづくりのため、<br>ログイン方式に変更しました</h3>
          <p class="account-welcome-lead">サービス向上と利用状況の把握に活用し、ニュース・考察・企画アイデアをより役立つ内容へ改善していきます。TG社員であれば、どなたでも登録してご利用いただけます。</p>
          <ul class="account-welcome-points">
            <li>登録は、表示名・メールアドレス・パスワードの入力だけで完了します。</li>
            <li>お気に入り・いいね・コメントを、端末が変わっても確認できます。</li>
            <li>ログイン状態はこの端末で維持されるため、通常は次回から入力不要です。</li>
          </ul>
        </section>
        <aside class="account-welcome-actions">
          <div class="account-welcome-action">
            <strong>まだ登録していない方</strong>
            <span>簡単なユーザー登録をお願いします。</span>
            <button class="account-primary" id="accountStartRegister" type="button">ユーザー登録へ</button>
          </div>
          <div class="account-welcome-action">
            <strong>すでに登録済みの方</strong>
            <span>登録したメールアドレスとパスワードでお進みください。</span>
            <button class="account-secondary" id="accountStartLogin" type="button">ログインへ</button>
          </div>
          <p class="account-privacy-note">メールアドレスはログインIDとして使用し、コメント欄などには公開されません。</p>
        </aside>
      </div>`;
    body.querySelector("#accountStartRegister").addEventListener("click", () => renderAuth("register"));
    body.querySelector("#accountStartLogin").addEventListener("click", () => renderAuth("login"));
    return;
  }
  const isRegister = mode === "register";
  document.getElementById("accountTitle").textContent = isRegister ? "新規登録" : "ログイン";
  body.innerHTML = `
    <p class="account-note">${isRegister ? "TG社員であれば、どなたでも登録できます。" : "登録済みの方は、登録した情報を入力してください。"} メールアドレスは公開されません。ログイン状態はこの端末で180日間維持されます。パスワードは必ずこのサービス専用のものを設定してください。</p>
    <div class="account-error${message ? " show" : ""}" id="accountError">${escapeAccountHtml(message)}</div>
    <form class="account-form" id="accountAuthForm">
      ${isRegister ? '<label class="account-field">表示名<input name="displayName" maxlength="40" autocomplete="name" required placeholder="コメントに表示する名前"></label>' : ""}
      <label class="account-field">メールアドレス<input name="email" type="email" maxlength="254" autocomplete="email" required placeholder="name@example.com"></label>
      <label class="account-field">パスワード<input name="password" type="password" minlength="8" maxlength="128" autocomplete="${isRegister ? "new-password" : "current-password"}" required></label>
      <button class="account-primary" type="submit">${isRegister ? "登録して始める" : "ログイン"}</button>
    </form>
    <div class="account-switch">${isRegister ? "登録済みですか？" : "初めて利用しますか？"} <button class="account-link" id="accountModeSwitch" type="button">${isRegister ? "ログイン" : "新規登録"}</button></div>`;
  body.querySelector("#accountModeSwitch").addEventListener("click", () => {
    renderAuth(isRegister ? "login" : "register");
  });
  body.querySelector("#accountAuthForm").addEventListener("submit", submitAuth);
}

async function submitAuth(event) {
  event.preventDefault();
  setAccountError("");
  const form = event.currentTarget;
  const button = form.querySelector("button[type=submit]");
  button.disabled = true;
  const values = new FormData(form);
  const body = {
    email: values.get("email"),
    password: values.get("password"),
    displayName: values.get("displayName"),
    clientId: accountClientId(),
    favorites: [],
  };
  try {
    const result = await accountApi(
      accountState.mode === "register" ? "/auth/register" : "/auth/login",
      { method: "POST", body },
    );
    accountState.user = result.user;
    await afterAuthentication();
    location.reload();
  } catch (error) {
    setAccountError(authErrorMessage(error));
  } finally {
    button.disabled = false;
  }
}

function accountItemIndex() {
  const index = new Map();
  const countryNames = { jp: "日本", cn: "中国", in: "インド", us: "米国", eu: "欧州", paper: "論文" };
  for (const item of window.LOADED_NEWS_DATA || window.NEWS_DATA || []) {
    index.set(String(item.id), {
      id: String(item.id),
      targetId: String(item.id),
      title: item.title,
      date: item.date,
      type: "news",
      image: item.img || "",
      description: item.desc || item.summary || "",
      country: countryNames[item.country] || item.country || "",
    });
  }
  for (const day of window.DAILY_INSIGHTS || []) {
    for (const region of ["jp", "cn", "in", "us", "eu"]) {
      for (const idea of day.ideas?.[region] || []) {
        const value = {
          id: `idea-${idea.id}`,
          targetId: String(idea.id),
          title: idea.title,
          date: day.date,
          type: "idea",
          image: idea.img || "",
          description: idea.desc || "",
          country: countryNames[region],
        };
        // Favorites historically use idea-123, while likes/comments use 123.
        index.set(`idea-${idea.id}`, value);
        index.set(String(idea.id), value);
      }
    }
  }
  return index;
}

function activityEntries(tab) {
  const activity = accountState.activity || {};
  const index = accountItemIndex();
  if (tab === "comments") {
    return (activity.comments || []).map((comment) => {
      const item = index.get(String(comment.itemId));
      return {
        ...(item || { id: String(comment.itemId), targetId: String(comment.itemId), type: "news" }),
        activityId: String(comment.itemId),
        title: item?.title || comment.itemId,
        comment: comment.text,
        activityDate: comment.createdAt,
      };
    });
  }
  const ids = tab === "likes" ? activity.likes || [] : activity.favorites || [];
  return ids.map((id) => {
    const item = index.get(String(id));
    return {
      ...(item || { id: String(id), targetId: String(id), type: "news" }),
      activityId: String(id),
      title: item?.title || id,
    };
  });
}

function openActivityItem(itemId) {
  const item = accountItemIndex().get(String(itemId));
  closeAccount();
  if (item?.type === "idea" && window.showIdeaItem) {
    window.showIdeaItem(item.targetId, true);
    return;
  }
  if (window.showNewsItem) window.showNewsItem(item?.targetId || itemId, false, true);
}

function activityCard(entry) {
  const image = entry.image
    ? `<img class="account-card-image" src="${escapeAccountHtml(entry.image)}" alt="" loading="lazy" referrerpolicy="no-referrer">`
    : `<span class="account-card-image-fallback" aria-hidden="true">${entry.type === "idea" ? "💡" : "📰"}</span>`;
  const comment = entry.comment
    ? `<div class="account-card-comment">${escapeAccountHtml(entry.comment)}</div>`
    : "";
  return `<button class="account-activity-card" type="button" data-item-id="${escapeAccountHtml(entry.activityId || entry.id)}">
    ${image}
    <span class="account-card-copy">
      <span class="account-card-meta"><span class="account-card-kind ${entry.type === "idea" ? "idea" : ""}">${entry.type === "idea" ? "企画アイデア" : "ニュース"}</span><span>${escapeAccountHtml(entry.country || "")}</span><span>${escapeAccountHtml(entry.date || entry.activityDate || "")}</span></span>
      <span class="account-card-title">${escapeAccountHtml(entry.title)}</span>
      <span class="account-card-desc">${escapeAccountHtml(entry.description || "")}</span>
      ${comment}
    </span>
  </button>`;
}

function renderActivityList() {
  const list = document.getElementById("accountActivityList");
  if (!list) return;
  const entries = activityEntries(accountState.activityTab);
  if (!entries.length) {
    list.innerHTML = '<div class="account-empty">まだ履歴がありません。</div>';
    return;
  }
  const ideas = entries.filter((entry) => entry.type === "idea");
  const news = entries.filter((entry) => entry.type !== "idea");
  const section = (title, values) => values.length
    ? `<div class="account-section-title">${title}<span class="account-section-count">${values.length}</span></div><div class="account-card-grid">${values.map(activityCard).join("")}</div>`
    : "";
  list.innerHTML = section("企画アイデア", ideas) + section("ニュース", news);
  list.querySelectorAll("[data-item-id]").forEach((button) => {
    button.addEventListener("click", () => openActivityItem(button.dataset.itemId));
  });
}

function renderAccountHome() {
  const body = document.getElementById("accountBody");
  const user = accountState.user;
  document.getElementById("accountTitle").textContent = "マイページ";
  body.innerHTML = `
    <div class="account-profile">
      <div><strong>${escapeAccountHtml(user.displayName)}</strong><div class="account-email">${escapeAccountHtml(user.email)}</div></div>
      <button class="account-secondary" id="accountLogout" type="button">ログアウト</button>
    </div>
    <form class="account-form" id="accountProfileForm" style="margin-bottom:20px">
      <label class="account-field">コメント表示名<input name="displayName" maxlength="40" value="${escapeAccountHtml(user.displayName)}" required></label>
      <button class="account-secondary" type="submit">表示名を更新</button>
    </form>
    <div class="account-tabs">
      <button class="account-tab" data-tab="favorites" type="button">お気に入り</button>
      <button class="account-tab" data-tab="likes" type="button">いいね</button>
      <button class="account-tab" data-tab="comments" type="button">自分のコメント</button>
      <button class="account-tab" data-tab="feedback" type="button">ご意見ボックス</button>
      ${user.isAdmin ? '<button class="account-tab" data-tab="admin" type="button">管理</button>' : ""}
    </div>
    <div id="accountActivityList" class="account-list"></div>`;
  body.querySelector("#accountLogout").addEventListener("click", logoutAccount);
  body.querySelector("#accountProfileForm").addEventListener("submit", updateProfile);
  body.querySelectorAll("[data-tab]").forEach((button) => {
    button.addEventListener("click", () => selectAccountTab(button.dataset.tab));
  });
  selectAccountTab(accountState.activityTab);
}

function selectAccountTab(tab) {
  accountState.activityTab = tab;
  document.querySelectorAll(".account-tab").forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === tab);
  });
  if (tab === "feedback") renderFeedbackForm();
  else if (tab === "admin") renderAdminPanel();
  else renderActivityList();
}

async function renderAdminPanel() {
  const list = document.getElementById("accountActivityList");
  if (!list || !accountState.user?.isAdmin) return;
  list.innerHTML = '<div class="account-empty">登録状況を読み込み中...</div>';
  try {
    accountState.admin = await accountApi("/admin/overview");
  } catch (error) {
    list.innerHTML = `<div class="account-error show">管理情報を取得できませんでした。${escapeAccountHtml(error.message)}</div>`;
    return;
  }
  const { totals = {}, users = [], feedback = [] } = accountState.admin;
  const kpis = [
    ["登録ユーザー", totals.users],
    ["利用履歴あり", totals.activeUsers],
    ["お気に入り", totals.favorites],
    ["いいね", totals.likes],
    ["コメント", totals.comments],
    ["ご意見", totals.feedback],
  ];
  list.innerHTML = `
    <div class="admin-kpis">${kpis.map(([label, value]) => `<div class="admin-kpi">${label}<strong>${Number(value || 0).toLocaleString()}</strong></div>`).join("")}</div>
    <h3 class="account-section-title">ユーザー登録状況</h3>
    <div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>ユーザー</th><th>登録日</th><th>最終利用</th><th>活動</th></tr></thead><tbody>
      ${users.map((user) => `<tr><td><strong>${escapeAccountHtml(user.displayName)}</strong>${user.isAdmin ? ' <span class="account-card-kind">管理者</span>' : ""}<br><span class="account-email">${escapeAccountHtml(user.email)}</span></td><td>${escapeAccountHtml(user.createdAt || "-")}</td><td>${escapeAccountHtml(user.lastSeenAt || "-")}</td><td>★ ${user.favorites} / 👍 ${user.likes} / 💬 ${user.comments} / 意見 ${user.feedback}</td></tr>`).join("")}
    </tbody></table></div>
    <h3 class="account-section-title">最近のご意見 <span class="account-section-count">${feedback.length}</span></h3>
    <div class="account-list">${feedback.length ? feedback.map((item) => `<div class="account-list-item" style="cursor:default"><span class="account-list-title">${escapeAccountHtml(item.message)}</span><span class="account-list-sub">${escapeAccountHtml(item.displayName)} / ${escapeAccountHtml(item.email)} / ${escapeAccountHtml(item.createdAt)} / ${escapeAccountHtml(item.status)}</span></div>`).join("") : '<div class="account-empty">ご意見はまだありません。</div>'}</div>`;
}

function renderFeedbackForm() {
  const list = document.getElementById("accountActivityList");
  const previous = accountState.activity?.feedback || [];
  list.innerHTML = `
    <form class="account-form" id="accountFeedbackForm">
      <label class="account-field">種類<select name="category"><option value="improvement">改善要望</option><option value="bug">不具合</option><option value="article">ニュース・画像の誤り</option><option value="idea">アイデア提案</option><option value="other">その他</option></select></label>
      <label class="account-field">内容<textarea name="message" maxlength="2000" required placeholder="ご意見を入力してください"></textarea></label>
      <button class="account-primary" type="submit">送信する</button>
      <div class="account-feedback-status" id="accountFeedbackStatus"></div>
    </form>
    ${previous.length ? `<div style="margin-top:22px"><strong>送信履歴</strong><div class="account-list" style="margin-top:10px">${previous.map((item) => `<div class="account-list-item" style="cursor:default"><span class="account-list-title">${escapeAccountHtml(item.message)}</span><span class="account-list-sub">${escapeAccountHtml(item.createdAt)} / ${escapeAccountHtml(item.status)}</span></div>`).join("")}</div></div>` : ""}`;
  list.querySelector("#accountFeedbackForm").addEventListener("submit", submitFeedback);
}

async function submitFeedback(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const values = new FormData(form);
  const status = form.querySelector("#accountFeedbackStatus");
  try {
    await accountApi("/feedback", {
      method: "POST",
      body: {
        category: values.get("category"),
        message: values.get("message"),
        pageUrl: location.href,
      },
    });
    form.reset();
    status.textContent = "送信しました。ありがとうございます。";
    await refreshActivity();
  } catch (_) {
    status.textContent = "送信できませんでした。時間をおいて再度お試しください。";
  }
}

async function updateProfile(event) {
  event.preventDefault();
  const displayName = new FormData(event.currentTarget).get("displayName");
  try {
    const result = await accountApi("/auth/profile", {
      method: "PUT",
      body: { displayName },
    });
    accountState.user = result.user;
    updateAccountButton();
    renderAccountHome();
  } catch (_) {
    alert("表示名を更新できませんでした。");
  }
}

async function refreshActivity() {
  if (!accountState.user) return;
  accountState.activity = await accountApi("/me/activity");
  window.applyServerFavorites?.(accountState.activity.favorites || []);
  localStorage.setItem(ACCOUNT_FAVORITES_OWNER_KEY, String(accountState.user.id));
}

async function afterAuthentication() {
  const favoriteOwner = localStorage.getItem(ACCOUNT_FAVORITES_OWNER_KEY);
  const favoritesToClaim = favoriteOwner ? [] : localFavoriteIds();
  await accountApi("/auth/claim", {
    method: "POST",
    body: { clientId: accountClientId(), favorites: favoritesToClaim },
  });
  await refreshActivity();
  updateAccountButton();
  updateRegistrationPrompt();
  window.dispatchEvent(new CustomEvent("dailynews:account-changed", { detail: accountState.user }));
}

async function logoutAccount() {
  await accountApi("/auth/logout", { method: "POST", body: {} }).catch(() => {});
  accountState.user = null;
  accountState.activity = null;
  accountState.admin = null;
  localStorage.removeItem(ACCOUNT_FAVORITES_OWNER_KEY);
  localStorage.removeItem(ACCOUNT_FAVORITES_KEY);
  Object.keys(localStorage)
    .filter((key) => key.startsWith("liked_"))
    .forEach((key) => localStorage.removeItem(key));
  window.applyServerFavorites?.([]);
  updateAccountButton();
  updateRegistrationPrompt();
  closeAccount();
  window.dispatchEvent(new CustomEvent("dailynews:account-changed", { detail: null }));
}

function updateAccountButton() {
  const button = document.getElementById("accountOpenButton");
  if (!button) return;
  button.textContent = accountState.user
    ? `${accountState.user.displayName} ▾`
    : "ログイン / 登録";
  button.title = accountState.user ? "マイページ" : "ログイン / 登録";
}

function openAccount(mode, message = "") {
  const overlay = document.getElementById("accountOverlay");
  overlay?.classList.add("open");
  document.body.style.overflow = "hidden";
  if (accountState.user) renderAccountHome();
  else renderAuth(mode || accountState.mode, message);
}

function closeAccount() {
  if (!accountState.user) return;
  document.getElementById("accountOverlay")?.classList.remove("open");
  document.body.style.overflow = "";
}

async function initializeAccount() {
  if (document.documentElement.classList.contains("github-pages-migration")) return;
  injectAccountUi();
  updateRegistrationPrompt();
  try {
    const result = await accountApi("/auth/me");
    accountState.user = result.user || null;
    if (accountState.user) await afterAuthentication();
  } catch (error) {
    console.warn("Account initialization failed:", error.message);
  }
  updateAccountButton();
  updateRegistrationPrompt();
}

window.dailyNewsAccount = {
  get user() {
    return accountState.user;
  },
  open: openAccount,
  openAuth(mode = "login", message = "") {
    openAccount(mode, message || "この操作にはログインが必要です。");
  },
  async setFavorite(itemId, favorite) {
    if (!accountState.user) {
      this.openAuth("login", "お気に入りを端末間で保存するにはログインしてください。登録時に現在のお気に入りを引き継ぎます。");
      return false;
    }
    const result = await accountApi(`/favorites/${encodeURIComponent(itemId)}`, {
      method: favorite ? "PUT" : "DELETE",
    });
    accountState.activity = accountState.activity || {};
    accountState.activity.favorites = result.favorites || [];
    return true;
  },
  async refreshActivity() {
    await refreshActivity();
    return accountState.activity;
  },
};

document.addEventListener("DOMContentLoaded", initializeAccount);
