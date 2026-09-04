"use strict";

const fs = require("fs");
const http = require("http");
const path = require("path");
const crypto = require("crypto");
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
const SESSION_COOKIE = "dailynews_session";
const SESSION_MAX_AGE_SECONDS = 180 * 24 * 60 * 60;
const AUTH_ATTEMPT_WINDOW_MS = 10 * 60 * 1000;
const AUTH_ATTEMPT_LIMIT = 12;
const authAttempts = new Map();
const ADMIN_EMAILS = new Set(
  (process.env.DAILYNEWS_ADMIN_EMAILS || "yuki.nakamura@toyoda-gosei.co.jp")
    .split(",")
    .map((value) => value.trim().toLowerCase())
    .filter(Boolean),
);

const MIME_TYPES = new Map([
  [".cer", "application/pkix-cert"],
  [".css", "text/css; charset=utf-8"],
  [".gif", "image/gif"],
  [".html", "text/html; charset=utf-8"],
  [".ico", "image/x-icon"],
  [".jpeg", "image/jpeg"],
  [".jpg", "image/jpeg"],
  [".js", "text/javascript; charset=utf-8"],
  [".json", "application/json; charset=utf-8"],
  [".png", "image/png"],
  [".ps1", "text/plain; charset=utf-8"],
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

  CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    password_salt TEXT NOT NULL,
    email_verified INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
  );

  CREATE TABLE IF NOT EXISTS mail_subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    display_name TEXT,
    user_id INTEGER UNIQUE,
    enabled INTEGER NOT NULL DEFAULT 1,
    source TEXT NOT NULL DEFAULT 'manual'
      CHECK (source IN ('manual', 'registered_user')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
  );

  CREATE INDEX IF NOT EXISTS mail_subscriptions_enabled_idx
    ON mail_subscriptions(enabled, email);

  CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
  );

  CREATE INDEX IF NOT EXISTS sessions_user_id_idx
    ON sessions(user_id, expires_at);

  CREATE TABLE IF NOT EXISTS user_likes (
    item_id TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (item_id, user_id),
    FOREIGN KEY (item_id) REFERENCES interactions(item_id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
  );

  CREATE TABLE IF NOT EXISTS user_irrelevant (
    item_id TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (item_id, user_id),
    FOREIGN KEY (item_id) REFERENCES interactions(item_id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
  );

  CREATE TABLE IF NOT EXISTS user_favorites (
    item_id TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (item_id, user_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
  );

  CREATE TABLE IF NOT EXISTS comment_likes (
    comment_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (comment_id, user_id),
    FOREIGN KEY (comment_id) REFERENCES comments(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
  );

  CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    category TEXT NOT NULL,
    message TEXT NOT NULL,
    item_id TEXT,
    page_url TEXT,
    status TEXT NOT NULL DEFAULT 'new',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
  );

  CREATE INDEX IF NOT EXISTS feedback_user_id_idx
    ON feedback(user_id, id DESC);
`);

function ensureColumn(tableName, columnName, definition) {
  const columns = db.prepare(`PRAGMA table_info(${tableName})`).all();
  if (!columns.some((column) => column.name === columnName)) {
    db.exec(`ALTER TABLE ${tableName} ADD COLUMN ${columnName} ${definition}`);
  }
}

ensureColumn("comments", "user_id", "INTEGER REFERENCES users(id)");
ensureColumn("comments", "parent_comment_id", "INTEGER REFERENCES comments(id)");
ensureColumn("users", "is_admin", "INTEGER NOT NULL DEFAULT 0");
db.exec(`
  CREATE INDEX IF NOT EXISTS comments_user_id_idx
    ON comments(user_id, id DESC);
  CREATE INDEX IF NOT EXISTS comments_parent_id_idx
    ON comments(parent_comment_id, id);

  CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    actor_user_id INTEGER,
    notification_type TEXT NOT NULL,
    item_id TEXT NOT NULL,
    comment_id INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    read_at TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (actor_user_id) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY (comment_id) REFERENCES comments(id) ON DELETE CASCADE
  );

  CREATE INDEX IF NOT EXISTS notifications_user_idx
    ON notifications(user_id, read_at, id DESC);
  CREATE INDEX IF NOT EXISTS notifications_comment_idx
    ON notifications(comment_id, notification_type, actor_user_id);
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
    SELECT id, user_name, comment_text, client_id, user_id, parent_comment_id, created_at
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
  clientLikes: db.prepare(`
    SELECT item_id FROM client_likes WHERE client_id = ?
  `),
  hasUserLike: db.prepare(`
    SELECT 1 AS found FROM user_likes WHERE item_id = ? AND user_id = ?
  `),
  likeUsers: db.prepare(`
    SELECT u.display_name
    FROM user_likes l
    JOIN users u ON u.id = l.user_id
    WHERE l.item_id = ?
    ORDER BY l.created_at, u.id
  `),
  allLikeUsers: db.prepare(`
    SELECT l.item_id, u.display_name
    FROM user_likes l
    JOIN users u ON u.id = l.user_id
    ORDER BY l.item_id, l.created_at, u.id
  `),
  insertUserLike: db.prepare(`
    INSERT OR IGNORE INTO user_likes(item_id, user_id) VALUES (?, ?)
  `),
  deleteUserLike: db.prepare(`
    DELETE FROM user_likes WHERE item_id = ? AND user_id = ?
  `),
  hasUserIrrelevant: db.prepare(`
    SELECT 1 AS found FROM user_irrelevant WHERE item_id = ? AND user_id = ?
  `),
  insertUserIrrelevant: db.prepare(`
    INSERT OR IGNORE INTO user_irrelevant(item_id, user_id) VALUES (?, ?)
  `),
  deleteUserIrrelevant: db.prepare(`
    DELETE FROM user_irrelevant WHERE item_id = ? AND user_id = ?
  `),
  irrelevantCount: db.prepare(`
    SELECT COUNT(*) AS count FROM user_irrelevant WHERE item_id = ?
  `),
  allIrrelevantCounts: db.prepare(`
    SELECT item_id, COUNT(*) AS count FROM user_irrelevant GROUP BY item_id
  `),
  changeLikes: db.prepare(`
    UPDATE interactions
    SET likes = MAX(0, likes + ?), updated_at = CURRENT_TIMESTAMP
    WHERE item_id = ?
  `),
  insertComment: db.prepare(`
    INSERT INTO comments(item_id, user_name, comment_text, client_id, user_id, parent_comment_id)
    VALUES (?, ?, ?, ?, ?, ?)
  `),
  findComment: db.prepare(`
    SELECT id, item_id, user_name, comment_text, client_id, user_id, parent_comment_id
    FROM comments WHERE id = ? AND item_id = ?
  `),
  deleteComment: db.prepare(`
    DELETE FROM comments WHERE id = ? AND item_id = ?
  `),
  detachCommentReplies: db.prepare(`
    UPDATE comments SET parent_comment_id = NULL WHERE parent_comment_id = ?
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
  userByEmail: db.prepare(`
    SELECT id, email, display_name, password_hash, password_salt, email_verified, is_admin
    FROM users WHERE email = ?
  `),
  userById: db.prepare(`
    SELECT id, email, display_name, email_verified, is_admin
    FROM users WHERE id = ?
  `),
  mentionableUsers: db.prepare(`
    SELECT id, display_name FROM users ORDER BY id
  `),
  insertUser: db.prepare(`
    INSERT INTO users(email, display_name, password_hash, password_salt)
    VALUES (?, ?, ?, ?)
  `),
  subscribeRegisteredUser: db.prepare(`
    INSERT INTO mail_subscriptions(email, display_name, user_id, source)
    VALUES (?, ?, ?, 'registered_user')
    ON CONFLICT(email) DO UPDATE SET
      display_name = excluded.display_name,
      user_id = excluded.user_id,
      source = 'registered_user',
      updated_at = CURRENT_TIMESTAMP
  `),
  usersForMailSeed: db.prepare(`
    SELECT id, email, display_name FROM users ORDER BY id
  `),
  updateUserName: db.prepare(`
    UPDATE users
    SET display_name = ?, updated_at = CURRENT_TIMESTAMP
    WHERE id = ?
  `),
  updateCommentNames: db.prepare(`
    UPDATE comments SET user_name = ? WHERE user_id = ?
  `),
  insertSession: db.prepare(`
    INSERT INTO sessions(token_hash, user_id, expires_at)
    VALUES (?, ?, ?)
  `),
  sessionUser: db.prepare(`
    SELECT u.id, u.email, u.display_name, u.email_verified, u.is_admin, s.expires_at
    FROM sessions s
    JOIN users u ON u.id = s.user_id
    WHERE s.token_hash = ? AND s.expires_at > ?
  `),
  touchSession: db.prepare(`
    UPDATE sessions SET last_seen_at = CURRENT_TIMESTAMP WHERE token_hash = ?
  `),
  deleteSession: db.prepare(`
    DELETE FROM sessions WHERE token_hash = ?
  `),
  deleteExpiredSessions: db.prepare(`
    DELETE FROM sessions WHERE expires_at <= ?
  `),
  insertFavorite: db.prepare(`
    INSERT OR IGNORE INTO user_favorites(item_id, user_id) VALUES (?, ?)
  `),
  deleteFavorite: db.prepare(`
    DELETE FROM user_favorites WHERE item_id = ? AND user_id = ?
  `),
  userFavorites: db.prepare(`
    SELECT item_id FROM user_favorites WHERE user_id = ? ORDER BY created_at DESC
  `),
  userLikes: db.prepare(`
    SELECT item_id FROM user_likes WHERE user_id = ? ORDER BY created_at DESC
  `),
  userIrrelevant: db.prepare(`
    SELECT item_id FROM user_irrelevant WHERE user_id = ? ORDER BY created_at DESC
  `),
  userComments: db.prepare(`
    SELECT id, item_id, comment_text, created_at
    FROM comments WHERE user_id = ? ORDER BY id DESC
  `),
  claimComments: db.prepare(`
    UPDATE comments
    SET user_id = ?, user_name = ?
    WHERE client_id = ? AND user_id IS NULL
  `),
  commentLikeCount: db.prepare(`
    SELECT COUNT(*) AS count FROM comment_likes WHERE comment_id = ?
  `),
  hasCommentLike: db.prepare(`
    SELECT 1 AS found FROM comment_likes WHERE comment_id = ? AND user_id = ?
  `),
  insertCommentLike: db.prepare(`
    INSERT OR IGNORE INTO comment_likes(comment_id, user_id) VALUES (?, ?)
  `),
  deleteCommentLike: db.prepare(`
    DELETE FROM comment_likes WHERE comment_id = ? AND user_id = ?
  `),
  participantUsers: db.prepare(`
    SELECT user_id FROM comments WHERE item_id = ? AND user_id IS NOT NULL
    UNION SELECT user_id FROM user_favorites WHERE item_id = ?
    UNION SELECT user_id FROM user_likes WHERE item_id = ?
  `),
  insertNotification: db.prepare(`
    INSERT INTO notifications(user_id, actor_user_id, notification_type, item_id, comment_id)
    VALUES (?, ?, ?, ?, ?)
  `),
  deleteCommentLikeNotification: db.prepare(`
    DELETE FROM notifications
    WHERE notification_type = 'comment_like' AND comment_id = ? AND actor_user_id = ?
  `),
  notifications: db.prepare(`
    SELECT
      n.id,
      n.notification_type,
      n.item_id,
      n.comment_id,
      n.created_at,
      n.read_at,
      actor.display_name AS actor_name,
      c.comment_text
    FROM notifications n
    LEFT JOIN users actor ON actor.id = n.actor_user_id
    LEFT JOIN comments c ON c.id = n.comment_id
    WHERE n.user_id = ?
    ORDER BY n.id DESC
    LIMIT ?
  `),
  unreadNotificationCount: db.prepare(`
    SELECT COUNT(*) AS count FROM notifications WHERE user_id = ? AND read_at IS NULL
  `),
  markNotificationRead: db.prepare(`
    UPDATE notifications SET read_at = COALESCE(read_at, CURRENT_TIMESTAMP)
    WHERE id = ? AND user_id = ?
  `),
  markAllNotificationsRead: db.prepare(`
    UPDATE notifications SET read_at = COALESCE(read_at, CURRENT_TIMESTAMP)
    WHERE user_id = ?
  `),
  recentActivity: db.prepare(`
    SELECT
      c.id,
      c.item_id,
      c.comment_text,
      c.parent_comment_id,
      c.created_at,
      u.display_name,
      (SELECT COUNT(*) FROM comments all_comments WHERE all_comments.item_id = c.item_id) AS comment_count,
      (SELECT likes FROM interactions i WHERE i.item_id = c.item_id) AS like_count
    FROM comments c
    JOIN users u ON u.id = c.user_id
    ORDER BY c.id DESC
    LIMIT ?
  `),
  userParticipation: db.prepare(`
    SELECT item_id, MAX(activity_at) AS activity_at
    FROM (
      SELECT item_id, created_at AS activity_at FROM comments WHERE user_id = ?
      UNION ALL
      SELECT item_id, created_at AS activity_at FROM user_likes WHERE user_id = ?
      UNION ALL
      SELECT item_id, created_at AS activity_at FROM user_favorites WHERE user_id = ?
    )
    GROUP BY item_id
    ORDER BY activity_at DESC
    LIMIT 200
  `),
  insertFeedback: db.prepare(`
    INSERT INTO feedback(user_id, category, message, item_id, page_url)
    VALUES (?, ?, ?, ?, ?)
  `),
  userFeedback: db.prepare(`
    SELECT id, category, message, item_id, page_url, status, created_at
    FROM feedback WHERE user_id = ? ORDER BY id DESC LIMIT 100
  `),
  markAdmin: db.prepare(`
    UPDATE users SET is_admin = 1 WHERE email = ?
  `),
  adminUsers: db.prepare(`
    SELECT
      u.id,
      u.email,
      u.display_name,
      u.is_admin,
      u.created_at,
      u.updated_at,
      MAX(s.last_seen_at) AS last_seen_at,
      (SELECT COUNT(*) FROM user_favorites f WHERE f.user_id = u.id) AS favorites,
      (SELECT COUNT(*) FROM user_likes l WHERE l.user_id = u.id) AS likes,
      (SELECT COUNT(*) FROM user_irrelevant r WHERE r.user_id = u.id) AS irrelevant,
      (SELECT COUNT(*) FROM comments c WHERE c.user_id = u.id) AS comments,
      (SELECT COUNT(*) FROM feedback fb WHERE fb.user_id = u.id) AS feedback
    FROM users u
    LEFT JOIN sessions s ON s.user_id = u.id
    GROUP BY u.id
    ORDER BY u.created_at DESC
  `),
  adminFeedback: db.prepare(`
    SELECT
      f.id,
      f.category,
      f.message,
      f.item_id,
      f.page_url,
      f.status,
      f.created_at,
      u.display_name,
      u.email
    FROM feedback f
    JOIN users u ON u.id = f.user_id
    ORDER BY f.id DESC
    LIMIT 100
  `),
  mailingList: db.prepare(`
    SELECT id, email, display_name, user_id, enabled, source, created_at, updated_at
    FROM mail_subscriptions
    ORDER BY enabled DESC, source DESC, email
  `),
  activeMailingList: db.prepare(`
    SELECT email, display_name, source
    FROM mail_subscriptions
    WHERE enabled = 1
    ORDER BY email
  `),
  mailingSubscriptionByEmail: db.prepare(`
    SELECT id FROM mail_subscriptions WHERE email = ?
  `),
  insertManualMailSubscription: db.prepare(`
    INSERT INTO mail_subscriptions(email, display_name, source)
    VALUES (?, ?, 'manual')
  `),
  setMailSubscriptionEnabled: db.prepare(`
    UPDATE mail_subscriptions
    SET enabled = ?, updated_at = CURRENT_TIMESTAMP
    WHERE id = ?
  `),
  deleteManualMailSubscription: db.prepare(`
    DELETE FROM mail_subscriptions
    WHERE id = ? AND source = 'manual' AND user_id IS NULL
  `),
};

for (const email of ADMIN_EMAILS) statements.markAdmin.run(email);
for (const user of statements.usersForMailSeed.all()) {
  statements.subscribeRegisteredUser.run(user.email, user.display_name, user.id);
}

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

function normalizeEmail(value) {
  return String(value || "").trim().toLowerCase();
}

function validEmail(value) {
  return (
    value.length >= 5 &&
    value.length <= 254 &&
    /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)
  );
}

function validDisplayName(value) {
  return (
    typeof value === "string" &&
    value.trim().length >= 1 &&
    value.trim().length <= 40 &&
    !/[\u0000-\u001f\u007f]/.test(value)
  );
}

function mailingListPayload() {
  const recipients = statements.mailingList.all().map((row) => ({
    id: Number(row.id),
    email: row.email,
    displayName: row.display_name || "",
    userId: row.user_id == null ? null : Number(row.user_id),
    enabled: Boolean(row.enabled),
    source: row.source,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
  }));
  return {
    activeCount: recipients.filter((recipient) => recipient.enabled).length,
    recipients,
  };
}

function validPassword(value) {
  return typeof value === "string" && value.length >= 8 && value.length <= 128;
}

function hashPassword(password, salt = crypto.randomBytes(16).toString("base64")) {
  return {
    salt,
    hash: crypto.scryptSync(password, salt, 64).toString("base64"),
  };
}

function verifyPassword(password, salt, expectedHash) {
  try {
    const actual = Buffer.from(hashPassword(password, salt).hash, "base64");
    const expected = Buffer.from(expectedHash, "base64");
    return actual.length === expected.length && crypto.timingSafeEqual(actual, expected);
  } catch (_) {
    return false;
  }
}

function tokenHash(token) {
  return crypto.createHash("sha256").update(token).digest("hex");
}

function parseCookies(request) {
  const result = {};
  for (const part of String(request.headers.cookie || "").split(";")) {
    const separator = part.indexOf("=");
    if (separator < 1) continue;
    const name = part.slice(0, separator).trim();
    const value = part.slice(separator + 1).trim();
    try {
      result[name] = decodeURIComponent(value);
    } catch (_) {
      result[name] = value;
    }
  }
  return result;
}

function requestUsesHttps(request) {
  return (
    request.socket.encrypted ||
    String(request.headers["x-forwarded-proto"] || "").toLowerCase() === "https" ||
    Boolean(request.headers["x-arr-ssl"])
  );
}

function sessionCookie(token, request, maxAge = SESSION_MAX_AGE_SECONDS) {
  const attributes = [
    `${SESSION_COOKIE}=${encodeURIComponent(token)}`,
    "Path=/",
    "HttpOnly",
    "SameSite=Lax",
    `Max-Age=${maxAge}`,
  ];
  if (requestUsesHttps(request)) attributes.push("Secure");
  return attributes.join("; ");
}

function publicUser(row) {
  return {
    id: Number(row.id),
    email: row.email,
    displayName: row.display_name,
    emailVerified: Boolean(row.email_verified),
    isAdmin: Boolean(row.is_admin),
  };
}

function authenticatedUser(request) {
  if (request.authChecked) return request.authUser || null;
  request.authChecked = true;
  const token = parseCookies(request)[SESSION_COOKIE];
  if (!token || token.length > 256) return null;
  const hash = tokenHash(token);
  const row = statements.sessionUser.get(hash, new Date().toISOString());
  if (!row) return null;
  statements.touchSession.run(hash);
  request.authTokenHash = hash;
  request.authUser = publicUser(row);
  return request.authUser;
}

function requireUser(request, response) {
  const user = authenticatedUser(request);
  if (!user) {
    apiError(response, 401, "authentication_required", "Login is required.");
    return null;
  }
  return user;
}

function requireAdmin(request, response) {
  const user = requireUser(request, response);
  if (!user) return null;
  if (!user.isAdmin) {
    apiError(response, 403, "administrator_required", "Administrator access is required.");
    return null;
  }
  return user;
}

function createSession(userId, request, response) {
  const token = crypto.randomBytes(32).toString("base64url");
  const expiresAt = new Date(
    Date.now() + SESSION_MAX_AGE_SECONDS * 1000,
  ).toISOString();
  statements.deleteExpiredSessions.run(new Date().toISOString());
  statements.insertSession.run(tokenHash(token), userId, expiresAt);
  response.setHeader("Set-Cookie", sessionCookie(token, request));
}

function authRateLimited(request, action) {
  const key = `${action}:${clientAddress(request)}`;
  const now = Date.now();
  const previous = authAttempts.get(key) || [];
  const recent = previous.filter((timestamp) => now - timestamp < AUTH_ATTEMPT_WINDOW_MS);
  recent.push(now);
  authAttempts.set(key, recent);
  return recent.length > AUTH_ATTEMPT_LIMIT;
}

function claimClientActivity(user, clientId, favoriteIds = []) {
  if (!validClientId(clientId)) return;
  withTransaction(() => {
    for (const row of statements.clientLikes.all(clientId)) {
      statements.ensureInteraction.run(row.item_id);
      const alreadyLiked = Boolean(
        statements.hasUserLike.get(row.item_id, user.id),
      );
      if (alreadyLiked) statements.changeLikes.run(-1, row.item_id);
      else statements.insertUserLike.run(row.item_id, user.id);
      statements.deleteLike.run(row.item_id, clientId);
    }
    statements.claimComments.run(user.id, user.displayName, clientId);
    for (const itemId of favoriteIds) {
      if (validItemId(itemId)) statements.insertFavorite.run(itemId, user.id);
    }
  });
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

function commentsFor(itemId, clientId, user = null) {
  return statements.comments.all(itemId).map((comment) => ({
    id: Number(comment.id),
    parentId: comment.parent_comment_id ? Number(comment.parent_comment_id) : null,
    user: comment.user_name,
    text: comment.comment_text,
    createdAt: comment.created_at,
    date: new Date(
      String(comment.created_at).includes("T")
        ? comment.created_at
        : `${String(comment.created_at).replace(" ", "T")}Z`,
    ).toLocaleDateString("ja-JP", { timeZone: "Asia/Tokyo" }),
    likes: Number(statements.commentLikeCount.get(comment.id)?.count || 0),
    liked: Boolean(
      user && statements.hasCommentLike.get(comment.id, user.id),
    ),
    canDelete: user
      ? Number(comment.user_id) === user.id
      : !comment.user_id && (!comment.client_id || comment.client_id === clientId),
  }));
}

function notificationPayload(userId, limit = 30) {
  const safeLimit = Math.max(1, Math.min(100, Number(limit) || 30));
  return {
    unreadCount: Number(
      statements.unreadNotificationCount.get(userId)?.count || 0,
    ),
    notifications: statements.notifications.all(userId, safeLimit).map((row) => ({
      id: Number(row.id),
      type: row.notification_type,
      itemId: row.item_id,
      commentId: row.comment_id ? Number(row.comment_id) : null,
      actorName: row.actor_name || "ユーザー",
      text: row.comment_text || "",
      createdAt: row.created_at,
      read: Boolean(row.read_at),
    })),
  };
}

function mentionedUserIds(text, actorId) {
  const body = String(text || "");
  return statements.mentionableUsers
    .all()
    .filter((row) => Number(row.id) !== actorId)
    .filter((row) => body.includes(`@${row.display_name}`))
    .map((row) => Number(row.id));
}

function notifyCommentParticipants(
  itemId,
  commentId,
  actor,
  parentComment,
  mentionUserIds = [],
) {
  const recipients = new Set(
    statements.participantUsers
      .all(itemId, itemId, itemId)
      .map((row) => Number(row.user_id))
      .filter((userId) => userId && userId !== actor.id),
  );
  const notified = new Set();

  const parentUserId = Number(parentComment?.user_id || 0);
  if (parentUserId && parentUserId !== actor.id) {
    statements.insertNotification.run(
      parentUserId,
      actor.id,
      "comment_reply",
      itemId,
      commentId,
    );
    notified.add(parentUserId);
    recipients.delete(parentUserId);
  }

  for (const userId of new Set(mentionUserIds)) {
    if (!userId || userId === actor.id || notified.has(userId)) continue;
    statements.insertNotification.run(
      userId,
      actor.id,
      "mention",
      itemId,
      commentId,
    );
    notified.add(userId);
    recipients.delete(userId);
  }

  for (const userId of recipients) {
    if (notified.has(userId)) continue;
    statements.insertNotification.run(
      userId,
      actor.id,
      "article_comment",
      itemId,
      commentId,
    );
  }
}

function interactionFor(itemId, clientId, includeComments = true, user = null) {
  statements.ensureInteraction.run(itemId);
  const row = statements.interaction.get(itemId);
  const value = {
    likes: Number(row?.likes || 0),
    comments: Number(row?.comments || 0),
    reads: Number(row?.reads || 0),
    liked: user
      ? Boolean(statements.hasUserLike.get(itemId, user.id))
      : validClientId(clientId)
        ? Boolean(statements.hasLike.get(itemId, clientId))
        : false,
    likedBy: statements.likeUsers.all(itemId).map((row) => row.display_name),
    irrelevant: Number(statements.irrelevantCount.get(itemId)?.count || 0),
    markedIrrelevant: Boolean(
      user && statements.hasUserIrrelevant.get(itemId, user.id),
    ),
  };
  if (includeComments) {
    value.commentItems = commentsFor(itemId, clientId, user);
  }
  return value;
}

function allInteractions(user = null) {
  const result = {};
  for (const row of statements.interactions.all()) {
    result[row.item_id] = {
      likes: Number(row.likes || 0),
      comments: Number(row.comments || 0),
      reads: Number(row.reads || 0),
      likedBy: [],
      irrelevant: 0,
      markedIrrelevant: false,
    };
  }
  for (const row of statements.allLikeUsers.all()) {
    if (result[row.item_id]) result[row.item_id].likedBy.push(row.display_name);
  }
  for (const row of statements.allIrrelevantCounts.all()) {
    if (result[row.item_id]) result[row.item_id].irrelevant = Number(row.count || 0);
  }
  if (user) {
    for (const row of statements.userIrrelevant.all(user.id)) {
      if (result[row.item_id]) result[row.item_id].markedIrrelevant = true;
    }
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

  if (request.method === "GET" && requestUrl.pathname === "/api/auth/me") {
    const user = authenticatedUser(request);
    sendJson(response, 200, {
      authenticated: Boolean(user),
      user,
    });
    return;
  }

  if (!assertSameOrigin(request, response)) return;

  if (request.method === "POST" && requestUrl.pathname === "/api/auth/register") {
    if (authRateLimited(request, "register")) {
      apiError(response, 429, "too_many_attempts", "Please wait before trying again.");
      return;
    }
    const body = await readJson(request);
    const email = normalizeEmail(body.email);
    const displayName = String(body.displayName || "").trim();
    const password = String(body.password || "");
    const favorites = Array.isArray(body.favorites) ? body.favorites.slice(0, 5000) : [];
    if (!validEmail(email) || !validDisplayName(displayName) || !validPassword(password)) {
      apiError(response, 400, "invalid_registration", "Invalid registration details.");
      return;
    }
    if (statements.userByEmail.get(email)) {
      apiError(response, 409, "email_in_use", "This email address is already registered.");
      return;
    }
    const passwordData = hashPassword(password);
    let userId;
    try {
      userId = Number(
        statements.insertUser.run(
          email,
          displayName,
          passwordData.hash,
          passwordData.salt,
        ).lastInsertRowid,
      );
    } catch (error) {
      if (String(error.message).includes("UNIQUE")) {
        apiError(response, 409, "email_in_use", "This email address is already registered.");
        return;
      }
      throw error;
    }
    if (ADMIN_EMAILS.has(email)) statements.markAdmin.run(email);
    statements.subscribeRegisteredUser.run(email, displayName, userId);
    const user = publicUser(statements.userById.get(userId));
    claimClientActivity(user, body.clientId, favorites);
    createSession(userId, request, response);
    sendJson(response, 201, { authenticated: true, user });
    return;
  }

  if (request.method === "POST" && requestUrl.pathname === "/api/auth/login") {
    if (authRateLimited(request, "login")) {
      apiError(response, 429, "too_many_attempts", "Please wait before trying again.");
      return;
    }
    const body = await readJson(request);
    const email = normalizeEmail(body.email);
    const password = String(body.password || "");
    const row = statements.userByEmail.get(email);
    if (!row || !verifyPassword(password, row.password_salt, row.password_hash)) {
      apiError(response, 401, "invalid_credentials", "Email address or password is incorrect.");
      return;
    }
    const user = publicUser(row);
    const favorites = Array.isArray(body.favorites) ? body.favorites.slice(0, 5000) : [];
    claimClientActivity(user, body.clientId, favorites);
    createSession(user.id, request, response);
    sendJson(response, 200, { authenticated: true, user });
    return;
  }

  if (request.method === "POST" && requestUrl.pathname === "/api/auth/logout") {
    authenticatedUser(request);
    if (request.authTokenHash) statements.deleteSession.run(request.authTokenHash);
    response.setHeader("Set-Cookie", sessionCookie("", request, 0));
    sendJson(response, 200, { authenticated: false, user: null });
    return;
  }

  if (request.method === "POST" && requestUrl.pathname === "/api/auth/claim") {
    const user = requireUser(request, response);
    if (!user) return;
    const body = await readJson(request);
    const favorites = Array.isArray(body.favorites) ? body.favorites.slice(0, 5000) : [];
    claimClientActivity(user, body.clientId, favorites);
    sendJson(response, 200, { authenticated: true, user });
    return;
  }

  if (request.method === "PUT" && requestUrl.pathname === "/api/auth/profile") {
    const user = requireUser(request, response);
    if (!user) return;
    const body = await readJson(request);
    const displayName = String(body.displayName || "").trim();
    if (!validDisplayName(displayName)) {
      apiError(response, 400, "invalid_display_name", "Invalid display name.");
      return;
    }
    withTransaction(() => {
      statements.updateUserName.run(displayName, user.id);
      statements.updateCommentNames.run(displayName, user.id);
    });
    sendJson(response, 200, {
      authenticated: true,
      user: publicUser(statements.userById.get(user.id)),
    });
    return;
  }

  if (request.method === "GET" && requestUrl.pathname === "/api/users/mentions") {
    const user = requireUser(request, response);
    if (!user) return;
    sendJson(response, 200, {
      users: statements.mentionableUsers
        .all()
        .filter((row) => Number(row.id) !== user.id)
        .map((row) => ({ displayName: row.display_name })),
    });
    return;
  }

  if (request.method === "GET" && requestUrl.pathname === "/api/interactions") {
    sendJson(response, 200, {
      interactions: allInteractions(authenticatedUser(request)),
    });
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
      interactionFor(
        itemId,
        requestUrl.searchParams.get("clientId"),
        true,
        authenticatedUser(request),
      ),
    );
    return;
  }

  if (request.method === "GET" && requestUrl.pathname === "/api/access") {
    sendJson(response, 200, accessStats());
    return;
  }

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
    segments[3] === "irrelevant"
  ) {
    const itemId = decodeURIComponent(segments[2]);
    const body = await readJson(request);
    const user = requireUser(request, response);
    if (!user) return;
    if (!validItemId(itemId)) {
      apiError(response, 400, "invalid_request", "Invalid item ID.");
      return;
    }
    const markedIrrelevant = Boolean(body.markedIrrelevant);
    withTransaction(() => {
      statements.ensureInteraction.run(itemId);
      if (markedIrrelevant) {
        statements.insertUserIrrelevant.run(itemId, user.id);
      } else {
        statements.deleteUserIrrelevant.run(itemId, user.id);
      }
    });
    sendJson(response, 200, interactionFor(itemId, body.clientId, true, user));
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
    const user = requireUser(request, response);
    if (!user) return;
    if (!validItemId(itemId)) {
      apiError(response, 400, "invalid_request", "Invalid item ID.");
      return;
    }
    const liked = Boolean(body.liked);
    withTransaction(() => {
      statements.ensureInteraction.run(itemId);
      const current = Boolean(statements.hasUserLike.get(itemId, user.id));
      if (liked && !current) {
        statements.insertUserLike.run(itemId, user.id);
        statements.changeLikes.run(1, itemId);
      } else if (!liked && current) {
        statements.deleteUserLike.run(itemId, user.id);
        statements.changeLikes.run(-1, itemId);
      }
    });
    sendJson(response, 200, interactionFor(itemId, body.clientId, true, user));
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
    const user = requireUser(request, response);
    if (!user) return;
    if (
      !validItemId(itemId) ||
      !text ||
      text.length > 500
    ) {
      apiError(response, 400, "invalid_comment", "Invalid comment.");
      return;
    }
    const parentCommentId = body.parentCommentId == null
      ? null
      : Number(body.parentCommentId);
    const parentComment = parentCommentId == null
      ? null
      : statements.findComment.get(parentCommentId, itemId);
    if (parentCommentId != null && (
      !Number.isSafeInteger(parentCommentId) || !parentComment
    )) {
      apiError(response, 400, "invalid_parent_comment", "Reply target was not found.");
      return;
    }
    withTransaction(() => {
      statements.ensureInteraction.run(itemId);
      const inserted = statements.insertComment.run(
        itemId,
        user.displayName,
        text,
        validClientId(body.clientId) ? body.clientId : null,
        user.id,
        parentCommentId,
      );
      notifyCommentParticipants(
        itemId,
        Number(inserted.lastInsertRowid),
        user,
        parentComment,
        mentionedUserIds(text, user.id),
      );
    });
    sendJson(response, 201, interactionFor(itemId, body.clientId, true, user));
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
    const user = authenticatedUser(request);
    if (
      !validItemId(itemId) ||
      !Number.isSafeInteger(commentId) ||
      (!user && !validClientId(clientId))
    ) {
      apiError(response, 400, "invalid_request", "Invalid delete request.");
      return;
    }
    const comment = statements.findComment.get(commentId, itemId);
    if (!comment) {
      apiError(response, 404, "comment_not_found", "Comment was not found.");
      return;
    }
    const ownsComment = user
      ? Number(comment.user_id) === user.id
      : !comment.user_id && (!comment.client_id || comment.client_id === clientId);
    if (!ownsComment) {
      apiError(response, 403, "comment_owner_required", "Only the author can delete this comment.");
      return;
    }
    withTransaction(() => {
      statements.detachCommentReplies.run(commentId);
      statements.deleteComment.run(commentId, itemId);
    });
    sendJson(response, 200, interactionFor(itemId, clientId, true, user));
    return;
  }

  if (
    request.method === "PUT" &&
    segments.length === 6 &&
    segments[0] === "api" &&
    segments[1] === "interactions" &&
    segments[3] === "comments" &&
    segments[5] === "like"
  ) {
    const itemId = decodeURIComponent(segments[2]);
    const commentId = Number(segments[4]);
    const user = requireUser(request, response);
    if (!user) return;
    const body = await readJson(request);
    if (!validItemId(itemId) || !Number.isSafeInteger(commentId)) {
      apiError(response, 400, "invalid_request", "Invalid comment like request.");
      return;
    }
    const comment = statements.findComment.get(commentId, itemId);
    if (!comment) {
      apiError(response, 404, "comment_not_found", "Comment was not found.");
      return;
    }
    withTransaction(() => {
      if (Boolean(body.liked)) {
        const inserted = statements.insertCommentLike.run(commentId, user.id);
        if (Number(inserted.changes) === 1 && comment.user_id && Number(comment.user_id) !== user.id) {
          statements.insertNotification.run(
            Number(comment.user_id),
            user.id,
            "comment_like",
            itemId,
            commentId,
          );
        }
      } else {
        statements.deleteCommentLike.run(commentId, user.id);
        statements.deleteCommentLikeNotification.run(commentId, user.id);
      }
    });
    sendJson(
      response,
      200,
      interactionFor(itemId, body.clientId, true, user),
    );
    return;
  }

  if (
    (request.method === "PUT" || request.method === "DELETE") &&
    segments.length === 3 &&
    segments[0] === "api" &&
    segments[1] === "favorites"
  ) {
    const user = requireUser(request, response);
    if (!user) return;
    const itemId = decodeURIComponent(segments[2]);
    if (!validItemId(itemId)) {
      apiError(response, 400, "invalid_item_id", "Invalid favorite item ID.");
      return;
    }
    if (request.method === "PUT") statements.insertFavorite.run(itemId, user.id);
    else statements.deleteFavorite.run(itemId, user.id);
    sendJson(response, 200, {
      favorites: statements.userFavorites.all(user.id).map((row) => row.item_id),
    });
    return;
  }

  if (request.method === "GET" && requestUrl.pathname === "/api/me/activity") {
    const user = requireUser(request, response);
    if (!user) return;
    const notifications = notificationPayload(user.id, 100);
    sendJson(response, 200, {
      user,
      favorites: statements.userFavorites.all(user.id).map((row) => row.item_id),
      likes: statements.userLikes.all(user.id).map((row) => row.item_id),
      irrelevant: statements.userIrrelevant.all(user.id).map((row) => row.item_id),
      comments: statements.userComments.all(user.id).map((row) => ({
        id: Number(row.id),
        itemId: row.item_id,
        text: row.comment_text,
        createdAt: row.created_at,
      })),
      participated: statements.userParticipation
        .all(user.id, user.id, user.id)
        .map((row) => ({
          itemId: row.item_id,
          activityAt: row.activity_at,
        })),
      notifications: notifications.notifications,
      unreadNotifications: notifications.unreadCount,
      feedback: statements.userFeedback.all(user.id).map((row) => ({
        id: Number(row.id),
        category: row.category,
        message: row.message,
        itemId: row.item_id,
        pageUrl: row.page_url,
        status: row.status,
        createdAt: row.created_at,
      })),
    });
    return;
  }

  if (request.method === "GET" && requestUrl.pathname === "/api/activity/recent") {
    const user = requireUser(request, response);
    if (!user) return;
    const limit = Math.max(
      1,
      Math.min(12, Number(requestUrl.searchParams.get("limit")) || 6),
    );
    sendJson(response, 200, {
      activity: statements.recentActivity.all(limit).map((row) => ({
        commentId: Number(row.id),
        itemId: row.item_id,
        user: row.display_name,
        text: row.comment_text,
        type: row.parent_comment_id ? "comment_reply" : "article_comment",
        createdAt: row.created_at,
        comments: Number(row.comment_count || 0),
        likes: Number(row.like_count || 0),
      })),
    });
    return;
  }

  if (request.method === "GET" && requestUrl.pathname === "/api/notifications") {
    const user = requireUser(request, response);
    if (!user) return;
    sendJson(
      response,
      200,
      notificationPayload(user.id, requestUrl.searchParams.get("limit")),
    );
    return;
  }

  if (request.method === "PUT" && requestUrl.pathname === "/api/notifications/read") {
    const user = requireUser(request, response);
    if (!user) return;
    const body = await readJson(request);
    if (body.all) {
      statements.markAllNotificationsRead.run(user.id);
    } else {
      const ids = Array.isArray(body.ids)
        ? [...new Set(body.ids.map(Number).filter(Number.isSafeInteger))].slice(0, 100)
        : [];
      for (const id of ids) statements.markNotificationRead.run(id, user.id);
    }
    sendJson(response, 200, notificationPayload(user.id, 30));
    return;
  }

  if (request.method === "GET" && requestUrl.pathname === "/api/admin/overview") {
    const admin = requireAdmin(request, response);
    if (!admin) return;
    const users = statements.adminUsers.all().map((row) => ({
      id: Number(row.id),
      email: row.email,
      displayName: row.display_name,
      isAdmin: Boolean(row.is_admin),
      createdAt: row.created_at,
      updatedAt: row.updated_at,
      lastSeenAt: row.last_seen_at,
      favorites: Number(row.favorites || 0),
      likes: Number(row.likes || 0),
      irrelevant: Number(row.irrelevant || 0),
      comments: Number(row.comments || 0),
      feedback: Number(row.feedback || 0),
    }));
    const feedback = statements.adminFeedback.all().map((row) => ({
      id: Number(row.id),
      category: row.category,
      message: row.message,
      itemId: row.item_id,
      pageUrl: row.page_url,
      status: row.status,
      createdAt: row.created_at,
      displayName: row.display_name,
      email: row.email,
    }));
    sendJson(response, 200, {
      totals: {
        users: users.length,
        activeUsers: users.filter((user) => user.lastSeenAt).length,
        favorites: users.reduce((sum, user) => sum + user.favorites, 0),
        likes: users.reduce((sum, user) => sum + user.likes, 0),
        irrelevant: users.reduce((sum, user) => sum + user.irrelevant, 0),
        comments: users.reduce((sum, user) => sum + user.comments, 0),
        feedback: users.reduce((sum, user) => sum + user.feedback, 0),
        mailRecipients: mailingListPayload().activeCount,
      },
      users,
      feedback,
      mailingList: mailingListPayload().recipients,
    });
    return;
  }

  if (request.method === "GET" && requestUrl.pathname === "/api/admin/mailing-list") {
    const admin = requireAdmin(request, response);
    if (!admin) return;
    sendJson(response, 200, mailingListPayload());
    return;
  }

  if (request.method === "POST" && requestUrl.pathname === "/api/admin/mailing-list") {
    const admin = requireAdmin(request, response);
    if (!admin) return;
    const body = await readJson(request);
    const email = normalizeEmail(body.email);
    const displayName = String(body.displayName || "").trim();
    if (!validEmail(email) || (displayName && !validDisplayName(displayName))) {
      apiError(response, 400, "invalid_recipient", "Invalid recipient details.");
      return;
    }
    if (statements.mailingSubscriptionByEmail.get(email)) {
      apiError(response, 409, "recipient_exists", "This email address is already registered.");
      return;
    }
    statements.insertManualMailSubscription.run(email, displayName || null);
    sendJson(response, 201, mailingListPayload());
    return;
  }

  if (
    request.method === "PUT" &&
    segments.length === 4 &&
    segments[0] === "api" &&
    segments[1] === "admin" &&
    segments[2] === "mailing-list"
  ) {
    const admin = requireAdmin(request, response);
    if (!admin) return;
    const id = Number(segments[3]);
    const body = await readJson(request);
    if (!Number.isSafeInteger(id) || id < 1 || typeof body.enabled !== "boolean") {
      apiError(response, 400, "invalid_recipient", "Invalid recipient update.");
      return;
    }
    const result = statements.setMailSubscriptionEnabled.run(body.enabled ? 1 : 0, id);
    if (!result.changes) {
      apiError(response, 404, "recipient_not_found", "Recipient was not found.");
      return;
    }
    sendJson(response, 200, mailingListPayload());
    return;
  }

  if (
    request.method === "DELETE" &&
    segments.length === 4 &&
    segments[0] === "api" &&
    segments[1] === "admin" &&
    segments[2] === "mailing-list"
  ) {
    const admin = requireAdmin(request, response);
    if (!admin) return;
    const id = Number(segments[3]);
    if (!Number.isSafeInteger(id) || id < 1) {
      apiError(response, 400, "invalid_recipient", "Invalid recipient ID.");
      return;
    }
    const result = statements.deleteManualMailSubscription.run(id);
    if (!result.changes) {
      apiError(response, 400, "recipient_not_deletable", "Registered users can only be disabled.");
      return;
    }
    sendJson(response, 200, mailingListPayload());
    return;
  }

  if (request.method === "POST" && requestUrl.pathname === "/api/feedback") {
    const user = requireUser(request, response);
    if (!user) return;
    const body = await readJson(request);
    const allowedCategories = new Set([
      "improvement",
      "bug",
      "article",
      "idea",
      "other",
    ]);
    const category = String(body.category || "other");
    const message = String(body.message || "").trim();
    const itemId = validItemId(body.itemId) ? body.itemId : null;
    const pageUrl = String(body.pageUrl || "").slice(0, 500) || null;
    if (!allowedCategories.has(category) || !message || message.length > 2000) {
      apiError(response, 400, "invalid_feedback", "Invalid feedback.");
      return;
    }
    const result = statements.insertFeedback.run(
      user.id,
      category,
      message,
      itemId,
      pageUrl,
    );
    sendJson(response, 201, { id: Number(result.lastInsertRowid), status: "new" });
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
    sendJson(
      response,
      200,
      interactionFor(itemId, body.clientId, false, authenticatedUser(request)),
    );
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
      ? "no-store, max-age=0, must-revalidate"
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

  const protectedContent =
    requestUrl.pathname === "/news_data.js" ||
    requestUrl.pathname === "/insights_data.js" ||
    requestUrl.pathname.startsWith("/images/");
  if (protectedContent && !authenticatedUser(request)) {
    send(
      response,
      401,
      "Login is required to access DailyNews content.",
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
