"use strict";

const fs = require("fs");
const http = require("http");
const path = require("path");
const { DatabaseSync } = require("node:sqlite");

const ROOT = path.resolve(__dirname, "..");
const RELEASES_DIR = path.join(ROOT, "releases");
const ACTIVE_RELEASE_FILE = path.join(ROOT, "active-release.txt");
const DATA_DIR = path.join(ROOT, "data");
const DB_FILE = path.join(DATA_DIR, "dailynews.sqlite");
const LOG_FILE = path.join(ROOT, "logs", "server.log");
const HOST = process.env.DAILYNEWS_HOST || "202.15.67.132";
const PORT = Number(process.env.DAILYNEWS_PORT || 8082);
const ALLOWED_CLIENTS = (
  process.env.DAILYNEWS_ALLOWED_CLIENTS ||
  "127.0.0.1,::1,202.15.67.0/24,172.29.0.0/16"
)
  .split(",")
  .map((value) => value.trim())
  .filter(Boolean);
const TRUSTED_PROXIES = ["127.0.0.1", "::1", "202.15.67.132"];

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

fs.mkdirSync(DATA_DIR, { recursive: true });
const db = new DatabaseSync(DB_FILE);
db.exec(`
  PRAGMA journal_mode = WAL;
  PRAGMA synchronous = NORMAL;
  PRAGMA foreign_keys = ON;
  PRAGMA busy_timeout = 5000;

  CREATE TABLE IF NOT EXISTS interactions (
    item_id TEXT PRIMARY KEY,
    likes INTEGER NOT NULL DEFAULT 0 CHECK (likes >= 0),
    reads INTEGER NOT NULL DEFAULT 0 CHECK (reads >= 0),
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
  );

  CREATE TABLE IF NOT EXISTS client_likes (
    item_id TEXT NOT NULL,
    client_id TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (item_id, client_id),
    FOREIGN KEY (item_id) REFERENCES interactions(item_id) ON DELETE CASCADE
  );

  CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id TEXT NOT NULL,
    user_name TEXT NOT NULL DEFAULT 'Guest',
    comment_text TEXT NOT NULL,
    client_id TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (item_id) REFERENCES interactions(item_id) ON DELETE CASCADE
  );

  CREATE INDEX IF NOT EXISTS comments_item_id_idx
    ON comments(item_id, id);

  CREATE TABLE IF NOT EXISTS article_reads (
    item_id TEXT NOT NULL,
    client_id TEXT NOT NULL,
    date_key TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (item_id, client_id, date_key),
    FOREIGN KEY (item_id) REFERENCES interactions(item_id) ON DELETE CASCADE
  );

  CREATE TABLE IF NOT EXISTS access_daily (
    date_key TEXT PRIMARY KEY,
    visit_count INTEGER NOT NULL DEFAULT 0 CHECK (visit_count >= 0)
  );

  CREATE TABLE IF NOT EXISTS access_clients (
    client_id TEXT NOT NULL,
    date_key TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (client_id, date_key)
  );

  CREATE TABLE IF NOT EXISTS settings (
    setting_key TEXT PRIMARY KEY,
    setting_value TEXT NOT NULL
  );

  INSERT OR IGNORE INTO settings(setting_key, setting_value)
    VALUES ('total_visits', '0');
`);

