"use strict";

const fs = require("fs");
const http = require("http");
const path = require("path");
const { DatabaseSync } = require("node:sqlite");

const ROOT = path.resolve(__dirname, "..");
const PUBLIC_DIR = path.join(ROOT, "public");
const CONTENT_DIR = path.join(ROOT, "content");
const MEDIA_DIR = path.join(CONTENT_DIR, "images");
const DATA_DIR = path.join(ROOT, "data");
const LOG_DIR = path.join(ROOT, "logs");
const DB_FILE = path.join(DATA_DIR, "interiorgram.sqlite");
const CONTENT_FILE = path.join(CONTENT_DIR, "posts.json");
const LOG_FILE = path.join(LOG_DIR, "server.log");
const HOST = process.env.INTERIORGRAM_HOST || "127.0.0.1";
const PORT = Number(process.env.INTERIORGRAM_PORT || 8083);

const MIME_TYPES = new Map([
  [".css", "text/css; charset=utf-8"],
  [".gif", "image/gif"],
  [".html", "text/html; charset=utf-8"],
  [".ico", "image/x-icon"],
  [".jpeg", "image/jpeg"],
  [".jpg", "image/jpeg"],
  [".js", "text/javascript; charset=utf-8"],
  [".json", "application/json; charset=utf-8"],
  [".png", "image/png"],
  [".svg", "image/svg+xml"],
  [".webp", "image/webp"],
]);

for (const directory of [DATA_DIR, LOG_DIR, CONTENT_DIR, MEDIA_DIR]) {
  fs.mkdirSync(directory, { recursive: true });
}

const db = new DatabaseSync(DB_FILE);
db.exec(`
  PRAGMA journal_mode = WAL;
  PRAGMA synchronous = NORMAL;
  PRAGMA foreign_keys = ON;
  PRAGMA busy_timeout = 5000;

  CREATE TABLE IF NOT EXISTS posts (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    body TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'アイデア',
    region TEXT NOT NULL DEFAULT 'グローバル',
    tags_json TEXT NOT NULL DEFAULT '[]',
    image_path TEXT NOT NULL DEFAULT '',
    image_alt TEXT NOT NULL DEFAULT '',
    author TEXT NOT NULL DEFAULT 'Interiorgram',
    source_ids_json TEXT NOT NULL DEFAULT '[]',
    published_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'published',
    featured INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
  );

  CREATE TABLE IF NOT EXISTS likes (
    post_id TEXT NOT NULL,
    client_id TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (post_id, client_id),
    FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE
  );

  CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id TEXT NOT NULL,
    client_id TEXT NOT NULL,
    user_name TEXT NOT NULL DEFAULT 'Guest',
    comment_text TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE
  );

  CREATE TABLE IF NOT EXISTS views (
    post_id TEXT NOT NULL,
    client_id TEXT NOT NULL,
    date_key TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (post_id, client_id, date_key),
    FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE
  );

  CREATE INDEX IF NOT EXISTS posts_published_at_idx
    ON posts(status, published_at DESC);
  CREATE INDEX IF NOT EXISTS comments_post_id_idx
    ON comments(post_id, id);
`);

const upsertPost = db.prepare(`
  INSERT INTO posts (
    id, title, summary, body, category, region, tags_json,
    image_path, image_alt, author, source_ids_json, published_at,
    status, featured, updated_at
  ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
  ON CONFLICT(id) DO UPDATE SET
    title = excluded.title,
    summary = excluded.summary,
    body = excluded.body,
    category = excluded.category,
    region = excluded.region,
    tags_json = excluded.tags_json,
    image_path = excluded.image_path,
    image_alt = excluded.image_alt,
    author = excluded.author,
    source_ids_json = excluded.source_ids_json,
    published_at = excluded.published_at,
    status = excluded.status,
    featured = excluded.featured,
    updated_at = CURRENT_TIMESTAMP
`);

function log(message) {
  const line = `${new Date().toISOString()} ${message}\n`;
  process.stdout.write(line);
  try {
    fs.appendFileSync(LOG_FILE, line, "utf8");
  } catch (_) {
    // Logging must not stop the service.
  }
}

