"use strict";

const ACTIVITY_API_BASE = "/api";
const ACTIVITY_POLL_MS = 30000;

const activityState = {
  recent: [],
  notifications: [],
  unreadCount: 0,
  recentExpanded: false,
  ready: false,
};

function activityEscape(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

async function activityApi(path, options = {}) {
  const request = {
    credentials: "same-origin",
    cache: "no-store",
    ...options,
    headers: { Accept: "application/json", ...(options.headers || {}) },
  };
  if (request.body && typeof request.body !== "string") {
    request.headers["Content-Type"] = "application/json";
    request.body = JSON.stringify(request.body);
  }
  const response = await fetch(`${ACTIVITY_API_BASE}${path}`, request);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(payload?.error?.message || `HTTP ${response.status}`);
    error.status = response.status;
    throw error;
  }
  return payload;
}

function activityItemIndex() {
  const index = new Map();
  for (const item of window.LOADED_NEWS_DATA || window.NEWS_DATA || []) {
    if (window.interactionsData?.[String(item.id)]?.hidden) continue;
    index.set(String(item.id), {
      id: String(item.id),
      targetId: String(item.id),
      type: "news",
      title: item.title || String(item.id),
      image: String(item.img || "").replace(/&amp;/g, "&"),
    });
  }
  for (const day of window.DAILY_INSIGHTS || []) {
    for (const region of ["jp", "cn", "in", "us", "eu"]) {
      for (const idea of day.ideas?.[region] || []) {
        const value = {
          id: String(idea.id),
          targetId: String(idea.id),
          type: "idea",
          title: idea.title || `企画アイデア ${idea.id}`,
          image: String(idea.img || "").replace(/&amp;/g, "&"),
        };
        index.set(String(idea.id), value);
        index.set(`idea-${idea.id}`, value);
      }
    }
  }
  return index;
}

function relativeTime(value) {
  const normalized = String(value || "").replace(" ", "T");
  const date = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(normalized) ? normalized : `${normalized}Z`);
  if (Number.isNaN(date.getTime())) return "";
  const seconds = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000));
  if (seconds < 60) return "たった今";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}分前`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}時間前`;
  if (seconds < 604800) return `${Math.floor(seconds / 86400)}日前`;
  return date.toLocaleDateString("ja-JP", { timeZone: "Asia/Tokyo" });
}