const statements = {
  ensureInteraction: db.prepare(`
    INSERT OR IGNORE INTO interactions(item_id) VALUES (?)
  `),
  interaction: db.prepare(`
    SELECT
      i.item_id,
      i.likes,
      i.reads,
      COUNT(c.id) AS comments
    FROM interactions i
    LEFT JOIN comments c ON c.item_id = i.item_id
    WHERE i.item_id = ?
    GROUP BY i.item_id
  `),
  interactions: db.prepare(`
    SELECT
      i.item_id,
      i.likes,
      i.reads,
      COUNT(c.id) AS comments
    FROM interactions i
    LEFT JOIN comments c ON c.item_id = i.item_id
    GROUP BY i.item_id
  `),
  comments: db.prepare(`
    SELECT id, user_name, comment_text, client_id, created_at
    FROM comments
    WHERE item_id = ?
    ORDER BY id
  `),
  hasLike: db.prepare(`
    SELECT 1 AS found FROM client_likes WHERE item_id = ? AND client_id = ?
  `),
  insertLike: db.prepare(`
    INSERT OR IGNORE INTO client_likes(item_id, client_id) VALUES (?, ?)
  `),
  deleteLike: db.prepare(`
    DELETE FROM client_likes WHERE item_id = ? AND client_id = ?
  `),
  changeLikes: db.prepare(`
    UPDATE interactions
    SET likes = MAX(0, likes + ?), updated_at = CURRENT_TIMESTAMP
    WHERE item_id = ?
  `),
  insertComment: db.prepare(`
    INSERT INTO comments(item_id, user_name, comment_text, client_id)
    VALUES (?, ?, ?, ?)
  `),
  findComment: db.prepare(`
    SELECT id, item_id, client_id FROM comments WHERE id = ? AND item_id = ?
  `),
  deleteComment: db.prepare(`
    DELETE FROM comments WHERE id = ? AND item_id = ?
  `),
  insertRead: db.prepare(`
    INSERT OR IGNORE INTO article_reads(item_id, client_id, date_key)
    VALUES (?, ?, ?)
  `),
  incrementReads: db.prepare(`
    UPDATE interactions
    SET reads = reads + 1, updated_at = CURRENT_TIMESTAMP
    WHERE item_id = ?
  `),
  insertAccessClient: db.prepare(`
    INSERT OR IGNORE INTO access_clients(client_id, date_key) VALUES (?, ?)
  `),
  incrementAccessDay: db.prepare(`
    INSERT INTO access_daily(date_key, visit_count) VALUES (?, 1)
    ON CONFLICT(date_key) DO UPDATE SET visit_count = visit_count + 1
  `),
  incrementAccessTotal: db.prepare(`
    UPDATE settings
    SET setting_value = CAST(CAST(setting_value AS INTEGER) + 1 AS TEXT)
    WHERE setting_key = 'total_visits'
  `),
  accessDaily: db.prepare(`
    SELECT date_key, visit_count FROM access_daily ORDER BY date_key
  `),
  accessTotal: db.prepare(`
    SELECT CAST(setting_value AS INTEGER) AS total
    FROM settings WHERE setting_key = 'total_visits'
  `),
  todayAccess: db.prepare(`
    SELECT visit_count FROM access_daily WHERE date_key = ?
  `),
  resetAccessDay: db.prepare(`
    INSERT INTO access_daily(date_key, visit_count) VALUES (?, 0)
    ON CONFLICT(date_key) DO UPDATE SET visit_count = 0
  `),
  deleteAccessClients: db.prepare(`
    DELETE FROM access_clients WHERE date_key = ?
  `),
  changeAccessTotal: db.prepare(`
    UPDATE settings
    SET setting_value = CAST(MAX(0, CAST(setting_value AS INTEGER) - ?) AS TEXT)
    WHERE setting_key = 'total_visits'
  `),
};

function log(message) {
  const line = `${new Date().toISOString()} ${message}\n`;
  process.stdout.write(line);
  try {
    fs.mkdirSync(path.dirname(LOG_FILE), { recursive: true });
    fs.appendFileSync(LOG_FILE, line, "utf8");
  } catch (_) {
    // Serving must continue if file logging is temporarily unavailable.
  }
}

function normalizeAddress(address) {
  const normalized = String(address || "").trim().replace(/^::ffff:/, "");
  const bracketedIpv6 = normalized.match(/^\[([^\]]+)\](?::\d+)?$/);
  if (bracketedIpv6) return bracketedIpv6[1];
  const ipv4WithPort = normalized.match(/^(\d{1,3}(?:\.\d{1,3}){3}):\d+$/);
  return ipv4WithPort ? ipv4WithPort[1] : normalized;
}