function normalizeList(value) {
  if (!Array.isArray(value)) return [];
  return [...new Set(value.map((item) => String(item).trim()).filter(Boolean))];
}

function normalizePost(input) {
  const id = String(input.id || "").trim();
  const title = String(input.title || "").trim();
  if (!/^[a-zA-Z0-9][a-zA-Z0-9_-]{2,79}$/.test(id)) {
    throw new Error(`Invalid post id: ${id || "(empty)"}`);
  }
  if (!title || title.length > 120) {
    throw new Error(`Invalid title for post: ${id}`);
  }
  const publishedAt = String(input.publishedAt || "").trim();
  if (!/^\d{4}-\d{2}-\d{2}(?:T[\d:.+-]+Z?)?$/.test(publishedAt)) {
    throw new Error(`Invalid publishedAt for post: ${id}`);
  }
  return {
    id,
    title,
    summary: String(input.summary || "").trim().slice(0, 500),
    body: String(input.body || "").trim().slice(0, 10000),
    category: String(input.category || "アイデア").trim().slice(0, 40),
    region: String(input.region || "グローバル").trim().slice(0, 40),
    tags: normalizeList(input.tags).slice(0, 20),
    image: String(input.image || "").trim().replaceAll("\\", "/").slice(0, 300),
    imageAlt: String(input.imageAlt || "").trim().slice(0, 240),
    author: String(input.author || "Interiorgram").trim().slice(0, 80),
    sourceIds: normalizeList(input.sourceIds).slice(0, 20),
    publishedAt,
    status: input.status === "draft" ? "draft" : "published",
    featured: input.featured ? 1 : 0,
  };
}

function importContent() {
  if (!fs.existsSync(CONTENT_FILE)) {
    log(`Content file not found: ${CONTENT_FILE}`);
    return;
  }
  const parsed = JSON.parse(fs.readFileSync(CONTENT_FILE, "utf8"));
  if (!Array.isArray(parsed)) {
    throw new Error("posts.json must contain a JSON array.");
  }
  db.exec("BEGIN IMMEDIATE");
  try {
    const importedIds = [];
    for (const item of parsed) {
      const post = normalizePost(item);
      importedIds.push(post.id);
      upsertPost.run(
        post.id,
        post.title,
        post.summary,
        post.body,
        post.category,
        post.region,
        JSON.stringify(post.tags),
        post.image,
        post.imageAlt,
        post.author,
        JSON.stringify(post.sourceIds),
        post.publishedAt,
        post.status,
        post.featured,
      );
    }
    if (importedIds.length) {
      const placeholders = importedIds.map(() => "?").join(", ");
      db.prepare(
        `UPDATE posts SET status = 'draft', updated_at = CURRENT_TIMESTAMP
         WHERE id NOT IN (${placeholders})`,
      ).run(...importedIds);
    } else {
      db.prepare(
        "UPDATE posts SET status = 'draft', updated_at = CURRENT_TIMESTAMP",
      ).run();
    }
    db.exec("COMMIT");
    log(`Imported ${parsed.length} content post(s).`);
  } catch (error) {
    db.exec("ROLLBACK");
    throw error;
  }
}

function safeJsonArray(value) {
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed : [];
  } catch (_) {
    return [];
  }
}

function postFromRow(row, clientId = "") {
  if (!row) return null;
  return {
    id: row.id,
    title: row.title,
    summary: row.summary,
    body: row.body,
    category: row.category,
    region: row.region,
    tags: safeJsonArray(row.tags_json),
    image: row.image_path,
    imageAlt: row.image_alt,
    author: row.author,
    sourceIds: safeJsonArray(row.source_ids_json),
    publishedAt: row.published_at,
    featured: Boolean(row.featured),
    likes: Number(row.likes || 0),
    comments: Number(row.comments || 0),
    views: Number(row.views || 0),
    liked: clientId
      ? Boolean(
          db
            .prepare("SELECT 1 AS found FROM likes WHERE post_id = ? AND client_id = ?")
            .get(row.id, clientId),
        )
      : false,
  };
}

