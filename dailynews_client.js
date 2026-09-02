"use strict";

const API_BASE = "/api";
const CLIENT_ID_KEY = "dailynews_client_id_v1";
const LOCAL_ACCESS_KEY = "local_access_stats";
const LOCAL_INTERACTIONS_KEY = "local_interactions";
const LOCAL_READS_KEY = "local_article_reads";
const LOCAL_ACCESS_MARK_KEY = "local_access_mark_date_v3";
const JST_OFFSET_MS = 9 * 60 * 60 * 1000;
const IRRELEVANT_TOOLTIP =
  "この記事が内装開発と関係ない場合に押してください。今後の関連度判定の精度向上に活用します。";

let accessStatsCache = null;
let localInteractionsCache = null;
let interactionPollTimer = null;
let hoverCommentTimer = null;
let hoverCommentTarget = null;
const hoverCommentCache = new Map();

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
window.getDailyNewsClientId = getClientId;

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
  const width = Math.max(760, (series.length - 1) * 26 + 72);
  const height = 220;
  const padding = { top: 18, right: 18, bottom: 38, left: 42 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const xFor = (index) => padding.left + (series.length === 1 ? plotWidth / 2 : (index / (series.length - 1)) * plotWidth);
  const yFor = (value) => padding.top + plotHeight - (value / max) * plotHeight;
  const points = series.map((item, index) => `${xFor(index).toFixed(1)},${yFor(item.value).toFixed(1)}`).join(" ");
  const areaPoints = `${padding.left},${padding.top + plotHeight} ${points} ${padding.left + plotWidth},${padding.top + plotHeight}`;
  const labelStep = Math.max(1, Math.ceil(series.length / 10));

  const gridLines = [0, 0.25, 0.5, 0.75, 1].map((ratio) => {
    const y = padding.top + plotHeight - ratio * plotHeight;
    return `<line class="access-line-grid" x1="${padding.left}" y1="${y}" x2="${padding.left + plotWidth}" y2="${y}"></line>
      <text class="access-line-axis-label" x="${padding.left - 8}" y="${y + 3}" text-anchor="end">${Math.round(max * ratio)}</text>`;
  }).join("");

  const xLabels = series.map((item, index) => {
    if (index % labelStep !== 0 && index !== series.length - 1) return "";
    return `<text class="access-line-axis-label" x="${xFor(index)}" y="${height - 12}" text-anchor="middle">${item.label}</text>`;
  }).join("");

  const pointNodes = series.map((item, index) => `
    <circle class="access-line-point" cx="${xFor(index)}" cy="${yFor(item.value)}" r="4" tabindex="0">
      <title>${item.key}: ${item.value}</title>
    </circle>`).join("");

  chart.innerHTML = `
    <svg class="access-line-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="日別アクセス数の折れ線グラフ">
      <defs>
        <linearGradient id="accessAreaGradient" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#7df1c2" stop-opacity="0.32"></stop>
          <stop offset="100%" stop-color="#7df1c2" stop-opacity="0.02"></stop>
        </linearGradient>
      </defs>
      ${gridLines}
      <polygon class="access-line-area" points="${areaPoints}"></polygon>
      <polyline class="access-line-path" points="${points}"></polyline>
      ${pointNodes}
      ${xLabels}
    </svg>`;
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
    irrelevant: 0,
    markedIrrelevant: false,
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
    likedBy: Array.isArray(data.likedBy) ? data.likedBy : previous.likedBy || [],
    irrelevant:
      typeof data.irrelevant === "number"
        ? data.irrelevant
        : Number(previous.irrelevant || 0),
    markedIrrelevant:
      typeof data.markedIrrelevant === "boolean"
        ? data.markedIrrelevant
        : Boolean(previous.markedIrrelevant),
  };
}

function getInteractionRenderData(itemId) {
  const data = window.interactionsData[itemId] || {};
  return {
    likes: data.likes || 0,
    comments: data.commentItems || [],
    commentCount:
      typeof data.comments === "number"
        ? data.comments
        : (data.commentItems || []).length,
    reads: data.reads || 0,
    liked: Boolean(data.liked),
    likedBy: data.likedBy || [],
    irrelevant: data.irrelevant || 0,
    markedIrrelevant: Boolean(data.markedIrrelevant),
  };
}