function ipv4ToInt(address) {
  const parts = address.split(".");
  if (
    parts.length !== 4 ||
    parts.some((part) => !/^\d{1,3}$/.test(part) || Number(part) > 255)
  ) {
    return null;
  }
  return parts.reduce(
    (result, part) => ((result << 8) | Number(part)) >>> 0,
    0,
  );
}

function addressMatches(address, rule) {
  if (!rule.includes("/")) {
    return address.toLowerCase() === normalizeAddress(rule).toLowerCase();
  }
  const [network, bitsText] = rule.split("/");
  const bits = Number(bitsText);
  const addressInt = ipv4ToInt(address);
  const networkInt = ipv4ToInt(network);
  if (addressInt === null || networkInt === null || bits < 0 || bits > 32) {
    return false;
  }
  const mask = bits === 0 ? 0 : (0xffffffff << (32 - bits)) >>> 0;
  return (addressInt & mask) === (networkInt & mask);
}

function isAllowedClient(address) {
  const normalized = normalizeAddress(address);
  return ALLOWED_CLIENTS.some((rule) => addressMatches(normalized, rule));
}

function clientAddress(request) {
  const socketAddress = normalizeAddress(request.socket.remoteAddress);
  const trustedProxy = TRUSTED_PROXIES.some((rule) =>
    addressMatches(socketAddress, rule),
  );
  if (trustedProxy && request.headers["x-forwarded-for"]) {
    return normalizeAddress(
      String(request.headers["x-forwarded-for"]).split(",")[0].trim(),
    );
  }
  return socketAddress;
}

function activeRelease() {
  try {
    const releaseId = fs.readFileSync(ACTIVE_RELEASE_FILE, "utf8").trim();
    if (!/^[0-9a-f]{7,40}$/i.test(releaseId)) {
      return null;
    }
    const releaseDir = path.join(RELEASES_DIR, releaseId);
    return fs.statSync(releaseDir).isDirectory()
      ? { releaseId, releaseDir }
      : null;
  } catch (_) {
    return null;
  }
}

function commonHeaders(extraHeaders = {}) {
  return {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-Frame-Options": "SAMEORIGIN",
    ...extraHeaders,
  };
}

function send(response, status, body, contentType, extraHeaders = {}) {
  response.writeHead(status, {
    "Content-Type": contentType,
    ...commonHeaders(extraHeaders),
  });
  response.end(body);
}

function sendJson(response, status, value, extraHeaders = {}) {
  send(
    response,
    status,
    JSON.stringify(value),
    "application/json; charset=utf-8",
    {
      "Cache-Control": "no-store",
      ...extraHeaders,
    },
  );
}

function apiError(response, status, code, message) {
  sendJson(response, status, { error: { code, message } });
}

function jstDateKey() {
  const date = new Date(Date.now() + 9 * 60 * 60 * 1000);
  return [
    date.getUTCFullYear(),
    String(date.getUTCMonth() + 1).padStart(2, "0"),
    String(date.getUTCDate()).padStart(2, "0"),
  ].join("-");
}

function validItemId(value) {
  return typeof value === "string" && /^[A-Za-z0-9_-]{1,100}$/.test(value);
}

function validClientId(value) {
  return typeof value === "string" && /^[A-Za-z0-9_-]{16,100}$/.test(value);
}

function readJson(request, maxBytes = 16 * 1024) {
  return new Promise((resolve, reject) => {
    let body = "";
    request.setEncoding("utf8");
    request.on("data", (chunk) => {
      body += chunk;
      if (Buffer.byteLength(body, "utf8") > maxBytes) {
        reject(Object.assign(new Error("Request body is too large."), { status: 413 }));
        request.destroy();
      }
    });
    request.on("end", () => {
      try {
        resolve(body ? JSON.parse(body) : {});
      } catch (_) {
        reject(Object.assign(new Error("Invalid JSON body."), { status: 400 }));
      }
    });
    request.on("error", reject);
  });
}

function withTransaction(action) {
  db.exec("BEGIN IMMEDIATE");
  try {
    const result = action();
    db.exec("COMMIT");
    return result;
  } catch (error) {
    db.exec("ROLLBACK");
    throw error;
  }
}

