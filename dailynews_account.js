"use strict";

const ACCOUNT_API_BASE = "/api";
const ACCOUNT_CLIENT_ID_KEY = "dailynews_client_id_v1";
const ACCOUNT_FAVORITES_KEY = "favorites_v1";
const ACCOUNT_FAVORITES_OWNER_KEY = "dailynews_favorites_owner_v1";

const accountState = {
  user: null,
  activity: null,
  mode: "login",
  activityTab: "favorites",
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
    .account-bar { display:flex; justify-content:flex-end; margin:12px 0 0; }
    .account-button { border:1px solid rgba(125,241,194,.38); border-radius:999px; padding:8px 14px; background:rgba(125,241,194,.08); color:#dffbef; font-weight:700; cursor:pointer; }
    .account-button:hover { background:rgba(125,241,194,.16); }
    .account-overlay { position:fixed; inset:0; z-index:10020; display:none; align-items:center; justify-content:center; padding:18px; background:rgba(2,6,12,.78); backdrop-filter:blur(8px); }
    .account-overlay.open { display:flex; }
    .account-dialog { width:min(760px,100%); max-height:min(86vh,840px); overflow:auto; border:1px solid rgba(125,241,194,.28); border-radius:22px; background:linear-gradient(145deg,#151f2c,#0c131f); color:#eef4fb; box-shadow:0 30px 90px rgba(0,0,0,.55); }
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
    .account-error { display:none; margin:0 0 13px; padding:10px 12px; border-radius:10px; background:rgba(255,92,112,.12); color:#ffb5c0; font-size:13px; }
    .account-error.show { display:block; }
    .account-tabs { display:flex; gap:8px; flex-wrap:wrap; margin:0 0 16px; }
    .account-tab { border:1px solid rgba(255,255,255,.13); border-radius:999px; padding:7px 12px; background:transparent; color:#b7c4d4; cursor:pointer; }
    .account-tab.active { border-color:#7df1c2; background:rgba(125,241,194,.12); color:#eafff7; }
    .account-list { display:grid; gap:10px; }
    .account-list-item { width:100%; border:1px solid rgba(255,255,255,.1); border-radius:13px; padding:12px 14px; background:rgba(255,255,255,.035); color:#e8eef7; text-align:left; cursor:pointer; }
    .account-list-title { display:block; font-weight:800; line-height:1.5; }
    .account-list-sub { display:block; margin-top:4px; color:#91a0b5; font-size:12px; line-height:1.5; }
    .account-empty { padding:30px 12px; color:#8291a6; text-align:center; }
    .account-profile { display:grid; grid-template-columns:1fr auto; gap:14px; align-items:end; margin-bottom:18px; }
    .account-email { color:#8ea0b6; font-size:12px; overflow-wrap:anywhere; }
    .account-feedback-status { color:#7df1c2; font-size:12px; }
    .comment-actions { display:flex; align-items:center; gap:8px; margin-top:8px; }
    .comment-like-btn { border:1px solid rgba(255,255,255,.12); border-radius:999px; padding:3px 8px; background:transparent; color:#9fb0c5; font-size:11px; cursor:pointer; }
    .comment-like-btn.liked { border-color:rgba(125,241,194,.45); background:rgba(125,241,194,.12); color:#7df1c2; }
    @media(max-width:640px) { .account-profile { grid-template-columns:1fr; } .account-dialog { max-height:94vh; } }
  `;
  document.head.appendChild(style);
}

function injectAccountUi() {
  accountStyles();
  const header = document.querySelector("header#top") || document.body;
  const bar = document.createElement("div");
  bar.className = "account-bar";
  bar.innerHTML = '<button class="account-button" id="accountOpenButton" type="button">ログイン / 登録</button>';
  header.appendChild(bar);

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
  overlay.querySelector(".account-close").addEventListener("click", closeAccount);
  overlay.addEventListener("click", (event) => {
    if (event.target === overlay) closeAccount();
  });
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
  const isRegister = mode === "register";
  const secureUrl = `https://${location.host}${location.pathname}${location.search}`;
  const securityNote = location.protocol === "https:"
    ? ""
    : `<p class="account-note" style="color:#ffd28a">パスワードを保護するため、可能な端末では <a href="${escapeAccountHtml(secureUrl)}" style="color:#7df1c2">HTTPS版</a> を利用してください。</p>`;
  document.getElementById("accountTitle").textContent = isRegister ? "新規登録" : "ログイン";
  body.innerHTML = `
    <p class="account-note">メールアドレスをログインIDとして使用します。コメントには表示名だけが表示され、メールアドレスは公開されません。ログイン状態はこの端末で180日間維持されます。</p>
    ${securityNote}
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
    renderAccountHome();
  } catch (error) {
    setAccountError(authErrorMessage(error));
  } finally {
    button.disabled = false;
  }
}

function accountItemIndex() {
  const index = new Map();
  for (const item of window.LOADED_NEWS_DATA || window.NEWS_DATA || []) {
    index.set(item.id, { id: item.id, title: item.title, date: item.date, type: "news" });
  }
  for (const day of window.DAILY_INSIGHTS || []) {
    for (const region of ["jp", "cn", "in", "us", "eu"]) {
      for (const idea of day.ideas?.[region] || []) {
        index.set(`idea-${idea.id}`, {
          id: `idea-${idea.id}`,
          title: idea.title,
          date: day.date,
          type: "idea",
        });
      }
    }
  }
  return index;
}

function activityEntries(tab) {
  const activity = accountState.activity || {};
  const index = accountItemIndex();
  if (tab === "comments") {
    return (activity.comments || []).map((comment) => ({
      id: comment.itemId,
      title: index.get(comment.itemId)?.title || comment.itemId,
      sub: comment.text,
    }));
  }
  const ids = tab === "likes" ? activity.likes || [] : activity.favorites || [];
  return ids.map((id) => ({
    id,
    title: index.get(id)?.title || id,
    sub: index.get(id)?.date || "",
  }));
}

function openActivityItem(itemId) {
  closeAccount();
  if (!itemId.startsWith("idea-") && window.showNewsItemFromRef) {
    window.showNewsItemFromRef(itemId);
    return;
  }
  document.getElementById("ideasSection")?.scrollIntoView({ behavior: "smooth" });
}

function renderActivityList() {
  const list = document.getElementById("accountActivityList");
  if (!list) return;
  const entries = activityEntries(accountState.activityTab);
  if (!entries.length) {
    list.innerHTML = '<div class="account-empty">まだ履歴がありません。</div>';
    return;
  }
  list.innerHTML = entries
    .map(
      (entry) => `<button class="account-list-item" type="button" data-item-id="${escapeAccountHtml(entry.id)}"><span class="account-list-title">${escapeAccountHtml(entry.title)}</span><span class="account-list-sub">${escapeAccountHtml(entry.sub)}</span></button>`,
    )
    .join("");
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
      <button class="account-tab" data-tab="likes" type="button">いいねした記事</button>
      <button class="account-tab" data-tab="comments" type="button">自分のコメント</button>
      <button class="account-tab" data-tab="feedback" type="button">ご意見ボックス</button>
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
  else renderActivityList();
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
  window.dispatchEvent(new CustomEvent("dailynews:account-changed", { detail: accountState.user }));
}

async function logoutAccount() {
  await accountApi("/auth/logout", { method: "POST", body: {} }).catch(() => {});
  accountState.user = null;
  accountState.activity = null;
  localStorage.removeItem(ACCOUNT_FAVORITES_OWNER_KEY);
  localStorage.removeItem(ACCOUNT_FAVORITES_KEY);
  Object.keys(localStorage)
    .filter((key) => key.startsWith("liked_"))
    .forEach((key) => localStorage.removeItem(key));
  window.applyServerFavorites?.([]);
  updateAccountButton();
  closeAccount();
  window.dispatchEvent(new CustomEvent("dailynews:account-changed", { detail: null }));
}

function updateAccountButton() {
  const button = document.getElementById("accountOpenButton");
  if (!button) return;
  button.textContent = accountState.user
    ? `${accountState.user.displayName} / マイページ`
    : "ログイン / 登録";
}

function openAccount(mode, message = "") {
  const overlay = document.getElementById("accountOverlay");
  overlay?.classList.add("open");
  document.body.style.overflow = "hidden";
  if (accountState.user) renderAccountHome();
  else renderAuth(mode || accountState.mode, message);
}

function closeAccount() {
  document.getElementById("accountOverlay")?.classList.remove("open");
  document.body.style.overflow = "";
}

async function initializeAccount() {
  if (document.documentElement.classList.contains("github-pages-migration")) return;
  injectAccountUi();
  try {
    const result = await accountApi("/auth/me");
    accountState.user = result.user || null;
    if (accountState.user) await afterAuthentication();
  } catch (error) {
    console.warn("Account initialization failed:", error.message);
  }
  updateAccountButton();
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
