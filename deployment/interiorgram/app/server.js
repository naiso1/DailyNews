"use strict";

const fs = require("fs");
const http = require("http");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const PUBLIC_DIR = path.join(ROOT, "public");
const DATA_FILE = path.join(PUBLIC_DIR, "data.json");
const STATE_DIR = path.join(ROOT, "data");
const LOG_DIR = path.join(ROOT, "logs");
const REACTIONS_FILE = path.join(STATE_DIR, "reactions.json");
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

for (const directory of [STATE_DIR, LOG_DIR]) {
  fs.mkdirSync(directory, { recursive: true });
}

class HttpError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

function log(message) {
  const line = `${new Date().toISOString()} ${message}\n`;
  process.stdout.write(line);
  try {
    fs.appendFileSync(LOG_FILE, line, "utf8");
  } catch (_) {
    // Logging must never stop the service.
  }
}

function readIdeas() {
  const parsed = JSON.parse(fs.readFileSync(DATA_FILE, "utf8"));
  if (!Array.isArray(parsed)) {
    throw new Error("data.json must contain an array.");
  }
  return parsed.filter((idea) => idea && idea.title !== "New Idea");
}

function emptyReactions() {
  return { likes: {}, comments: {}, deleted: [] };
}

function readReactions() {
  if (!fs.existsSync(REACTIONS_FILE)) return emptyReactions();
  try {
    const parsed = JSON.parse(fs.readFileSync(REACTIONS_FILE, "utf8"));
    return {
      likes: parsed.likes && typeof parsed.likes === "object" ? parsed.likes : {},
      comments:
        parsed.comments && typeof parsed.comments === "object"
          ? parsed.comments
          : {},
      deleted: Array.isArray(parsed.deleted) ? parsed.deleted : [],
    };
  } catch (error) {
    log(`Could not read reactions: ${error.message}`);
    return emptyReactions();
  }
}

function writeReactions(reactions) {
  const temporary = `${REACTIONS_FILE}.${process.pid}.tmp`;
  fs.writeFileSync(
    temporary,
    `${JSON.stringify(reactions, null, 2)}\n`,
    "utf8",
  );
  fs.renameSync(temporary, REACTIONS_FILE);
}

function ideaExists(ideaId) {
  return readIdeas().some((idea) => String(idea.id) === ideaId);
}

function normalizeIdeaId(value) {
  const ideaId = String(value || "").trim();
  if (!/^[A-Za-z0-9_-]{3,100}$/.test(ideaId)) {
    throw new HttpError(400, "アイデアIDが不正です。");
  }
  if (!ideaExists(ideaId)) {
    throw new HttpError(404, "アイデアが見つかりません。");
  }
  return ideaId;
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

function readJson(request, maxBytes = 16 * 1024) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let size = 0;
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

function serveFile(request, response, root, relativePath, cacheControl) {
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
  if (request.method === "HEAD") {
    response.end();
    return;
  }
  fs.createReadStream(file).pipe(response);
}

async function handleApi(request, response, requestUrl) {
  if (request.method === "GET" && requestUrl.pathname === "/health") {
    sendJson(response, 200, {
      status: "ok",
      service: "interiorgram",
      ideas: readIdeas().length,
      time: new Date().toISOString(),
    });
    return true;
  }

  if (request.method === "GET" && requestUrl.pathname === "/api/ideas") {
    sendJson(response, 200, readIdeas());
    return true;
  }

  if (request.method === "GET" && requestUrl.pathname === "/api/meta") {
    sendJson(response, 200, readReactions());
    return true;
  }

  const likeMatch = requestUrl.pathname.match(
    /^\/api\/ideas\/([^/]+)\/like$/,
  );
  if (request.method === "POST" && likeMatch) {
    const ideaId = normalizeIdeaId(decodeURIComponent(likeMatch[1]));
    const reactions = readReactions();
    reactions.likes[ideaId] = Number(reactions.likes[ideaId] || 0) + 1;
    writeReactions(reactions);
    sendJson(response, 200, { likes: reactions.likes[ideaId] });
    return true;
  }

  const commentMatch = requestUrl.pathname.match(
    /^\/api\/ideas\/([^/]+)\/comments$/,
  );
  if (request.method === "POST" && commentMatch) {
    const ideaId = normalizeIdeaId(decodeURIComponent(commentMatch[1]));
    const body = await readJson(request);
    const text = String(body.text || "").trim();
    if (!text || text.length > 500) {
      throw new HttpError(
        400,
        "コメントは1文字以上500文字以内で入力してください。",
      );
    }
    const reactions = readReactions();
    if (!Array.isArray(reactions.comments[ideaId])) {
      reactions.comments[ideaId] = [];
    }
    const comment = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      text,
      date: new Date().toISOString(),
    };
    reactions.comments[ideaId].push(comment);
    writeReactions(reactions);
    sendJson(response, 201, {
      comment,
      comments: reactions.comments[ideaId],
    });
    return true;
  }

  if (
    request.method === "POST" &&
    ["/api/ideas/create", "/api/ideas/update", "/api/upload"].includes(
      requestUrl.pathname,
    )
  ) {
    throw new HttpError(
      403,
      "コンテンツ更新はAntigravityの公開フローから実行してください。",
    );
  }

  return false;
}

const server = http.createServer(async (request, response) => {
  try {
    const requestUrl = new URL(
      request.url,
      `http://${request.headers.host || "localhost"}`,
    );
    if (await handleApi(request, response, requestUrl)) return;

    if (requestUrl.pathname.startsWith("/api/")) {
      sendJson(response, 404, { error: "API endpoint not found" });
      return;
    }
    if (!["GET", "HEAD"].includes(request.method)) {
      sendJson(response, 405, { error: "Method not allowed" });
      return;
    }

    const relativePath =
      requestUrl.pathname === "/"
        ? "index.html"
        : decodeURIComponent(requestUrl.pathname.replace(/^\/+/, ""));
    serveFile(
      request,
      response,
      PUBLIC_DIR,
      relativePath,
      relativePath === "index.html" || relativePath === "data.js"
        ? "no-cache"
        : "public, max-age=3600",
    );
  } catch (error) {
    const status = error instanceof HttpError ? error.status : 500;
    if (status === 500) log(`ERROR ${error.stack || error.message}`);
    if (!response.headersSent) {
      sendJson(response, status, {
        error:
          status === 500
            ? "サーバーでエラーが発生しました。"
            : error.message,
      });
    } else {
      response.end();
    }
  }
});

try {
  const ideaCount = readIdeas().length;
  log(`Loaded ${ideaCount} Interiorgram idea(s).`);
} catch (error) {
  log(`Content load failed: ${error.stack || error.message}`);
  process.exit(1);
}

server.listen(PORT, HOST, () => {
  log(`Interiorgram listening on http://${HOST}:${PORT}`);
});

function shutdown(signal) {
  log(`Received ${signal}; shutting down.`);
  server.close(() => process.exit(0));
  setTimeout(() => process.exit(1), 5000).unref();
}

process.on("SIGINT", () => shutdown("SIGINT"));
process.on("SIGTERM", () => shutdown("SIGTERM"));
