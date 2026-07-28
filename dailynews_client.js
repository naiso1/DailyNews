"use strict";

const API_BASE = "/api";
const CLIENT_ID_KEY = "dailynews_client_id_v1";
const LOCAL_ACCESS_KEY = "local_access_stats";
const LOCAL_INTERACTIONS_KEY = "local_interactions";
const LOCAL_READS_KEY = "local_article_reads";
const LOCAL_ACCESS_MARK_KEY = "local_access_mark_date_v3";
const JST_OFFSET_MS = 9 * 60 * 60 * 1000;

let accessStatsCache = null;
let localInteractionsCache = null;
let interactionPollTimer = null;

window.interactionsData = {};
window.useLocalInteractions = false;
window.firebaseInteractionsReady = false;

function makeClientId() {
  if (globalThis.crypto?.randomUUID) {
    return globalThis.crypto.randomUUID().replace(/-/g, "");
  }
  const bytes = new Uint8Array(24);
  globalThis.crypto?.getRandomValues?.(bytes);
  return Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("");
}

function getClientId() {
  try {
    let value = localStorage.getItem(CLIENT_ID_KEY);
    if (!value || !/^[A-Za-z0-9_-]{16,100}$/.test(value)) {
      value = makeClientId();
      localStorage.setItem(CLIENT_ID_KEY, value);
    }
    return value;
  } catch (_) {
    if (!window.__dailyNewsClientId) window.__dailyNewsClientId = makeClientId();
    return window.__dailyNewsClientId;
  }
}

async function apiRequest(path, options = {}) {
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
  const response = await fetch(`${API_BASE}${path}`, request);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(
      payload?.error?.message || `API request failed (${response.status})`,
    );
    error.status = response.status;
    error.code = payload?.error?.code;
    throw error;
  }
  return payload;
}