const postSelect = `
  SELECT
    p.*,
    (SELECT COUNT(*) FROM likes l WHERE l.post_id = p.id) AS likes,
    (SELECT COUNT(*) FROM comments c WHERE c.post_id = p.id) AS comments,
    (SELECT COUNT(*) FROM views v WHERE v.post_id = p.id) AS views
  FROM posts p
`;

function listPosts(searchParams) {
  const q = String(searchParams.get("q") || "").trim().slice(0, 100);
  const category = String(searchParams.get("category") || "").trim().slice(0, 40);
  const region = String(searchParams.get("region") || "").trim().slice(0, 40);
  const tag = String(searchParams.get("tag") || "").trim().slice(0, 40);
  const clientId = normalizeClientId(searchParams.get("clientId"), false);
  const sort = searchParams.get("sort") === "popular" ? "popular" : "latest";
  const where = ["p.status = 'published'"];
  const params = [];

  if (q) {
    where.push(
      "(p.title LIKE ? OR p.summary LIKE ? OR p.body LIKE ? OR p.tags_json LIKE ?)",
    );
    const pattern = `%${q}%`;
    params.push(pattern, pattern, pattern, pattern);
  }
  if (category) {
    where.push("p.category = ?");
    params.push(category);
  }
  if (region) {
    where.push("p.region = ?");
    params.push(region);
  }
  if (tag) {
    where.push("p.tags_json LIKE ?");
    params.push(`%\"${tag}\"%`);
  }

  const order =
    sort === "popular"
      ? "likes DESC, comments DESC, p.published_at DESC"
      : "p.featured DESC, p.published_at DESC, p.id DESC";
  const sql = `${postSelect} WHERE ${where.join(" AND ")} ORDER BY ${order}`;
  return db
    .prepare(sql)
    .all(...params)
    .map((row) => postFromRow(row, clientId));
}

function getPost(postId, clientId = "") {
  const row = db
    .prepare(`${postSelect} WHERE p.id = ? AND p.status = 'published'`)
    .get(postId);
  return postFromRow(row, clientId);
}

function normalizeClientId(value, required = true) {
  const clientId = String(value || "").trim();
  if (!clientId && !required) return "";
  if (!/^[a-zA-Z0-9_-]{8,80}$/.test(clientId)) {
    throw new HttpError(400, "clientIdが不正です。");
  }
  return clientId;
}

class HttpError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

function commonHeaders(extra = {}) {
  return {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
    "X-Frame-Options": "SAMEORIGIN",
    ...extra,
  };
}

function send(response, status, body, contentType, extraHeaders = {}) {
  response.writeHead(status, {
    "Content-Type": contentType,
    ...commonHeaders(extraHeaders),
  });
  response.end(body);
}

function sendJson(response, status, value) {
  send(
    response,
    status,
    JSON.stringify(value),
    "application/json; charset=utf-8",
    { "Cache-Control": "no-store" },
  );
}

function readJson(request, maxBytes = 64 * 1024) {
  return new Promise((resolve, reject) => {
    let size = 0;
    const chunks = [];
    request.on("data", (chunk) => {
      size += chunk.length;
      if (size > maxBytes) {
        reject(new HttpError(413, "送信データが大きすぎます。"));
        request.destroy();
        return;
      }
      chunks.push(chunk);
    });
    request.on("end", () => {
      try {
        const text = Buffer.concat(chunks).toString("utf8");
        resolve(text ? JSON.parse(text) : {});
      } catch (_) {
        reject(new HttpError(400, "JSONが不正です。"));
      }
    });
    request.on("error", reject);
  });
}

function safeFile(root, relativePath) {
  const resolvedRoot = path.resolve(root);
  const resolvedFile = path.resolve(root, relativePath);
  if (
    resolvedFile !== resolvedRoot &&
    !resolvedFile.startsWith(`${resolvedRoot}${path.sep}`)
  ) {
    return null;
  }
  return resolvedFile;
}

