"use strict";

const fs = require("fs");
const http = require("http");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const RELEASES_DIR = path.join(ROOT, "releases");
const ACTIVE_RELEASE_FILE = path.join(ROOT, "active-release.txt");
const LOG_FILE = path.join(ROOT, "logs", "server.log");
const HOST = process.env.DAILYNEWS_HOST || "202.15.67.132";
const PORT = Number(process.env.DAILYNEWS_PORT || 8082);
const ALLOWED_CLIENTS = new Set(
  (process.env.DAILYNEWS_ALLOWED_CLIENTS ||
    "127.0.0.1,::1,202.15.67.132,172.29.41.49")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean),
);

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
  return String(address || "").replace(/^::ffff:/, "");
}

function isAllowedClient(address) {
  return ALLOWED_CLIENTS.has(normalizeAddress(address));
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

function send(response, status, body, contentType, extraHeaders = {}) {
  response.writeHead(status, {
    "Content-Type": contentType,
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    ...extraHeaders,
  });
  response.end(body);
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
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
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

const server = http.createServer((request, response) => {
  const client = normalizeAddress(request.socket.remoteAddress);
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

  if (request.method !== "GET" && request.method !== "HEAD") {
    send(response, 405, "Method Not Allowed", "text/plain; charset=utf-8", {
      Allow: "GET, HEAD",
    });
    return;
  }

  const requestUrl = new URL(
    request.url,
    `http://${request.headers.host || "localhost"}`,
  );
  const release = activeRelease();

  if (requestUrl.pathname === "/health") {
    const body = JSON.stringify({
      status: release ? "ok" : "not_ready",
      release: release?.releaseId || null,
      port: PORT,
      time: new Date().toISOString(),
    });
    send(
      response,
      release ? 200 : 503,
      request.method === "HEAD" ? "" : body,
      "application/json; charset=utf-8",
      { "Cache-Control": "no-store" },
    );
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
  server.close(() => process.exit(0));
  setTimeout(() => process.exit(1), 5000).unref();
}

process.on("SIGINT", () => shutdown("SIGINT"));
process.on("SIGTERM", () => shutdown("SIGTERM"));