function injectActivityStyles() {
  if (document.getElementById("dailynewsActivityStyles")) return;
  const style = document.createElement("style");
  style.id = "dailynewsActivityStyles";
  style.textContent = `
    .activity-bell{position:relative;display:grid;width:38px;height:38px;place-items:center;border:1px solid rgba(255,255,255,.12);border-radius:999px;background:rgba(255,255,255,.035);color:#e5edf6;font-size:16px;cursor:pointer;flex:0 0 auto}.activity-bell:hover{border-color:rgba(125,241,194,.38);background:rgba(125,241,194,.09)}
    .activity-count{position:absolute;top:-5px;right:-4px;display:grid;min-width:19px;height:19px;padding:0 4px;place-items:center;border:2px solid #101925;border-radius:10px;background:#ff6473;color:#fff;font-size:9px;font-weight:800}.activity-count[hidden]{display:none}
    .engagement-row{display:grid;grid-template-columns:minmax(0,1.05fr) minmax(0,.95fr);align-items:start;gap:16px;max-width:1400px;margin:0 auto 20px}.engagement-row>.activity-rail,.engagement-row>.ranking-wrapper{min-width:0;margin:0}.engagement-row .activity-grid{grid-template-columns:1fr}.engagement-row .ranking-item{grid-template-columns:minmax(0,1fr)}.engagement-row .ranking-meta{padding-left:40px}.engagement-row .ranking-actions{justify-self:start;padding-left:40px}
    .activity-rail{max-width:1400px;margin:0 auto 20px;padding:17px 18px;border:1px solid rgba(255,255,255,.08);border-radius:18px;background:rgba(16,22,35,.9);box-shadow:0 15px 40px rgba(0,0,0,.25)}
    .activity-head{display:flex;align-items:flex-end;justify-content:space-between;gap:15px;margin-bottom:12px}.activity-kicker{color:#7df1c2;font-size:9px;font-weight:800;letter-spacing:.14em}.activity-head h2{margin:2px 0 0;color:#e9edf5;font-size:17px}.activity-mine{border:1px solid rgba(111,167,255,.28);border-radius:999px;padding:6px 10px;background:rgba(111,167,255,.07);color:#a9c8ff;font-size:10px;cursor:pointer;white-space:nowrap}
    .activity-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));align-items:start;gap:9px}.activity-card{display:grid;grid-template-columns:68px minmax(0,1fr);gap:10px;min-width:0;padding:9px;border:1px solid rgba(255,255,255,.075);border-radius:13px;background:rgba(255,255,255,.025);cursor:pointer;transition:.2s ease}.activity-card:hover{transform:translateY(-2px);border-color:rgba(111,167,255,.38);background:rgba(111,167,255,.055)}
    .activity-card img,.activity-image-fallback{width:68px;height:68px;border-radius:9px;background:linear-gradient(135deg,#223248,#101925)}.activity-card img{object-fit:cover}.activity-image-fallback{display:grid;place-items:center;color:#70839a;font-size:20px}.activity-meta{margin-bottom:2px;color:#8197b0;font-size:9px}.activity-meta strong{color:#7df1c2}.activity-card h3{margin:0;overflow:hidden;color:#eef3f8;font-size:11px;line-height:1.45;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}.activity-card p{margin:4px 0 0;color:#a7b5c6;font-size:9px;line-height:1.55;white-space:normal;overflow-wrap:anywhere}.activity-empty{grid-column:1/-1;padding:12px;color:#8191a7;font-size:11px;text-align:center}.activity-more-row{display:flex;justify-content:center;margin-top:11px}.activity-more{border:1px solid rgba(125,241,194,.25);border-radius:999px;padding:7px 14px;background:rgba(125,241,194,.055);color:#aeeed6;font-size:10px;cursor:pointer}.activity-more:hover{background:rgba(125,241,194,.11)}.activity-more[hidden]{display:none}
    .activity-drawer-bg{position:fixed;inset:0;z-index:10040;visibility:hidden;background:rgba(1,4,9,.54);opacity:0;transition:.25s}.activity-drawer-bg.open{visibility:visible;opacity:1}.activity-drawer{position:fixed;top:0;right:0;z-index:10041;width:min(410px,94vw);height:100vh;padding:19px;overflow:auto;border-left:1px solid rgba(111,167,255,.25);background:#0c1420;color:#e9edf5;box-shadow:-25px 0 70px rgba(0,0,0,.55);transform:translateX(105%);transition:.3s cubic-bezier(.22,.75,.25,1)}.activity-drawer.open{transform:translateX(0)}
    .activity-drawer-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:13px}.activity-drawer h2{margin:0;font-size:18px}.activity-read-all{border:0;background:none;color:#8fb9ff;font-size:10px;cursor:pointer}.activity-notice{position:relative;display:grid;grid-template-columns:32px minmax(0,1fr);gap:10px;width:100%;margin-bottom:8px;padding:12px;border:1px solid rgba(255,255,255,.08);border-radius:12px;background:rgba(255,255,255,.025);color:inherit;text-align:left;cursor:pointer}.activity-notice.unread{border-color:rgba(111,167,255,.2);background:rgba(111,167,255,.065)}.activity-notice.unread::after{position:absolute;top:14px;right:11px;width:6px;height:6px;border-radius:50%;background:#6fa7ff;content:""}.activity-notice-icon{display:grid;width:30px;height:30px;place-items:center;border-radius:9px;background:rgba(111,167,255,.1)}.activity-notice p{margin:0;padding-right:8px;color:#c5d0de;font-size:11px;line-height:1.55}.activity-notice time{display:block;margin-top:4px;color:#718299;font-size:9px}.activity-drawer-note{color:#687b92;font-size:10px;line-height:1.6}.activity-highlight{animation:activityHighlight 2.6s ease}@keyframes activityHighlight{0%,100%{box-shadow:none}20%,70%{box-shadow:0 0 0 4px rgba(125,241,194,.24),0 20px 50px rgba(0,0,0,.3)}}
    .comment-item.reply-comment{margin-left:18px;border-left:2px solid rgba(111,167,255,.35);padding-left:10px}.comment-reply-label{margin-left:6px;padding:1px 5px;border-radius:999px;background:rgba(111,167,255,.12);color:#9fc3ff;font-size:9px}.comment-reply-btn{border:1px solid rgba(255,255,255,.12);border-radius:999px;padding:3px 8px;background:transparent;color:#9fb0c5;font-size:11px;cursor:pointer}.comment-reply-btn:hover{border-color:rgba(111,167,255,.45);color:#b9d3ff}
    @media(max-width:1000px){.engagement-row{grid-template-columns:1fr;margin-inline:10px}.engagement-row>.activity-rail,.engagement-row>.ranking-wrapper{margin:0}}
    @media(max-width:860px){.header-top-actions{grid-template-columns:minmax(0,1fr) auto auto auto!important;column-gap:7px}.activity-grid{grid-template-columns:1fr}.activity-head{align-items:flex-start;flex-direction:column}.activity-rail{margin-inline:10px}.engagement-row .activity-rail{margin-inline:0}}
    @media(max-width:520px){.header-top-actions{grid-template-columns:auto auto minmax(0,1fr)!important}.header-update-status{grid-column:1/-1}.activity-bell{grid-column:1}.source-list-button{grid-column:2}#accountHeaderSlot{grid-column:3;min-width:0}.account-button{max-width:100%;overflow:hidden;text-overflow:ellipsis}}
  `;
  document.head.appendChild(style);
}