function serveFile(response, root, relativePath, cacheControl) {
  const file = safeFile(root, relativePath);
  if (!file) {
    sendJson(response, 404, { error: "Not found" });
    return;
  }
  let stat;
  try {
    stat = fs.statSync(file);
  } catch (_) {
    sendJson(response, 404, { error: "Not found" });
    return;
  }
  if (!stat.isFile()) {
    sendJson(response, 404, { error: "Not found" });
    return;
  }
  const contentType =
    MIME_TYPES.get(path.extname(file).toLowerCase()) ||
    "application/octet-stream";
  response.writeHead(200, {
    "Content-Type": contentType,
    "Content-Length": stat.size,
    ...commonHeaders({ "Cache-Control": cacheControl }),
  });
  fs.createReadStream(file).pipe(response);
}

function requirePost(postId) {
  const found = db
    .prepare("SELECT 1 AS found FROM posts WHERE id = ? AND status = 'published'")
    .get(postId);
  if (!found) throw new HttpError(404, "投稿が見つかりません。");
}

async function handleApi(request, response, requestUrl) {
  if (request.method === "GET" && requestUrl.pathname === "/health") {
    const count = db
      .prepare("SELECT COUNT(*) AS count FROM posts WHERE status = 'published'")
      .get().count;
    sendJson(response, 200, {
      status: "ok",
      service: "interiorgram",
      posts: Number(count),
      time: new Date().toISOString(),
    });
    return true;
  }

  if (request.method === "GET" && requestUrl.pathname === "/api/meta") {
    const categories = db
      .prepare(
        "SELECT category, COUNT(*) AS count FROM posts WHERE status = 'published' GROUP BY category ORDER BY count DESC, category",
      )
      .all();
    const regions = db
      .prepare(
        "SELECT region, COUNT(*) AS count FROM posts WHERE status = 'published' GROUP BY region ORDER BY count DESC, region",
      )
      .all();
    const tags = new Map();
    for (const row of db
      .prepare("SELECT tags_json FROM posts WHERE status = 'published'")
      .all()) {
      for (const tag of safeJsonArray(row.tags_json)) {
        tags.set(tag, (tags.get(tag) || 0) + 1);
      }
    }
    sendJson(response, 200, {
      categories,
      regions,
      tags: [...tags.entries()]
        .map(([name, count]) => ({ name, count }))
        .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name, "ja")),
    });
    return true;
  }

  if (request.method === "GET" && requestUrl.pathname === "/api/posts") {
    sendJson(response, 200, { posts: listPosts(requestUrl.searchParams) });
    return true;
  }

  const postMatch = requestUrl.pathname.match(/^\/api\/posts\/([^/]+)$/);
  if (request.method === "GET" && postMatch) {
    const postId = decodeURIComponent(postMatch[1]);
    const clientId = normalizeClientId(
      requestUrl.searchParams.get("clientId"),
      false,
    );
    const post = getPost(postId, clientId);
    if (!post) throw new HttpError(404, "投稿が見つかりません。");
    sendJson(response, 200, { post });
    return true;
  }

  const likeMatch = requestUrl.pathname.match(
    /^\/api\/posts\/([^/]+)\/like$/,
  );
  if (request.method === "POST" && likeMatch) {
    const postId = decodeURIComponent(likeMatch[1]);
    requirePost(postId);
    const body = await readJson(request);
    const clientId = normalizeClientId(body.clientId);
    const existing = db
      .prepare("SELECT 1 AS found FROM likes WHERE post_id = ? AND client_id = ?")
      .get(postId, clientId);
    if (existing) {
      db.prepare("DELETE FROM likes WHERE post_id = ? AND client_id = ?").run(
        postId,
        clientId,
      );
    } else {
      db.prepare("INSERT INTO likes(post_id, client_id) VALUES (?, ?)").run(
        postId,
        clientId,
      );
    }
    const likes = db
      .prepare("SELECT COUNT(*) AS count FROM likes WHERE post_id = ?")
      .get(postId).count;
    sendJson(response, 200, { liked: !existing, likes: Number(likes) });
    return true;
  }

  const commentsMatch = requestUrl.pathname.match(
    /^\/api\/posts\/([^/]+)\/comments$/,
  );
  if (request.method === "GET" && commentsMatch) {
    const postId = decodeURIComponent(commentsMatch[1]);
    requirePost(postId);
    const comments = db
      .prepare(
        "SELECT id, user_name AS userName, comment_text AS text, created_at AS createdAt FROM comments WHERE post_id = ? ORDER BY id",
      )
      .all(postId);
    sendJson(response, 200, { comments });
    return true;
  }
  if (request.method === "POST" && commentsMatch) {
    const postId = decodeURIComponent(commentsMatch[1]);
    requirePost(postId);
    const body = await readJson(request);
    const clientId = normalizeClientId(body.clientId);
    const userName = String(body.userName || "Guest").trim().slice(0, 40);
    const text = String(body.text || "").trim();
    if (!text || text.length > 500) {
      throw new HttpError(400, "コメントは1～500文字で入力してください。");
    }
    const result = db
      .prepare(
        "INSERT INTO comments(post_id, client_id, user_name, comment_text) VALUES (?, ?, ?, ?)",
      )
      .run(postId, clientId, userName || "Guest", text);
    const comment = db
      .prepare(
        "SELECT id, user_name AS userName, comment_text AS text, created_at AS createdAt FROM comments WHERE id = ?",
      )
      .get(result.lastInsertRowid);
    sendJson(response, 201, { comment });
    return true;
  }

  const viewMatch = requestUrl.pathname.match(
    /^\/api\/posts\/([^/]+)\/view$/,
  );
  if (request.method === "POST" && viewMatch) {
    const postId = decodeURIComponent(viewMatch[1]);
    requirePost(postId);
    const body = await readJson(request);
    const clientId = normalizeClientId(body.clientId);
    const dateKey = new Date().toISOString().slice(0, 10);
    db.prepare(
      "INSERT OR IGNORE INTO views(post_id, client_id, date_key) VALUES (?, ?, ?)",
    ).run(postId, clientId, dateKey);
    const views = db
      .prepare("SELECT COUNT(*) AS count FROM views WHERE post_id = ?")
      .get(postId).count;
    sendJson(response, 200, { views: Number(views) });
    return true;
  }

  return false;
}

