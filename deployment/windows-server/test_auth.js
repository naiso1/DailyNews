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
fs.writeFileSync(path.join(releaseDir, "news_data.js"), "window.LOADED_NEWS_DATA=[];");

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
  const protectedBeforeLogin = await fetch(`${base}/news_data.js`);
  assert.equal(protectedBeforeLogin.status, 401);

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

  const protectedAfterLogin = await fetch(`${base}/news_data.js`, {
    headers: { Cookie: cookie },
  });
  assert.equal(protectedAfterLogin.status, 200);

  const like = await request("/api/interactions/jp1/like", {
    method: "PUT",
    body: { clientId: "abcdefghijklmnop1234", liked: true },
  });
  assert.equal(like.liked, true);
  assert.deepEqual(like.likedBy, ["Test User"]);

  const irrelevant = await request("/api/interactions/jp1/irrelevant", {
    method: "PUT",
    body: { clientId: "abcdefghijklmnop1234", markedIrrelevant: true },
  });
  assert.equal(irrelevant.markedIrrelevant, true);
  assert.equal(irrelevant.irrelevant, 1);

  const interactions = await request("/api/interactions");
  assert.deepEqual(interactions.interactions.jp1.likedBy, ["Test User"]);
  assert.equal(interactions.interactions.jp1.markedIrrelevant, true);
  assert.equal(interactions.interactions.jp1.irrelevant, 1);

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
  assert.deepEqual(activity.irrelevant, ["jp1"]);
  assert.equal(activity.comments.length, 1);
  assert.equal(activity.feedback.length, 1);

  const firstUserCookie = cookie;
  const secondRegistration = await request("/api/auth/register", {
    method: "POST",
    body: {
      email: "second.user@example.com",
      displayName: "Second User",
      password: "correct-horse-456",
      clientId: "secondclientidentifier1234",
      favorites: [],
    },
  });
  assert.equal(secondRegistration.authenticated, true);

  const mentionCandidates = await request("/api/users/mentions");
  assert.deepEqual(mentionCandidates.users, [{ displayName: "Test User" }]);

  const mention = await request("/api/interactions/jp1/comments", {
    method: "POST",
    body: {
      clientId: "secondclientidentifier1234",
      text: "@Test User mention test",
    },
  });
  assert.equal(
    mention.commentItems.find((entry) => entry.text === "@Test User mention test")?.user,
    "Second User",
  );

  const reply = await request("/api/interactions/jp1/comments", {
    method: "POST",
    body: {
      clientId: "secondclientidentifier1234",
      text: "test reply",
      parentCommentId: comment.commentItems[0].id,
    },
  });
  assert.equal(
    reply.commentItems.find((entry) => entry.text === "test reply")?.parentId,
    comment.commentItems[0].id,
  );

  await request(
    `/api/interactions/jp1/comments/${comment.commentItems[0].id}/like`,
    {
      method: "PUT",
      body: { clientId: "secondclientidentifier1234", liked: true },
    },
  );

  const secondActivity = await request("/api/me/activity");
  assert.equal(secondActivity.participated[0].itemId, "jp1");

  cookie = firstUserCookie;
  const notifications = await request("/api/notifications");
  assert.equal(notifications.unreadCount, 3);
  assert.deepEqual(
    new Set(notifications.notifications.map((entry) => entry.type)),
    new Set(["mention", "comment_reply", "comment_like"]),
  );

  const recent = await request("/api/activity/recent?limit=3");
  assert.equal(recent.activity[0].itemId, "jp1");
  assert.equal(recent.activity[0].type, "comment_reply");

  const markedRead = await request("/api/notifications/read", {
    method: "PUT",
    body: { ids: [notifications.notifications[0].id] },
  });
  assert.equal(markedRead.unreadCount, 2);
  const allRead = await request("/api/notifications/read", {
    method: "PUT",
    body: { all: true },
  });
  assert.equal(allRead.unreadCount, 0);

  const admin = await request("/api/admin/overview");
  assert.equal(admin.totals.users, 2);
  const adminUser = admin.users.find((user) => user.email === "test.user@example.com");
  assert.equal(adminUser.isAdmin, true);
  assert.equal(adminUser.irrelevant, 1);
  assert.equal(admin.totals.irrelevant, 1);
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