function injectActivityUi() {
  if (document.getElementById("activityRail")) return;
  injectActivityStyles();
  const accountSlot = document.getElementById("accountHeaderSlot");
  const actionArea = accountSlot?.parentElement || document.querySelector(".header-top-actions");
  if (actionArea) {
    const bell = document.createElement("button");
    bell.id = "activityBell";
    bell.className = "activity-bell";
    bell.type = "button";
    bell.title = "通知";
    bell.setAttribute("aria-label", "通知を開く");
    bell.innerHTML = '🔔<span class="activity-count" id="activityCount" hidden>0</span>';
    actionArea.insertBefore(bell, accountSlot || null);
    bell.addEventListener("click", () => setActivityDrawer(true));
  }

  const filters = document.querySelector(".filters");
  if (filters) {
    const ranking = document.getElementById("rankingWrapper");
    const engagementRow = document.createElement("div");
    engagementRow.id = "engagementRow";
    engagementRow.className = "engagement-row";
    filters.insertAdjacentElement("afterend", engagementRow);
    const rail = document.createElement("section");
    rail.id = "activityRail";
    rail.className = "activity-rail";
    rail.innerHTML = `
      <div class="activity-head">
        <div><span class="activity-kicker">RECENT ACTIVITY</span><h2>みんなの動き</h2></div>
        <button class="activity-mine" id="activityMine" type="button">参加した記事を見る</button>
      </div>
      <div class="activity-grid" id="activityGrid"><div class="activity-empty">動きを読み込み中...</div></div>
      <div class="activity-more-row"><button class="activity-more" id="activityMore" type="button" hidden>過去の動きを見る</button></div>`;
    engagementRow.appendChild(rail);
    if (ranking) engagementRow.appendChild(ranking);
    rail.querySelector("#activityMine")?.addEventListener("click", () => {
      window.dailyNewsAccount?.openTab?.("participation");
    });
    rail.querySelector("#activityGrid")?.addEventListener("click", (event) => {
      const card = event.target.closest("[data-activity-item]");
      if (card) openActivityTarget(card.dataset.activityItem);
    });
    rail.querySelector("#activityMore")?.addEventListener("click", () => {
      activityState.recentExpanded = !activityState.recentExpanded;
      renderRecentActivity();
    });
  }

  const backdrop = document.createElement("div");
  backdrop.id = "activityDrawerBackdrop";
  backdrop.className = "activity-drawer-bg";
  const drawer = document.createElement("aside");
  drawer.id = "activityDrawer";
  drawer.className = "activity-drawer";
  drawer.setAttribute("aria-label", "通知");
  drawer.innerHTML = `
    <div class="activity-drawer-head"><h2>通知</h2><button class="activity-read-all" id="activityReadAll" type="button">すべて既読にする</button></div>
    <div id="activityNotices"></div>
    <p class="activity-drawer-note">自分への返信・メンション、参加中の記事、コメントへの反応を優先して表示します。</p>`;
  document.body.append(backdrop, drawer);
  backdrop.addEventListener("click", () => setActivityDrawer(false));
  drawer.querySelector("#activityReadAll")?.addEventListener("click", markAllActivityRead);
  drawer.querySelector("#activityNotices")?.addEventListener("click", async (event) => {
    const notice = event.target.closest("[data-notification-id]");
    if (!notice) return;
    await markActivityRead([Number(notice.dataset.notificationId)]);
    openActivityTarget(notice.dataset.itemId);
  });
}