function commentsFor(itemId, clientId) {
  return statements.comments.all(itemId).map((comment) => ({
    id: Number(comment.id),
    user: comment.user_name,
    text: comment.comment_text,
    date: new Date(
      String(comment.created_at).includes("T")
        ? comment.created_at
        : `${String(comment.created_at).replace(" ", "T")}Z`,
    ).toLocaleDateString("ja-JP", { timeZone: "Asia/Tokyo" }),
    canDelete: !comment.client_id || comment.client_id === clientId,
  }));
}

function interactionFor(itemId, clientId, includeComments = true) {
  statements.ensureInteraction.run(itemId);
  const row = statements.interaction.get(itemId);
  const value = {
    likes: Number(row?.likes || 0),
    comments: Number(row?.comments || 0),
    reads: Number(row?.reads || 0),
    liked: validClientId(clientId)
      ? Boolean(statements.hasLike.get(itemId, clientId))
      : false,
  };
  if (includeComments) {
    value.commentItems = commentsFor(itemId, clientId);
  }
  return value;
}

function allInteractions() {
  const result = {};
  for (const row of statements.interactions.all()) {
    result[row.item_id] = {
      likes: Number(row.likes || 0),
      comments: Number(row.comments || 0),
      reads: Number(row.reads || 0),
    };
  }
  return result;
}

function accessStats() {
  const daily = {};
  for (const row of statements.accessDaily.all()) {
    daily[row.date_key] = Number(row.visit_count || 0);
  }
  return {
    total: Number(statements.accessTotal.get()?.total || 0),
    daily,
  };
}

function assertSameOrigin(request, response) {
  const origin = request.headers.origin;
  if (!origin) return true;
  try {
    if (new URL(origin).host === request.headers.host) return true;
  } catch (_) {
    // Invalid origins are rejected below.
  }
  apiError(response, 403, "origin_rejected", "Cross-origin writes are not allowed.");
  return false;
}