function getJstDateKey(offsetDays = 0) {
  const target = new Date(
    Date.now() + JST_OFFSET_MS + offsetDays * 24 * 60 * 60 * 1000,
  );
  const year = target.getUTCFullYear();
  const month = String(target.getUTCMonth() + 1).padStart(2, "0");
  const day = String(target.getUTCDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function getTodayKey() {
  return getJstDateKey();
}

function getYesterdayKey() {
  return getJstDateKey(-1);
}

function parseDateKeyToUTC(dateKey) {
  if (!dateKey) return null;
  const parts = dateKey.split("-").map(Number);
  if (parts.length !== 3 || !parts[0]) return null;
  return new Date(Date.UTC(parts[0], parts[1] - 1, parts[2]));
}

function setAccessCounterStatus(label, isLocal = false) {
  const element = document.getElementById("accessCounterStatus");
  if (!element) return;
  element.textContent = label;
  element.style.color = isLocal ? "var(--accent-3)" : "var(--accent-2)";
}

function loadLocalAccessStats() {
  try {
    return JSON.parse(localStorage.getItem(LOCAL_ACCESS_KEY)) || {
      total: 0,
      daily: {},
    };
  } catch (_) {
    return { total: 0, daily: {} };
  }
}

function saveLocalAccessStats(value) {
  try {
    localStorage.setItem(LOCAL_ACCESS_KEY, JSON.stringify(value));
  } catch (_) {
    // Local fallback is best effort only.
  }
}

function hasCountedAccessToday() {
  try {
    return localStorage.getItem(LOCAL_ACCESS_MARK_KEY) === getTodayKey();
  } catch (_) {
    return false;
  }
}

function markAccessCountedToday() {
  try {
    localStorage.setItem(LOCAL_ACCESS_MARK_KEY, getTodayKey());
  } catch (_) {
    // Server-side idempotency still prevents duplicate daily visits.
  }
}

function bumpLocalAccessStats() {
  const data = loadLocalAccessStats();
  if (hasCountedAccessToday()) return data;
  const today = getTodayKey();
  data.total = (data.total || 0) + 1;
  data.daily = data.daily || {};
  data.daily[today] = (data.daily[today] || 0) + 1;
  const cutoffKey = getJstDateKey(-30);
  Object.keys(data.daily).forEach((date) => {
    if (date < cutoffKey) delete data.daily[date];
  });
  saveLocalAccessStats(data);
  markAccessCountedToday();
  return data;
}

function renderAccessStats(data) {
  const today = getTodayKey();
  const yesterday = getYesterdayKey();
  const total = document.getElementById("totalVisits");
  const todayElement = document.getElementById("todayVisits");
  const yesterdayElement = document.getElementById("yesterdayVisits");
  if (total) total.textContent = (data.total || 0).toLocaleString();
  if (todayElement) {
    todayElement.textContent = ((data.daily && data.daily[today]) || 0).toLocaleString();
  }
  if (yesterdayElement) {
    yesterdayElement.textContent = ((data.daily && data.daily[yesterday]) || 0).toLocaleString();
  }
  accessStatsCache = data;
  window.accessStatsCache = data;
  renderAccessChart(data);
}

function buildAccessSeries(data) {
  const daily = data?.daily || {};
  const dates = Object.keys(daily)
    .map(parseDateKeyToUTC)
    .filter((date) => date && !Number.isNaN(date.getTime()));
  if (!dates.length) return [];
  const start = new Date(Math.min(...dates.map((date) => date.getTime())));
  const end = new Date(Math.max(...dates.map((date) => date.getTime())));
  const series = [];
  for (
    let date = new Date(start);
    date <= end;
    date.setUTCDate(date.getUTCDate() + 1)
  ) {
    const key = [
      date.getUTCFullYear(),
      String(date.getUTCMonth() + 1).padStart(2, "0"),
      String(date.getUTCDate()).padStart(2, "0"),
    ].join("-");
    series.push({
      key,
      label: `${date.getUTCMonth() + 1}/${date.getUTCDate()}`,
      dow: ["日", "月", "火", "水", "木", "金", "土"][date.getUTCDay()],
      value: daily[key] || 0,
    });
  }
  return series;
}

function renderAccessChart(data) {
  const chart = document.getElementById("accessChart");
  if (!chart) return;
  const series = buildAccessSeries(
    data || accessStatsCache || loadLocalAccessStats(),
  );
  if (!series.length) {
    chart.innerHTML = '<div class="chart-empty">データがありません。</div>';
    return;
  }
  const range = document.getElementById("accessChartRange");
  if (range) {
    range.textContent = `${series[0].key.replace(/-/g, "/")}〜${series.at(-1).key.replace(/-/g, "/")} (${series.length}日)`;
  }
  const max = Math.max(...series.map((item) => item.value), 1);
  chart.innerHTML = series
    .map((item) => {
      const height = Math.max(8, Math.round((item.value / max) * 100));
      return `
        <div class="chart-bar">
          <div class="bar" style="height:${height}%"></div>
          <div class="bar-value">${item.value}</div>
          <div class="bar-label">${item.label}</div>
          <div class="bar-dow">${item.dow}</div>
        </div>`;
    })
    .join("");
}

function loadLocalInteractions() {
  if (localInteractionsCache) return localInteractionsCache;
  try {
    localInteractionsCache =
      JSON.parse(localStorage.getItem(LOCAL_INTERACTIONS_KEY)) || {};
  } catch (_) {
    localInteractionsCache = {};
  }
  return localInteractionsCache;
}

function saveLocalInteractions(data) {
  localInteractionsCache = data;
  try {
    localStorage.setItem(LOCAL_INTERACTIONS_KEY, JSON.stringify(data));
  } catch (_) {
    // Local fallback is best effort only.
  }
}

function getLocalInteractionData(itemId) {
  return loadLocalInteractions()[itemId] || {
    likes: 0,
    comments: [],
    reads: getLocalReadCount(itemId),
  };
}

function setLocalInteractionData(itemId, value) {
  const data = loadLocalInteractions();
  data[itemId] = value;
  saveLocalInteractions(data);
  mergeInteractionData(itemId, value);
}

function loadLocalReads() {
  try {
    return JSON.parse(localStorage.getItem(LOCAL_READS_KEY)) || {};
  } catch (_) {
    return {};
  }
}

function saveLocalReads(data) {
  try {
    localStorage.setItem(LOCAL_READS_KEY, JSON.stringify(data));
  } catch (_) {
    // Local fallback is best effort only.
  }
}

function hasReadToday(itemId, dateKey) {
  const data = loadLocalReads();
  return Boolean(data[itemId] && data[itemId][dateKey]);
}

function markReadToday(itemId, dateKey) {
  const data = loadLocalReads();
  if (!data[itemId]) data[itemId] = {};
  data[itemId][dateKey] = true;
  saveLocalReads(data);
}

function getLocalReadCount(itemId) {
  return Object.keys(loadLocalReads()[itemId] || {}).length;
}
window.getLocalReadCount = getLocalReadCount;

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function mergeInteractionData(itemId, data) {
  const previous = window.interactionsData[itemId] || {};
  const commentItems = Array.isArray(data.commentItems)
    ? data.commentItems
    : Array.isArray(data.comments)
      ? data.comments
      : previous.commentItems || [];
  const commentCount =
    typeof data.comments === "number" ? data.comments : commentItems.length;
  window.interactionsData[itemId] = {
    likes: Number(data.likes || 0),
    comments: Number(commentCount || 0),
    commentItems,
    reads:
      typeof data.reads === "number"
        ? data.reads
        : Number(previous.reads || 0),
    liked: typeof data.liked === "boolean" ? data.liked : previous.liked,
  };
}

function getInteractionRenderData(itemId) {
  const data = window.interactionsData[itemId] || {};
  return {
    likes: data.likes || 0,
    comments: data.commentItems || [],
    reads: data.reads || 0,
  };
}

function refreshInteractionCounts() {
  const interactions = window.interactionsData || {};
  document.querySelectorAll(".card").forEach((card) => {
    if (!card.id?.startsWith("card-")) return;
    const itemId = card.id.slice(5);
    const data = interactions[itemId];
    if (!data) return;
    const likeCount = card.querySelector(
      '.action-btn[onclick*="toggleLike"] .count',
    );
    const commentCount = card.querySelector(".btn-comment .count");
    const readCount = card.querySelector(".read-count");
    if (likeCount) likeCount.textContent = data.likes || 0;
    if (commentCount) commentCount.textContent = data.comments || 0;
    if (readCount) readCount.textContent = `閲覧 ${data.reads || 0}`;
  });
}
window.refreshInteractionCounts = refreshInteractionCounts;

function updateRankings() {
  window.refreshInteractionCounts?.();
  window.scheduleRankingUpdate?.();
}

function enableLocalInteractions() {
  window.useLocalInteractions = true;
  const local = loadLocalInteractions();
  window.interactionsData = {};
  Object.entries(local).forEach(([itemId, value]) => {
    mergeInteractionData(itemId, value);
  });
  updateRankings();
}

async function loadInteractions() {
  try {
    const payload = await apiRequest("/interactions");
    Object.entries(payload.interactions || {}).forEach(([itemId, value]) => {
      mergeInteractionData(itemId, value);
    });
    window.firebaseInteractionsReady = true;
    window.useLocalInteractions = false;
    updateRankings();
    return true;
  } catch (error) {
    console.warn("DailyNews API sync failed:", error.message);
    enableLocalInteractions();
    return false;
  }
}

function startInteractionPolling() {
  if (interactionPollTimer) return;
  interactionPollTimer = setInterval(() => {
    if (!document.hidden) loadInteractions();
  }, 15000);
}

async function initDailyNewsApi() {
  const connected = await loadInteractions();
  if (connected) console.log("DailyNews SQLite API connected");
  startInteractionPolling();
}
window.initDailyNewsApi = initDailyNewsApi;
window.initFirebase = initDailyNewsApi;

async function updateAccessCounter() {
  if (window.__accessCounterInFlight || window.__accessCounterCounted) return;
  window.__accessCounterInFlight = true;
  try {
    const stats = hasCountedAccessToday()
      ? await apiRequest("/access")
      : await apiRequest("/access", {
          method: "POST",
          body: { clientId: getClientId() },
        });
    renderAccessStats(stats);
    markAccessCountedToday();
    window.__accessCounterCounted = true;
    setAccessCounterStatus("サーバー同期");
  } catch (error) {
    console.warn("Access counter fallback:", error.message);
    renderAccessStats(bumpLocalAccessStats());
    window.__accessCounterCounted = true;
    setAccessCounterStatus("端末内（サーバー未接続）", true);
  } finally {
    window.__accessCounterInFlight = false;
  }
}
window.updateAccessCounter = updateAccessCounter;

async function resetTodayAccessCount() {
  try {
    const stats = await apiRequest("/access/reset-today", {
      method: "POST",
      body: {},
    });
    renderAccessStats(stats);
    markAccessCountedToday();
    window.__accessCounterCounted = true;
    setAccessCounterStatus("サーバー同期");
  } catch (error) {
    console.warn("Reset access count failed:", error.message);
    const data = loadLocalAccessStats();
    const today = getTodayKey();
    const previous = data.daily?.[today] || 0;
    data.total = Math.max(0, (data.total || 0) - previous);
    data.daily = data.daily || {};
    data.daily[today] = 0;
    saveLocalAccessStats(data);
    renderAccessStats(data);
  }
}
window.resetTodayAccessCount = resetTodayAccessCount;

function setupAccessAnalyticsToggle() {
  const toggle = document.getElementById("analysisToggle");
  const panel = document.getElementById("accessAnalytics");
  if (!toggle || !panel || toggle.__dailyNewsBound) return;
  toggle.__dailyNewsBound = true;
  toggle.addEventListener("click", () => {
    const willShow = panel.classList.contains("hidden");
    panel.classList.toggle("hidden", !willShow);
    toggle.textContent = willShow ? "閉じる" : "アクセス推移";
    toggle.setAttribute("aria-expanded", willShow ? "true" : "false");
    if (willShow) {
      renderAccessChart(accessStatsCache || loadLocalAccessStats());
    }
  });
}
window.setupAccessAnalyticsToggle = setupAccessAnalyticsToggle;
window.renderAccessChart = renderAccessChart;

async function trackArticleRead(itemId) {
  if (!itemId) return;
  const today = getTodayKey();
  if (hasReadToday(itemId, today)) return;
  try {
    const data = await apiRequest(
      `/interactions/${encodeURIComponent(itemId)}/read`,
      {
        method: "POST",
        keepalive: true,
        body: { clientId: getClientId() },
      },
    );
    markReadToday(itemId, today);
    mergeInteractionData(itemId, data);
  } catch (error) {
    console.warn("Read count update failed:", error.message);
    markReadToday(itemId, today);
    const local = getLocalInteractionData(itemId);
    local.reads = Math.max(local.reads || 0, getLocalReadCount(itemId));
    setLocalInteractionData(itemId, local);
  }
  updateRankings();
}
window.trackArticleRead = trackArticleRead;

const hoverReadTimers = new Map();

function startHoverRead(itemId) {
  if (!itemId || hasReadToday(itemId, getTodayKey())) return;
  if (hoverReadTimers.has(itemId)) return;
  hoverReadTimers.set(
    itemId,
    setTimeout(() => {
      hoverReadTimers.delete(itemId);
      trackArticleRead(itemId);
    }, 5000),
  );
}

function cancelHoverRead(itemId) {
  const timer = hoverReadTimers.get(itemId);
  if (!timer) return;
  clearTimeout(timer);
  hoverReadTimers.delete(itemId);
}

function setupHoverReadTracking() {
  const grid = document.getElementById("newsGrid");
  if (!grid || grid.__hoverReadBound) return;
  grid.__hoverReadBound = true;
  grid.addEventListener("mouseover", (event) => {
    const card = event.target.closest(".card");
    if (!card || !grid.contains(card) || card.contains(event.relatedTarget)) return;
    startHoverRead(card.id?.replace("card-", "") || "");
  });
  grid.addEventListener("mouseout", (event) => {
    const card = event.target.closest(".card");
    if (!card || !grid.contains(card) || card.contains(event.relatedTarget)) return;
    cancelHoverRead(card.id?.replace("card-", "") || "");
  });
}
window.setupHoverReadTracking = setupHoverReadTracking;

const liveElements = {};

function renderItem(itemId) {
  const elements = liveElements[itemId];
  if (!elements) return;
  const data = elements.lastData || getInteractionRenderData(itemId);
  if (elements.btnLike) {
    const count = elements.btnLike.querySelector(".count");
    if (count) count.textContent = data.likes || 0;
  }
  if (elements.btnComment) {
    const count = elements.btnComment.querySelector(".count");
    if (count) count.textContent = (data.comments || []).length;
  }
  if (elements.commentList) {
    elements.commentList.innerHTML = (data.comments || [])
      .map(
        (comment, index) => `
          <div class="comment-item">
            <div class="comment-user">${escapeHtml(comment.user || "Guest")}
              <span style="font-weight:normal;color:#888;font-size:10px;margin-left:6px;">${escapeHtml(comment.date || "")}</span>
            </div>
            <div class="comment-text">${escapeHtml(comment.text || "")}</div>
            ${comment.canDelete === false ? "" : `<button class="delete-btn" onclick="deleteComment('${escapeHtml(itemId)}', ${index})">×</button>`}
          </div>`,
      )
      .join("");
  }
  mergeInteractionData(itemId, {
    ...window.interactionsData[itemId],
    likes: data.likes,
    reads: data.reads,
    commentItems: data.comments,
    comments: data.comments.length,
  });
  updateRankings();
}

async function fetchInteractionDetail(itemId) {
  const detail = await apiRequest(
    `/interactions/${encodeURIComponent(itemId)}?clientId=${encodeURIComponent(getClientId())}`,
  );
  mergeInteractionData(itemId, detail);
  if (liveElements[itemId]) {
    liveElements[itemId].lastData = getInteractionRenderData(itemId);
    renderItem(itemId);
  }
  return detail;
}

window.subscribeItem = (itemId, btnLike, btnComment, commentList) => {
  if (!liveElements[itemId]) liveElements[itemId] = {};
  if (btnLike) liveElements[itemId].btnLike = btnLike;
  if (btnComment) liveElements[itemId].btnComment = btnComment;
  if (commentList) liveElements[itemId].commentList = commentList;
  liveElements[itemId].lastData = getInteractionRenderData(itemId);
  renderItem(itemId);

  if (!window.useLocalInteractions) {
    fetchInteractionDetail(itemId).catch((error) => {
      console.warn(`Interaction detail failed for ${itemId}:`, error.message);
    });
  }
};

window.toggleLike = async (itemId, button) => {
  const storageKey = `liked_${itemId}`;
  const wasLiked = Boolean(localStorage.getItem(storageKey));
  const desiredLiked = !wasLiked;
  const count = button.querySelector(".count");
  const previousCount = Number.parseInt(count?.textContent || "0", 10) || 0;
  const optimisticCount = Math.max(0, previousCount + (desiredLiked ? 1 : -1));
  button.classList.toggle("liked", desiredLiked);
  if (count) count.textContent = optimisticCount;
  if (desiredLiked) localStorage.setItem(storageKey, "true");
  else localStorage.removeItem(storageKey);
  mergeInteractionData(itemId, {
    ...(window.interactionsData[itemId] || {}),
    likes: optimisticCount,
  });
  updateRankings();

  if (window.useLocalInteractions) {
    const local = getLocalInteractionData(itemId);
    local.likes = optimisticCount;
    setLocalInteractionData(itemId, local);
    return;
  }

  try {
    const data = await apiRequest(
      `/interactions/${encodeURIComponent(itemId)}/like`,
      {
        method: "PUT",
        body: { clientId: getClientId(), liked: desiredLiked },
      },
    );
    mergeInteractionData(itemId, data);
    button.classList.toggle("liked", data.liked);
    if (data.liked) localStorage.setItem(storageKey, "true");
    else localStorage.removeItem(storageKey);
    if (count) count.textContent = data.likes || 0;
    updateRankings();
  } catch (error) {
    console.error("Like save failed:", error);
    button.classList.toggle("liked", wasLiked);
    if (count) count.textContent = previousCount;
    if (wasLiked) localStorage.setItem(storageKey, "true");
    else localStorage.removeItem(storageKey);
    mergeInteractionData(itemId, {
      ...(window.interactionsData[itemId] || {}),
      likes: previousCount,
    });
    alert("いいねの保存に失敗しました。通信状態を確認してください。");
  }
};

window.toggleComments = (itemId, button) => {
  const card = button.closest(".card") || button.closest(".idea-card");
  const section = card?.querySelector(".comment-section");
  const commentList = section?.querySelector(".comment-list");
  if (!section || !commentList) return;
  const isOpen = section.classList.toggle("open");
  button.classList.toggle("active-comment", isOpen);
  if (isOpen) window.subscribeItem(itemId, null, button, commentList);
};

window.submitComment = async (itemId, input) => {
  const text = input.value.trim();
  if (!text) return;
  input.value = "";

  if (window.useLocalInteractions) {
    const local = getLocalInteractionData(itemId);
    local.comments = Array.isArray(local.comments) ? local.comments : [];
    local.comments.push({
      user: "Guest",
      text,
      date: new Date().toLocaleDateString("ja-JP"),
      canDelete: true,
    });
    setLocalInteractionData(itemId, local);
    if (liveElements[itemId]) {
      liveElements[itemId].lastData = getInteractionRenderData(itemId);
      renderItem(itemId);
    }
    return;
  }

  try {
    const data = await apiRequest(
      `/interactions/${encodeURIComponent(itemId)}/comments`,
      {
        method: "POST",
        body: { clientId: getClientId(), user: "Guest", text },
      },
    );
    mergeInteractionData(itemId, data);
    if (liveElements[itemId]) {
      liveElements[itemId].lastData = getInteractionRenderData(itemId);
      renderItem(itemId);
    }
  } catch (error) {
    console.error("Comment save failed:", error);
    input.value = text;
    alert("コメントの保存に失敗しました。通信状態を確認してください。");
  }
};

window.deleteComment = async (itemId, commentIndex) => {
  if (!confirm("コメントを削除しますか？")) return;
  const interaction = window.interactionsData[itemId] || {};
  const comments = interaction.commentItems || [];
  const comment = comments[commentIndex];

  if (window.useLocalInteractions || !comment?.id) {
    comments.splice(commentIndex, 1);
    setLocalInteractionData(itemId, {
      ...interaction,
      comments,
      commentItems: comments,
    });
    if (liveElements[itemId]) {
      liveElements[itemId].lastData = getInteractionRenderData(itemId);
      renderItem(itemId);
    }
    return;
  }

  try {
    const data = await apiRequest(
      `/interactions/${encodeURIComponent(itemId)}/comments/${comment.id}?clientId=${encodeURIComponent(getClientId())}`,
      { method: "DELETE" },
    );
    mergeInteractionData(itemId, data);
    if (liveElements[itemId]) {
      liveElements[itemId].lastData = getInteractionRenderData(itemId);
      renderItem(itemId);
    }
  } catch (error) {
    console.error("Comment delete failed:", error);
    alert(
      error.status === 403
        ? "このコメントは投稿した端末からのみ削除できます。"
        : "コメントの削除に失敗しました。",
    );
  }
};

const interactionObserver = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      const card = entry.target;
      const likeButton = card.querySelector(
        '.action-btn[onclick*="toggleLike"]',
      );
      const match = likeButton
        ?.getAttribute("onclick")
        ?.match(/'([^']+)'/);
      if (match) {
        const itemId = match[1];
        window.subscribeItem(
          itemId,
          likeButton,
          card.querySelector(".btn-comment"),
          null,
        );
        likeButton.classList.toggle(
          "liked",
          Boolean(localStorage.getItem(`liked_${itemId}`)),
        );
      }
      interactionObserver.unobserve(card);
    });
  },
  { threshold: 0.1 },
);

function observeInteractionCards(root = document) {
  root.querySelectorAll?.(".card, .idea-card").forEach((element) => {
    interactionObserver.observe(element);
  });
}

setTimeout(() => observeInteractionCards(), 1000);
new MutationObserver((records) => {
  records.forEach((record) => {
    record.addedNodes.forEach((node) => {
      if (node.nodeType === Node.ELEMENT_NODE) observeInteractionCards(node);
    });
  });
}).observe(document.documentElement, { childList: true, subtree: true });