function setActivityDrawer(open) {
  document.getElementById("activityDrawer")?.classList.toggle("open", open);
  document.getElementById("activityDrawerBackdrop")?.classList.toggle("open", open);
}

function activityImage(item) {
  if (!item?.image) return '<span class="activity-image-fallback" aria-hidden="true">📰</span>';
  return `<img src="${activityEscape(item.image)}" alt="" loading="lazy" referrerpolicy="no-referrer">`;
}

function renderRecentActivity() {
  const grid = document.getElementById("activityGrid");
  if (!grid) return;
  const index = activityItemIndex();
  const available = activityState.recent
    .map((entry) => ({ entry, item: index.get(String(entry.itemId)) }))
    .filter(({ item }) => item);
  const rows = activityState.recentExpanded ? available : available.slice(0, 3);
  const more = document.getElementById("activityMore");
  if (more) {
    more.hidden = available.length <= 3;
    more.textContent = activityState.recentExpanded
      ? "最新3件に戻す"
      : `過去の動きを見る（${available.length - 3}件）`;
  }
  if (!rows.length) {
    grid.innerHTML = '<div class="activity-empty">まだコメントの動きはありません。</div>';
    return;
  }
  grid.innerHTML = rows.map(({ entry, item }) => `
    <article class="activity-card" data-activity-item="${activityEscape(entry.itemId)}" tabindex="0">
      ${activityImage(item)}
      <div><div class="activity-meta"><strong>${activityEscape(entry.user)}</strong>${entry.type === "comment_reply" ? "が返信" : "がコメント"}・${activityEscape(relativeTime(entry.createdAt))}</div><h3>${activityEscape(item.title)}</h3><p>${activityEscape(entry.text)}</p></div>
    </article>`).join("");
}

function notificationMessage(notification) {
  const actor = `<strong>${activityEscape(notification.actorName)}</strong>`;
  if (notification.type === "comment_reply") return `${actor}さんがあなたのコメントに返信しました。`;
  if (notification.type === "mention") return `${actor}さんがコメントであなたをメンションしました。`;
  if (notification.type === "comment_like") return `${actor}さんがあなたのコメントにいいねしました。`;
  return `参加中の記事に${actor}さんがコメントしました。`;
}