async function handleApi(request, response, requestUrl) {
  const segments = requestUrl.pathname.split("/").filter(Boolean);

  if (request.method === "GET" && requestUrl.pathname === "/api/status") {
    sendJson(response, 200, {
      status: "ok",
      storage: "sqlite",
      time: new Date().toISOString(),
    });
    return;
  }

  if (request.method === "GET" && requestUrl.pathname === "/api/interactions") {
    sendJson(response, 200, { interactions: allInteractions() });
    return;
  }

  if (
    request.method === "GET" &&
    segments.length === 3 &&
    segments[0] === "api" &&
    segments[1] === "interactions"
  ) {
    const itemId = decodeURIComponent(segments[2]);
    if (!validItemId(itemId)) {
      apiError(response, 400, "invalid_item_id", "Invalid item ID.");
      return;
    }
    sendJson(
      response,
      200,
      interactionFor(itemId, requestUrl.searchParams.get("clientId")),
    );
    return;
  }

  if (request.method === "GET" && requestUrl.pathname === "/api/access") {
    sendJson(response, 200, accessStats());
    return;
  }

  if (!assertSameOrigin(request, response)) return;

  if (request.method === "POST" && requestUrl.pathname === "/api/access") {
    const body = await readJson(request);
    if (!validClientId(body.clientId)) {
      apiError(response, 400, "invalid_client_id", "Invalid client ID.");
      return;
    }
    const dateKey = jstDateKey();
    withTransaction(() => {
      const inserted = statements.insertAccessClient.run(body.clientId, dateKey);
      if (Number(inserted.changes) === 1) {
        statements.incrementAccessDay.run(dateKey);
        statements.incrementAccessTotal.run();
      }
    });
    sendJson(response, 200, accessStats());
    return;
  }

  if (
    request.method === "POST" &&
    requestUrl.pathname === "/api/access/reset-today"
  ) {
    const dateKey = jstDateKey();
    withTransaction(() => {
      const previous = Number(
        statements.todayAccess.get(dateKey)?.visit_count || 0,
      );
      statements.resetAccessDay.run(dateKey);
      statements.deleteAccessClients.run(dateKey);
      statements.changeAccessTotal.run(previous);
    });
    sendJson(response, 200, accessStats());
    return;
  }

  if (
    request.method === "PUT" &&
    segments.length === 4 &&
    segments[0] === "api" &&
    segments[1] === "interactions" &&
    segments[3] === "like"
  ) {
    const itemId = decodeURIComponent(segments[2]);
    const body = await readJson(request);
    if (!validItemId(itemId) || !validClientId(body.clientId)) {
      apiError(response, 400, "invalid_request", "Invalid item or client ID.");
      return;
    }
    const liked = Boolean(body.liked);
    withTransaction(() => {
      statements.ensureInteraction.run(itemId);
      const current = Boolean(statements.hasLike.get(itemId, body.clientId));
      if (liked && !current) {
        statements.insertLike.run(itemId, body.clientId);
        statements.changeLikes.run(1, itemId);
      } else if (!liked && current) {
        statements.deleteLike.run(itemId, body.clientId);
        statements.changeLikes.run(-1, itemId);
      }
    });
    sendJson(response, 200, interactionFor(itemId, body.clientId));
    return;
  }

  if (
    request.method === "POST" &&
    segments.length === 4 &&
    segments[0] === "api" &&
    segments[1] === "interactions" &&
    segments[3] === "comments"
  ) {
    const itemId = decodeURIComponent(segments[2]);
    const body = await readJson(request);
    const text = String(body.text || "").trim();
    const user = String(body.user || "Guest").trim().slice(0, 40) || "Guest";
    if (
      !validItemId(itemId) ||
      !validClientId(body.clientId) ||
      !text ||
      text.length > 500
    ) {
      apiError(response, 400, "invalid_comment", "Invalid comment.");
      return;
    }
    withTransaction(() => {
      statements.ensureInteraction.run(itemId);
      statements.insertComment.run(itemId, user, text, body.clientId);
    });
    sendJson(response, 201, interactionFor(itemId, body.clientId));
    return;
  }

  if (
    request.method === "DELETE" &&
    segments.length === 5 &&
    segments[0] === "api" &&
    segments[1] === "interactions" &&
    segments[3] === "comments"
  ) {
    const itemId = decodeURIComponent(segments[2]);
    const commentId = Number(segments[4]);
    const clientId = requestUrl.searchParams.get("clientId");
    if (
      !validItemId(itemId) ||
      !Number.isSafeInteger(commentId) ||
      !validClientId(clientId)
    ) {
      apiError(response, 400, "invalid_request", "Invalid delete request.");
      return;
    }
    const comment = statements.findComment.get(commentId, itemId);
    if (!comment) {
      apiError(response, 404, "comment_not_found", "Comment was not found.");
      return;
    }
    if (comment.client_id && comment.client_id !== clientId) {
      apiError(response, 403, "comment_owner_required", "Only the author can delete this comment.");
      return;
    }
    statements.deleteComment.run(commentId, itemId);
    sendJson(response, 200, interactionFor(itemId, clientId));
    return;
  }

  if (
    request.method === "POST" &&
    segments.length === 4 &&
    segments[0] === "api" &&
    segments[1] === "interactions" &&
    segments[3] === "read"
  ) {
    const itemId = decodeURIComponent(segments[2]);
    const body = await readJson(request);
    if (!validItemId(itemId) || !validClientId(body.clientId)) {
      apiError(response, 400, "invalid_request", "Invalid item or client ID.");
      return;
    }
    withTransaction(() => {
      statements.ensureInteraction.run(itemId);
      const inserted = statements.insertRead.run(
        itemId,
        body.clientId,
        jstDateKey(),
      );
      if (Number(inserted.changes) === 1) {
        statements.incrementReads.run(itemId);
      }
    });
    sendJson(response, 200, interactionFor(itemId, body.clientId, false));
    return;
  }

  apiError(response, 404, "api_not_found", "API endpoint was not found.");
}

