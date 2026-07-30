"use strict";

const state = {
  posts: [],
  meta: { categories: [], regions: [], tags: [] },
  query: "",
  category: "",
  sort: "latest",
  selectedPost: null,
};

const elements = {
  postCount: document.querySelector("#postCount"),
  searchInput: document.querySelector("#searchInput"),
  sortSelect: document.querySelector("#sortSelect"),
  categoryFilters: document.querySelector("#categoryFilters"),
  activeFilters: document.querySelector("#activeFilters"),
  galleryGrid: document.querySelector("#galleryGrid"),
  emptyState: document.querySelector("#emptyState"),
  loadingState: document.querySelector("#loadingState"),
  resetFilters: document.querySelector("#resetFilters"),
  dialog: document.querySelector("#postDialog"),
  dialogContent: document.querySelector("#dialogContent"),
  closeDialog: document.querySelector("#closeDialog"),
  toast: document.querySelector("#toast"),
};

const CLIENT_ID_KEY = "interiorgram_client_id_v1";
const USER_NAME_KEY = "interiorgram_user_name_v1";
const clientId = getClientId();
let searchTimer = null;
let toastTimer = null;

function getClientId() {
  let value = localStorage.getItem(CLIENT_ID_KEY);
  if (!value) {
    value =
      typeof crypto.randomUUID === "function"
        ? crypto.randomUUID().replaceAll("-", "")
        : `client_${Date.now()}_${Math.random().toString(36).slice(2)}`;
    localStorage.setItem(CLIENT_ID_KEY, value);
  }
  return value;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || `通信エラー (${response.status})`);
  }
  return data;
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function formatDate(value) {
  const date = new Date(
    /^\d{4}-\d{2}-\d{2}$/.test(value) ? `${value}T00:00:00` : value,
  );
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("ja-JP", {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(date);
}

function showToast(message) {
  elements.toast.textContent = message;
  elements.toast.classList.add("visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => elements.toast.classList.remove("visible"), 2600);
}

async function loadMeta() {
  const data = await api("api/meta");
  state.meta = data;
  renderCategoryFilters();
}

async function loadPosts() {
  elements.loadingState.classList.remove("hidden");
  elements.emptyState.hidden = true;
  const params = new URLSearchParams({
    clientId,
    sort: state.sort,
  });
  if (state.query) params.set("q", state.query);
  if (state.category) params.set("category", state.category);

  try {
    const data = await api(`api/posts?${params}`);
    state.posts = data.posts || [];
    renderPosts();
  } catch (error) {
    state.posts = [];
    renderPosts();
    showToast(error.message);
  } finally {
    elements.loadingState.classList.add("hidden");
  }
}

function renderCategoryFilters() {
  elements.categoryFilters.replaceChildren();
  const filters = [
    { category: "", label: "すべて" },
    ...state.meta.categories.map((item) => ({
      category: item.category,
      label: `${item.category} ${item.count}`,
    })),
  ];
  for (const filter of filters) {
    const button = el("button", "filter-chip", filter.label);
    button.type = "button";
    button.classList.toggle("active", state.category === filter.category);
    button.addEventListener("click", () => {
      state.category = filter.category;
      renderCategoryFilters();
      updateActiveFilters();
      loadPosts();
    });
    elements.categoryFilters.append(button);
  }
}

function updateActiveFilters() {
  elements.activeFilters.replaceChildren();
  const pieces = [];
  if (state.query) pieces.push(`検索「${state.query}」`);
  if (state.category) pieces.push(`カテゴリ「${state.category}」`);
  if (!pieces.length) return;
  elements.activeFilters.append(
    document.createTextNode(`${pieces.join(" / ")}で絞り込み中`),
  );
  const reset = el("button", "", "解除");
  reset.type = "button";
  reset.addEventListener("click", resetFilters);
  elements.activeFilters.append(reset);
}

function renderPosts() {
  elements.galleryGrid.replaceChildren();
  elements.postCount.textContent = new Intl.NumberFormat("ja-JP").format(
    state.posts.length,
  );
  elements.emptyState.hidden = state.posts.length > 0;

  state.posts.forEach((post, index) => {
    elements.galleryGrid.append(createCard(post, index));
  });
}

function createCard(post, index) {
  const article = el("article", "idea-card");
  article.tabIndex = 0;
  article.setAttribute("aria-label", post.title);
  article.addEventListener("click", () => openPost(post.id));
  article.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      openPost(post.id);
    }
  });

  const visual = el("div", "card-visual");
  if (post.image) {
    const image = document.createElement("img");
    image.src = post.image;
    image.alt = post.imageAlt || post.title;
    image.loading = "lazy";
    image.addEventListener("error", () => {
      image.replaceWith(el("div", "visual-placeholder", "Interior / Idea"));
    });
    visual.append(image);
  } else {
    visual.append(el("div", "visual-placeholder", "Interior / Idea"));
  }
  visual.append(el("span", "card-index", String(index + 1).padStart(2, "0")));
  if (post.featured) visual.append(el("span", "card-featured", "FEATURED"));

  const copy = el("div", "card-copy");
  const meta = el("div", "card-meta");
  meta.append(
    el("span", "", post.category.toUpperCase()),
    el("span", "", post.region),
    el("span", "", formatDate(post.publishedAt)),
  );
  copy.append(meta, el("h3", "", post.title));
  if (post.summary) copy.append(el("p", "", post.summary));

  const footer = el("div", "card-footer");
  const tags = el("div", "tag-row");
  post.tags.slice(0, 3).forEach((tag) => tags.append(el("span", "tag", `#${tag}`)));
  const engagement = el("div", "engagement");
  engagement.append(
    el("span", "", `♥ ${post.likes}`),
    el("span", "", `◌ ${post.comments}`),
  );
  footer.append(tags, engagement);
  copy.append(footer);
  article.append(visual, copy);
  return article;
}

