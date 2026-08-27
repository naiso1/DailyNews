"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawn } = require("node:child_process");

const port = 18082 + Math.floor(Math.random() * 1000);
const root = fs.mkdtempSync(path.join(os.tmpdir(), "dailynews-auth-"));
const appDir = path.join(root, "app");
const releaseDir = path.join(root, "releases", "abcdef1");
fs.mkdirSync(appDir, { recursive: true });
fs.mkdirSync(releaseDir, { recursive: true });
fs.copyFileSync(path.join(__dirname, "server.js"), path.join(appDir, "server.js"));
fs.writeFileSync(path.join(root, "active-release.txt"), "abcdef1\n", "ascii");
fs.writeFileSync(path.join(releaseDir, "index.html"), "<!doctype html><title>test</title>");

const child = spawn(process.execPath, [path.join(appDir, "server.js")], {
  cwd: appDir,
  env: {
    ...process.env,
    DAILYNEWS_HOST: "127.0.0.1",
    DAILYNEWS_PORT: String(port),
    DAILYNEWS_ADMIN_EMAILS: "test.user@example.com",
  },
  stdio: ["ignore", "pipe", "pipe"],
});

let stderr = "";
child.stderr.on("data", (chunk) => {
  stderr += chunk.toString();
});

const base = `http://127.0.0.1:${port}`;
let cookie = "";

async function request(pathname, options = {}) {
  const headers = {
    Accept: "application/json",
    Origin: base,
    ...(options.headers || {}),
  };
  if (cookie) headers.Cookie = cookie;
  if (options.body && typeof options.body !== "string") {
    headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(options.body);
  }
  const response = await fetch(`${base}${pathname}`, { ...options, headers });
  const setCookie = response.headers.get("set-cookie");
  if (setCookie) cookie = setCookie.split(";", 1)[0];
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(`${response.status}: ${JSON.stringify(payload)}`);
  }
  return payload;
}

async function waitForServer() {
  for (let attempt = 0; attempt < 40; attempt += 1) {
    try {
      await request("/api/status");
      return;
    } catch (_) {
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
  }
  throw new Error(`Test server did not start: ${stderr}`);
}

async function main() {
  await waitForServer();
  const registration = await request("/api/auth/register", {
    method: "POST",
    body: {
      email: "Test.User@example.com",
      displayName: "Test User",
      password: "correct-horse-123",
      clientId: "abcdefghijklmnop1234",
      favorites: ["jp1"],
    },
  });
  assert.equal(registration.authenticated, true);

  const me = await request("/api/auth/me");
  assert.equal(me.user.email, "test.user@example.com");
  assert.equal(me.user.displayName, "Test User");
  assert.equal(me.user.isAdmin, true);

  const like = await request("/api/interactions/jp1/like", {
    method: "PUT",
    body: { clientId: "abcdefghijklmnop1234", liked: true },
  });
  assert.equal(like.liked, true);

  const comment = await request("/api/interactions/jp1/comments", {
    method: "POST",
    body: { clientId: "abcdefghijklmnop1234", text: "test comment" },
  });
  assert.equal(comment.commentItems[0].user, "Test User");

  const commentLike = await request(
    `/api/interactions/jp1/comments/${comment.commentItems[0].id}/like`,
    {
      method: "PUT",
      body: { clientId: "abcdefghijklmnop1234", liked: true },
    },
  );
  assert.equal(commentLike.commentItems[0].likes, 1);

  await request("/api/feedback", {
    method: "POST",
    body: {
      category: "improvement",
      message: "test feedback",
      pageUrl: `${base}/`,
    },
  });

  const activity = await request("/api/me/activity");
  assert.deepEqual(activity.favorites, ["jp1"]);
  assert.deepEqual(activity.likes, ["jp1"]);
  assert.equal(activity.comments.length, 1);
  assert.equal(activity.feedback.length, 1);

  const admin = await request("/api/admin/overview");
  assert.equal(admin.totals.users, 1);
  assert.equal(admin.users[0].email, "test.user@example.com");
  assert.equal(admin.users[0].isAdmin, true);
  assert.equal(admin.feedback.length, 1);
  process.stdout.write("DailyNews auth integration test passed.\n");
}

main()
  .catch((error) => {
    process.stderr.write(`${error.stack || error}\n`);
    process.exitCode = 1;
  })
  .finally(() => {
    child.kill();
    fs.rmSync(root, { recursive: true, force: true });
  });