function renderNotifications() {
  const count = document.getElementById("activityCount");
  if (count) {
    count.hidden = activityState.unreadCount < 1;
    count.textContent = activityState.unreadCount > 99 ? "99+" : String(activityState.unreadCount);
  }
  const list = document.getElementById("activityNotices");
  if (!list) return;
  if (!activityState.notifications.length) {
    list.innerHTML = '<div class="activity-empty">通知はまだありません。</div>';
    return;
  }
  const icons = { comment_reply: "↩", mention: "@", comment_like: "👍", article_comment: "💬" };
  list.innerHTML = activityState.notifications.map((notification) => `
    <button class="activity-notice${notification.read ? "" : " unread"}" type="button" data-notification-id="${notification.id}" data-item-id="${activityEscape(notification.itemId)}">
      <span class="activity-notice-icon">${icons[notification.type] || "●"}</span>
      <span><p>${notificationMessage(notification)}</p><time>${activityEscape(relativeTime(notification.createdAt))}</time></span>
    </button>`).join("");
}

async function loadActivity() {
  if (!window.dailyNewsAccount?.user) return;
  try {
    const [recent, notices] = await Promise.all([
      activityApi("/activity/recent?limit=12"),
      activityApi("/notifications?limit=30"),
    ]);
    activityState.recent = recent.activity || [];
    activityState.notifications = notices.notifications || [];
    activityState.unreadCount = Number(notices.unreadCount || 0);
    renderRecentActivity();
    renderNotifications();
  } catch (error) {
    if (error.status !== 401) console.warn("Activity load failed:", error.message);
  }
}

async function markActivityRead(ids) {
  const result = await activityApi("/notifications/read", {
    method: "PUT",
    body: { ids },
  }).catch(() => null);
  if (!result) return;
  activityState.notifications = result.notifications || [];
  activityState.unreadCount = Number(result.unreadCount || 0);
  renderNotifications();
  window.dailyNewsAccount?.refreshActivity?.().catch(() => {});
}

async function markAllActivityRead() {
  const result = await activityApi("/notifications/read", {
    method: "PUT",
    body: { all: true },
  }).catch(() => null);
  if (!result) return;
  activityState.notifications = result.notifications || [];
  activityState.unreadCount = Number(result.unreadCount || 0);
  renderNotifications();
  window.dailyNewsAccount?.refreshActivity?.().catch(() => {});
}

function openActivityTarget(itemId) {
  setActivityDrawer(false);
  const item = activityItemIndex().get(String(itemId));
  if (item?.type === "idea" && window.showIdeaItem) {
    window.showIdeaItem(item.targetId, true);
  } else if (window.showNewsItem) {
    window.showNewsItem(item?.targetId || itemId, false, true);
  }
  window.setTimeout(() => {
    const card = document.getElementById(`card-${item?.targetId || itemId}`)
      || document.querySelector(`[data-news-id="${CSS.escape(item?.targetId || itemId)}"]`);
    card?.scrollIntoView({ behavior: "smooth", block: "center" });
    card?.classList.add("activity-highlight");
    window.setTimeout(() => card?.classList.remove("activity-highlight"), 2700);
  }, 280);
}

async function initializeActivity() {
  if (document.documentElement.classList.contains("github-pages-migration")) return;
  injectActivityUi();
  if (window.__dataScriptsReady) await window.__dataScriptsReady.catch(() => {});
  activityState.ready = true;
  await loadActivity();
  window.setInterval(loadActivity, ACTIVITY_POLL_MS);
}

window.addEventListener("dailynews:account-changed", () => {
  if (activityState.ready) loadActivity();
});
window.addEventListener("dailynews:activity-updated", () => {
  if (activityState.ready) loadActivity();
});
document.addEventListener("DOMContentLoaded", initializeActivity);