const server = http.createServer(async (request, response) => {
  try {
    const requestUrl = new URL(request.url, `http://${request.headers.host || "localhost"}`);
    if (await handleApi(request, response, requestUrl)) return;

    if (requestUrl.pathname.startsWith("/api/")) {
      sendJson(response, 404, { error: "API endpoint not found" });
      return;
    }

    if (request.method !== "GET" && request.method !== "HEAD") {
      sendJson(response, 405, { error: "Method not allowed" });
      return;
    }

    if (requestUrl.pathname.startsWith("/media/")) {
      serveFile(
        response,
        MEDIA_DIR,
        decodeURIComponent(requestUrl.pathname.slice("/media/".length)),
        "public, max-age=86400",
      );
      return;
    }

    const relativePath =
      requestUrl.pathname === "/"
        ? "index.html"
        : decodeURIComponent(requestUrl.pathname.replace(/^\/+/, ""));
    serveFile(
      response,
      PUBLIC_DIR,
      relativePath,
      relativePath === "index.html" ? "no-cache" : "public, max-age=3600",
    );
  } catch (error) {
    const status = error instanceof HttpError ? error.status : 500;
    if (status === 500) log(`ERROR ${error.stack || error.message}`);
    if (!response.headersSent) {
      sendJson(response, status, {
        error: status === 500 ? "サーバーでエラーが発生しました。" : error.message,
      });
    } else {
      response.end();
    }
  }
});

try {
  importContent();
} catch (error) {
  log(`Content import failed: ${error.stack || error.message}`);
  process.exit(1);
}

server.listen(PORT, HOST, () => {
  log(`Interiorgram listening on http://${HOST}:${PORT}`);
});

function shutdown(signal) {
  log(`Received ${signal}; shutting down.`);
  server.close(() => {
    db.close();
    process.exit(0);
  });
  setTimeout(() => process.exit(1), 5000).unref();
}

process.on("SIGINT", () => shutdown("SIGINT"));
process.on("SIGTERM", () => shutdown("SIGTERM"));