async function openPost(postId) {
  try {
    const data = await api(
      `api/posts/${encodeURIComponent(postId)}?clientId=${encodeURIComponent(clientId)}`,
    );
    state.selectedPost = data.post;
    renderDialog();
    elements.dialog.showModal();
    document.body.style.overflow = "hidden";
    recordView(postId);
    loadComments(postId);
  } catch (error) {
    showToast(error.message);
  }
}

function renderDialog() {
  const post = state.selectedPost;
  elements.dialogContent.replaceChildren();
  if (!post) return;

  const layout = el("div", "dialog-layout");
  const visual = el("div", "dialog-visual");
  if (post.image) {
    const image = document.createElement("img");
    image.src = post.image;
    image.alt = post.imageAlt || post.title;
    image.addEventListener("error", () => {
      image.replaceWith(el("div", "visual-placeholder", "Interior / Idea"));
    });
    visual.append(image);
  } else {
    visual.append(el("div", "visual-placeholder", "Interior / Idea"));
  }

  const copy = el("div", "dialog-copy");
  copy.append(
    el(
      "p",
      "eyebrow",
      `${post.category.toUpperCase()} / ${post.region} / ${formatDate(post.publishedAt)}`,
    ),
    el("h2", "", post.title),
  );
  if (post.summary) copy.append(el("p", "dialog-summary", post.summary));
  if (post.body) copy.append(el("div", "dialog-body", post.body));

  const tags = el("div", "dialog-tags");
  post.tags.forEach((tag) => tags.append(el("span", "tag", `#${tag}`)));
  copy.append(tags);

  const actions = el("div", "dialog-actions");
  const likeButton = el(
    "button",
    `like-button${post.liked ? " active" : ""}`,
    `${post.liked ? "♥" : "♡"} いいね ${post.likes}`,
  );
  likeButton.type = "button";
  likeButton.addEventListener("click", toggleLike);
  actions.append(likeButton, el("span", "view-count", `閲覧 ${post.views}`));
  copy.append(actions, createCommentsPanel(post.id));
  layout.append(visual, copy);
  elements.dialogContent.append(layout);
}