function serveFile(request, response, releaseDir, pathname) {
  let decodedPath;
  try {
    decodedPath = decodeURIComponent(pathname);
  } catch (_) {
    send(response, 400, "Bad Request", "text/plain; charset=utf-8");
    return;
  }

  const relativePath =
    decodedPath === "/" ? "index.html" : decodedPath.replace(/^\/+/, "");
  const filePath = path.resolve(releaseDir, relativePath);
  const releasePrefix = `${path.resolve(releaseDir)}${path.sep}`;

  if (!filePath.startsWith(releasePrefix)) {
    send(response, 403, "Forbidden", "text/plain; charset=utf-8");
    return;
  }

  let stat;
  try {
    stat = fs.lstatSync(filePath);
  } catch (_) {
    send(response, 404, "Not Found", "text/plain; charset=utf-8");
    return;
  }

  if (!stat.isFile() || stat.isSymbolicLink()) {
    send(response, 404, "Not Found", "text/plain; charset=utf-8");
    return;
  }

  const extension = path.extname(filePath).toLowerCase();
  const contentType = MIME_TYPES.get(extension);
  if (!contentType) {
    send(response, 403, "Forbidden", "text/plain; charset=utf-8");
    return;
  }

  const cacheControl =
    extension === ".html" || extension === ".js" || extension === ".json"
      ? "no-cache"
      : "public, max-age=86400";

  response.writeHead(200, {
    "Content-Type": contentType,
    "Content-Length": stat.size,
    "Cache-Control": cacheControl,
    ...commonHeaders(),
  });

  if (request.method === "HEAD") {
    response.end();
    return;
  }

  const stream = fs.createReadStream(filePath);
  stream.on("error", (error) => {
    log(`Read error for ${relativePath}: ${error.message}`);
    response.destroy(error);
  });
  stream.pipe(response);
}

const server = http.createServer(async (request, response) => {
  const client = clientAddress(request);
  if (!isAllowedClient(client)) {
    log(`Rejected client ${client}`);
    send(
      response,
      403,
      "Access is limited to approved clients.",
      "text/plain; charset=utf-8",
    );
    return;
  }

  const requestUrl = new URL(
    request.url,
    `http://${request.headers.host || "localhost"}`,
  );
  const release = activeRelease();

  if (requestUrl.pathname === "/health") {
    const body = {
      status: release ? "ok" : "not_ready",
      release: release?.releaseId || null,
      storage: "sqlite",
      port: PORT,
      time: new Date().toISOString(),
    };
    sendJson(response, release ? 200 : 503, request.method === "HEAD" ? {} : body);
    return;
  }

  if (requestUrl.pathname.startsWith("/api/")) {
    try {
      await handleApi(request, response, requestUrl);
    } catch (error) {
      log(`API error ${request.method} ${requestUrl.pathname}: ${error.stack || error.message}`);
      if (!response.headersSent) {
        apiError(
          response,
          Number(error.status) || 500,
          "server_error",
          Number(error.status) < 500 ? error.message : "Internal server error.",
        );
      } else {
        response.end();
      }
    }
    return;
  }

  if (request.method !== "GET" && request.method !== "HEAD") {
    send(response, 405, "Method Not Allowed", "text/plain; charset=utf-8", {
      Allow: "GET, HEAD",
    });
    return;
  }

  if (!release) {
    send(
      response,
      503,
      "DailyNews has no active release.",
      "text/plain; charset=utf-8",
    );
    return;
  }

  serveFile(request, response, release.releaseDir, requestUrl.pathname);
});

server.on("error", (error) => {
  log(`Server error: ${error.stack || error.message}`);
  process.exitCode = 1;
});

server.listen(PORT, HOST, () => {
  log(`DailyNews listening on http://${HOST}:${PORT}`);
});

function shutdown(signal) {
  log(`Received ${signal}; shutting down`);
  server.close(() => {
    db.close();
    process.exit(0);
  });
  setTimeout(() => process.exit(1), 5000).unref();
}

process.on("SIGINT", () => shutdown("SIGINT"));
process.on("SIGTERM", () => shutdown("SIGTERM"));