function likeTooltipText(data = {}) {
  const names = [...new Set((data.likedBy || []).filter(Boolean))];
  const total = Number(data.likes || 0);
  const unnamed = Math.max(0, total - names.length);
  if (!total) return "まだいいねはありません";
  if (!names.length) return `いいね ${total}件（登録前または未ログインの反応）`;
  return `いいねした人: ${names.join("、")}${unnamed ? `、ほか${unnamed}人` : ""}`;
}

function updateLikeTooltip(button, data) {
  if (!button) return;
  const label = likeTooltipText(data);
  button.title = label;
  button.setAttribute("aria-label", label);
}

function updateIrrelevantButton(button, data = {}) {
  if (!button) return;
  const count = button.querySelector(".count");
  if (count) count.textContent = Number(data.irrelevant || 0);
  button.classList.toggle("marked-irrelevant", Boolean(data.markedIrrelevant));
  button.dataset.tooltip = IRRELEVANT_TOOLTIP;
  button.title = IRRELEVANT_TOOLTIP;
  button.setAttribute("aria-label", IRRELEVANT_TOOLTIP);
}

function refreshInteractionCounts() {
  const interactions = window.interactionsData || {};
  document
    .querySelectorAll(".card, .idea-card, .ranking-item[data-news-id]")
    .forEach((card) => {
      const likeButton = card.querySelector(
        '.action-btn[onclick*="toggleLike"]',
      );
      const itemId =
        card.dataset.newsId ||
        (card.id?.startsWith("card-")
          ? card.id.slice(5)
          : likeButton?.getAttribute("onclick")?.match(/'([^']+)'/)?.[1]);
      if (!itemId) return;
      const data = interactions[itemId];
      if (!data) return;
      const likeCount = likeButton?.querySelector(".count");
      const commentCount = card.querySelector(".btn-comment .count");
      const irrelevantButton = card.querySelector(".relevance-feedback-btn");
      const readCount = card.querySelector(".read-count");
      if (likeCount) likeCount.textContent = data.likes || 0;
      if (commentCount) commentCount.textContent = data.comments || 0;
      if (readCount) readCount.textContent = `閲覧 ${data.reads || 0}`;
      updateLikeTooltip(likeButton, data);
      updateIrrelevantButton(irrelevantButton, data);
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
    const previousReactions = Object.entries(window.interactionsData || {})
      .map(
        ([id, value]) =>
          `${id}:${value.likes || 0}:${value.comments || 0}:${value.irrelevant || 0}`,
      )
      .join("|");
    const payload = await apiRequest("/interactions");
    Object.entries(payload.interactions || {}).forEach(([itemId, value]) => {
      mergeInteractionData(itemId, value);
    });
    window.firebaseInteractionsReady = true;
    window.useLocalInteractions = false;
    updateRankings();
    const currentReactions = Object.entries(window.interactionsData || {})
      .map(
        ([id, value]) =>
          `${id}:${value.likes || 0}:${value.comments || 0}:${value.irrelevant || 0}`,
      )
      .join("|");
    if (currentReactions !== previousReactions) window.refreshNewsReactionSort?.();
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
    elements.btnLike.classList.toggle("liked", data.liked);
    updateLikeTooltip(elements.btnLike, data);
  }
  if (elements.btnComment) {
    const count = elements.btnComment.querySelector(".count");
    if (count) count.textContent = data.commentCount || 0;
  }
  updateIrrelevantButton(elements.btnIrrelevant, data);
  if (elements.commentList) {
    elements.commentList.innerHTML = (data.comments || [])
      .map(
        (comment, index) => `
          <div class="comment-item${comment.parentId ? " reply-comment" : ""}" data-comment-id="${Number(comment.id || 0)}">
            <div class="comment-user">${escapeHtml(comment.user || "Guest")}
              <span style="font-weight:normal;color:#888;font-size:10px;margin-left:6px;">${escapeHtml(comment.date || "")}</span>
              ${comment.parentId ? '<span class="comment-reply-label">返信</span>' : ""}
            </div>
            <div class="comment-text">${escapeHtml(comment.text || "")}</div>
            <div class="comment-actions">
              ${comment.id ? `<button class="comment-like-btn${comment.liked ? " liked" : ""}" type="button" onclick="toggleCommentLike('${escapeHtml(itemId)}', ${comment.id}, ${comment.liked ? "false" : "true"})">&#128077; ${Number(comment.likes || 0)}</button>` : ""}
              ${comment.id ? `<button class="comment-reply-btn" type="button" onclick="replyToComment('${escapeHtml(itemId)}', ${comment.id})">返信</button>` : ""}
              ${comment.canDelete === false ? "" : `<button class="delete-btn" onclick="deleteComment('${escapeHtml(itemId)}', ${index})">&#21066;&#38500;</button>`}
            </div>
          </div>`,
      )
      .join("");
  }
  mergeInteractionData(itemId, {
    ...window.interactionsData[itemId],
    likes: data.likes,
    reads: data.reads,
    commentItems: data.comments,
    comments: data.commentCount,
    likedBy: data.likedBy,
    irrelevant: data.irrelevant,
    markedIrrelevant: data.markedIrrelevant,
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

function getCommentHoverBubble() {
  let bubble = document.getElementById("commentHoverBubble");
  if (bubble) return bubble;
  bubble = document.createElement("aside");
  bubble.id = "commentHoverBubble";
  bubble.className = "comment-hover-bubble";
  bubble.setAttribute("role", "status");
  bubble.setAttribute("aria-live", "polite");
  document.body.appendChild(bubble);
  return bubble;
}

function positionCommentHoverBubble(target, bubble) {
  const rect = target.getBoundingClientRect();
  const margin = 12;
  const left = Math.min(
    Math.max(margin, rect.left + 18),
    window.innerWidth - bubble.offsetWidth - margin,
  );
  let top = rect.top - bubble.offsetHeight - margin;
  if (top < margin) top = rect.bottom + margin;
  top = Math.min(top, window.innerHeight - bubble.offsetHeight - margin);
  bubble.style.left = `${left}px`;
  bubble.style.top = `${Math.max(margin, top)}px`;
}

function hideCommentHoverBubble() {
  const bubble = document.getElementById("commentHoverBubble");
  bubble?.classList.remove("visible");
  hoverCommentTarget = null;
}

function renderCommentHoverBubble(target, itemId, data) {
  if (hoverCommentTarget !== target || !document.contains(target)) {
    hideCommentHoverBubble();
    return;
  }
  const comments = Array.isArray(data?.commentItems) ? data.commentItems : [];
  const total = Number(data?.comments || comments.length || 0);
  if (!total || !comments.length) {
    hideCommentHoverBubble();
    return;
  }
  const shown = comments.slice(-3).reverse();
  const bubble = getCommentHoverBubble();
  bubble.innerHTML = `
    <div class="comment-hover-title">💬 コメント ${total}件</div>
    ${shown
      .map(
        (comment) => `<div class="comment-hover-item">
          <div class="comment-hover-user">${escapeHtml(comment.user || "Guest")}${comment.date ? ` · ${escapeHtml(comment.date)}` : ""}</div>
          <div class="comment-hover-text">${escapeHtml(comment.text || "")}</div>
        </div>`,
      )
      .join("")}
    ${total > shown.length ? `<div class="comment-hover-more">ほか ${total - shown.length}件。💬ボタンからすべて表示できます。</div>` : ""}`;
  bubble.classList.add("visible");
  positionCommentHoverBubble(target, bubble);
}

async function showCommentHoverBubble(target, itemId) {
  const summary = window.interactionsData[itemId] || {};
  if (Number(summary.comments || 0) <= 0) return;
  hoverCommentTarget = target;
  if (hoverCommentCache.has(itemId)) {
    renderCommentHoverBubble(target, itemId, hoverCommentCache.get(itemId));
    return;
  }
  const bubble = getCommentHoverBubble();
  bubble.innerHTML = '<div class="comment-hover-title">💬 コメントを読み込み中...</div>';
  bubble.classList.add("visible");
  positionCommentHoverBubble(target, bubble);
  try {
    const detail = await fetchInteractionDetail(itemId);
    hoverCommentCache.set(itemId, detail);
    renderCommentHoverBubble(target, itemId, detail);
  } catch (error) {
    console.warn(`Comment preview failed for ${itemId}:`, error.message);
    hideCommentHoverBubble();
  }
}

function setupCommentHoverPreview() {
  if (document.documentElement.dataset.commentHoverBound) return;
  document.documentElement.dataset.commentHoverBound = "true";
  const selector = ".card[data-news-id], .ranking-item[data-news-id]";
  document.addEventListener("mouseover", (event) => {
    if (event.target.closest(".relevance-feedback-btn")) {
      clearTimeout(hoverCommentTimer);
      hideCommentHoverBubble();
      return;
    }
    const target = event.target.closest(selector);
    if (!target || target.contains(event.relatedTarget)) return;
    clearTimeout(hoverCommentTimer);
    hoverCommentTimer = setTimeout(() => {
      showCommentHoverBubble(target, target.dataset.newsId);
    }, 350);
  });
  document.addEventListener("mouseout", (event) => {
    const target = event.target.closest(selector);
    if (!target || target.contains(event.relatedTarget)) return;
    clearTimeout(hoverCommentTimer);
    if (hoverCommentTarget === target) hideCommentHoverBubble();
  });
  window.addEventListener("scroll", hideCommentHoverBubble, { passive: true });
  window.addEventListener("resize", hideCommentHoverBubble);
}

window.subscribeItem = (
  itemId,
  btnLike,
  btnComment,
  commentList,
  btnIrrelevant,
) => {
  if (!liveElements[itemId]) liveElements[itemId] = {};
  if (btnLike) liveElements[itemId].btnLike = btnLike;
  if (btnComment) liveElements[itemId].btnComment = btnComment;
  if (commentList) liveElements[itemId].commentList = commentList;
  if (btnIrrelevant) liveElements[itemId].btnIrrelevant = btnIrrelevant;
  liveElements[itemId].lastData = getInteractionRenderData(itemId);
  renderItem(itemId);

  if (!window.useLocalInteractions) {
    fetchInteractionDetail(itemId).catch((error) => {
      console.warn(`Interaction detail failed for ${itemId}:`, error.message);
    });
  }
};

window.toggleIrrelevant = async (itemId, button) => {
  if (window.useLocalInteractions) {
    alert(
      "サーバーに接続できないため、関連なしの評価を保存できません。時間をおいて再度お試しください。",
    );
    return;
  }

  const previous = window.interactionsData[itemId] || {};
  const wasMarked = Boolean(
    previous.markedIrrelevant || button.classList.contains("marked-irrelevant"),
  );
  const desiredMarked = !wasMarked;
  const previousCount = Number(previous.irrelevant || 0);
  const optimisticCount = Math.max(
    0,
    previousCount + (desiredMarked ? 1 : -1),
  );
  mergeInteractionData(itemId, {
    ...previous,
    irrelevant: optimisticCount,
    markedIrrelevant: desiredMarked,
  });
  updateIrrelevantButton(button, window.interactionsData[itemId]);
  updateRankings();

  try {
    const data = await apiRequest(
      `/interactions/${encodeURIComponent(itemId)}/irrelevant`,
      {
        method: "PUT",
        body: {
          clientId: getClientId(),
          markedIrrelevant: desiredMarked,
        },
      },
    );
    mergeInteractionData(itemId, data);
    hoverCommentCache.delete(itemId);
    updateIrrelevantButton(button, data);
    updateRankings();
  } catch (error) {
    console.error("Irrelevant feedback save failed:", error);
    mergeInteractionData(itemId, {
      ...previous,
      irrelevant: previousCount,
      markedIrrelevant: wasMarked,
    });
    updateIrrelevantButton(button, window.interactionsData[itemId]);
    updateRankings();
    if (error.status === 401) {
      window.dailyNewsAccount?.openAuth(
        "login",
        "関連なしの評価を保存するにはログインしてください。",
      );
      return;
    }
    alert("関連なしの評価を保存できませんでした。通信状態を確認してください。");
  }
};

window.toggleLike = async (itemId, button) => {
  const storageKey = `liked_${itemId}`;
  const wasLiked = Boolean(
    window.interactionsData[itemId]?.liked ||
    button.classList.contains("liked") ||
    localStorage.getItem(storageKey),
  );
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
    window.refreshNewsReactionSort?.();
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
    hoverCommentCache.delete(itemId);
    button.classList.toggle("liked", data.liked);
    if (data.liked) localStorage.setItem(storageKey, "true");
    else localStorage.removeItem(storageKey);
    if (count) count.textContent = data.likes || 0;
    updateRankings();
    window.refreshNewsReactionSort?.();
    window.dispatchEvent(new CustomEvent("dailynews:activity-updated"));
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
    if (error.status === 401) {
      window.dailyNewsAccount?.openAuth(
        "login",
        "いいねを保存するにはログインしてください。",
      );
      return;
    }
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

async function saveComment(itemId, text, parentCommentId = null, input = null) {
  if (!text) return;
  if (input) input.value = "";

  if (window.useLocalInteractions) {
    if (input) input.value = text;
    alert("サーバーに接続できないため、コメントを保存できません。時間をおいて再度お試しください。");
    return;
  }

  try {
    const data = await apiRequest(
      `/interactions/${encodeURIComponent(itemId)}/comments`,
      {
        method: "POST",
        body: { clientId: getClientId(), text, parentCommentId },
      },
    );
    mergeInteractionData(itemId, data);
    hoverCommentCache.delete(itemId);
    if (liveElements[itemId]) {
      liveElements[itemId].lastData = getInteractionRenderData(itemId);
      renderItem(itemId);
    }
    window.dispatchEvent(new CustomEvent("dailynews:activity-updated"));
  } catch (error) {
    console.error("Comment save failed:", error);
    if (input) input.value = text;
    if (error.status === 401) {
      window.dailyNewsAccount?.openAuth(
        "login",
        "コメントを投稿するにはログインしてください。",
      );
      return;
    }
    alert("コメントの保存に失敗しました。通信状態を確認してください。");
  }
}

window.submitComment = async (itemId, input) => {
  const text = input.value.trim();
  await saveComment(itemId, text, null, input);
};

window.replyToComment = async (itemId, commentId) => {
  const text = window.prompt("返信を入力してください。");
  if (!text?.trim()) return;
  await saveComment(itemId, text.trim(), commentId);
};

window.toggleCommentLike = async (itemId, commentId, liked) => {
  try {
    const data = await apiRequest(
      `/interactions/${encodeURIComponent(itemId)}/comments/${commentId}/like`,
      {
        method: "PUT",
        body: { clientId: getClientId(), liked: Boolean(liked) },
      },
    );
    mergeInteractionData(itemId, data);
    hoverCommentCache.delete(itemId);
    if (liveElements[itemId]) {
      liveElements[itemId].lastData = getInteractionRenderData(itemId);
      renderItem(itemId);
    }
    window.dispatchEvent(new CustomEvent("dailynews:activity-updated"));
  } catch (error) {
    if (error.status === 401) {
      window.dailyNewsAccount?.openAuth(
        "login",
        "コメントにいいねするにはログインしてください。",
      );
      return;
    }
    console.error("Comment like failed:", error);
  }
};

window.addEventListener("dailynews:account-changed", () => {
  Object.keys(liveElements).forEach((itemId) => {
    fetchInteractionDetail(itemId).catch(() => {});
  });
});

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
    hoverCommentCache.delete(itemId);
    if (liveElements[itemId]) {
      liveElements[itemId].lastData = getInteractionRenderData(itemId);
      renderItem(itemId);
    }
    window.dispatchEvent(new CustomEvent("dailynews:activity-updated"));
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
          card.querySelector(".relevance-feedback-btn"),
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

setupCommentHoverPreview();
setTimeout(() => observeInteractionCards(), 1000);
new MutationObserver((records) => {
  records.forEach((record) => {
    record.addedNodes.forEach((node) => {
      if (node.nodeType === Node.ELEMENT_NODE) observeInteractionCards(node);
    });
  });
}).observe(document.documentElement, { childList: true, subtree: true });