function createCommentsPanel(postId) {
  const panel = el("section", "comments-panel");
  panel.append(el("h3", "", "コメント"));
  const list = el("div", "comment-list");
  list.dataset.postId = postId;
  list.append(el("p", "comment-empty", "読み込み中..."));
  panel.append(list);

  const form = el("form", "comment-form");
  const name = document.createElement("input");
  name.type = "text";
  name.maxLength = 40;
  name.placeholder = "名前";
  name.value = localStorage.getItem(USER_NAME_KEY) || "";
  const message = document.createElement("input");
  message.type = "text";
  message.maxLength = 500;
  message.required = true;
  message.placeholder = "アイデアへのコメント";
  const submit = el("button", "", "送信");
  submit.type = "submit";
  form.append(name, message, submit);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const text = message.value.trim();
    if (!text) return;
    submit.disabled = true;
    try {
      const userName = name.value.trim() || "Guest";
      localStorage.setItem(USER_NAME_KEY, userName);
      await api(`api/posts/${encodeURIComponent(postId)}/comments`, {
        method: "POST",
        body: JSON.stringify({ clientId, userName, text }),
      });
      message.value = "";
      state.selectedPost.comments += 1;
      await loadComments(postId);
      refreshCardCounts(postId);
      showToast("コメントを投稿しました");
    } catch (error) {
      showToast(error.message);
    } finally {
      submit.disabled = false;
    }
  });
  panel.append(form);
  return panel;
}

async function loadComments(postId) {
  const list = elements.dialogContent.querySelector(
    `.comment-list[data-post-id="${CSS.escape(postId)}"]`,
  );
  if (!list) return;
  try {
    const data = await api(`api/posts/${encodeURIComponent(postId)}/comments`);
    list.replaceChildren();
    if (!data.comments.length) {
      list.append(el("p", "comment-empty", "まだコメントはありません。"));
      return;
    }
    data.comments.forEach((comment) => {
      const item = el("article", "comment");
      const head = el("div", "comment-head");
      head.append(
        el("strong", "", comment.userName),
        el("span", "", formatDate(comment.createdAt)),
      );
      item.append(head, el("p", "", comment.text));
      list.append(item);
    });
  } catch (error) {
    list.replaceChildren(el("p", "comment-empty", error.message));
  }
}

async function toggleLike() {
  const post = state.selectedPost;
  if (!post) return;
  try {
    const result = await api(`api/posts/${encodeURIComponent(post.id)}/like`, {
      method: "POST",
      body: JSON.stringify({ clientId }),
    });
    post.liked = result.liked;
    post.likes = result.likes;
    renderDialog();
    loadComments(post.id);
    refreshCardCounts(post.id);
  } catch (error) {
    showToast(error.message);
  }
}

async function recordView(postId) {
  try {
    const result = await api(`api/posts/${encodeURIComponent(postId)}/view`, {
      method: "POST",
      body: JSON.stringify({ clientId }),
    });
    if (state.selectedPost?.id === postId) {
      state.selectedPost.views = result.views;
      const count = elements.dialogContent.querySelector(".view-count");
      if (count) count.textContent = `閲覧 ${result.views}`;
    }
  } catch (_) {
    // View counting is non-critical.
  }
}

function refreshCardCounts(postId) {
  const post = state.posts.find((item) => item.id === postId);
  if (post && state.selectedPost?.id === postId) {
    post.likes = state.selectedPost.likes;
    post.comments = state.selectedPost.comments;
    post.views = state.selectedPost.views;
    renderPosts();
  }
}

function closeDialog() {
  elements.dialog.close();
  elements.dialogContent.replaceChildren();
  state.selectedPost = null;
  document.body.style.overflow = "";
}

function resetFilters() {
  state.query = "";
  state.category = "";
  elements.searchInput.value = "";
  renderCategoryFilters();
  updateActiveFilters();
  loadPosts();
}

elements.searchInput.addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    state.query = elements.searchInput.value.trim();
    updateActiveFilters();
    loadPosts();
  }, 260);
});

elements.sortSelect.addEventListener("change", () => {
  state.sort = elements.sortSelect.value;
  loadPosts();
});

elements.resetFilters.addEventListener("click", resetFilters);
elements.closeDialog.addEventListener("click", closeDialog);
elements.dialog.addEventListener("click", (event) => {
  if (event.target === elements.dialog) closeDialog();
});
elements.dialog.addEventListener("cancel", (event) => {
  event.preventDefault();
  closeDialog();
});

async function init() {
  try {
    await Promise.all([loadMeta(), loadPosts()]);
  } catch (error) {
    showToast(error.message);
  }
}

init();
