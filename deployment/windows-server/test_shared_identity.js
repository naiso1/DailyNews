"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");
const { spawn } = require("node:child_process");
const { once } = require("node:events");
const { DatabaseSync } = require("node:sqlite");
const { migrate } = require("./shared-identity");

const root = fs.mkdtempSync(path.join(os.tmpdir(), "dailynews-shared-"));
const children = [];
const roots = Object.fromEntries(["interior", "exterior"].map((edition) => [edition, path.join(root, edition)]));
const dbFile = (edition) => path.join(roots[edition], "data", "dailynews.sqlite");
async function start(edition, shared = false) {
  const release = path.join(roots[edition], "releases", "abcdef1");
  fs.mkdirSync(release, { recursive: true });
  fs.writeFileSync(path.join(roots[edition], "active-release.txt"), "abcdef1");
  fs.writeFileSync(path.join(release, "index.html"), "<!doctype html><title>fixture</title>");
  fs.writeFileSync(path.join(release, "news_data.js"), `window.LOADED_NEWS_DATA=[{edition:'${edition}'}];`);
  const env = { ...process.env, DAILYNEWS_ROOT: roots[edition], DAILYNEWS_EDITION: edition,
    DAILYNEWS_HOST: "127.0.0.1", DAILYNEWS_PORT: "0", DAILYNEWS_ALLOWED_CLIENTS: "127.0.0.1,::1",
    DAILYNEWS_ADMIN_EMAILS: "shared@example.com", DAILYNEWS_IDENTITY_DB: "", DAILYNEWS_EXTERIOR_DB: "" };
  if (shared) Object.assign(env, { DAILYNEWS_IDENTITY_DB: dbFile("interior"), DAILYNEWS_EXTERIOR_DB: dbFile("exterior") });
  const child = spawn(process.execPath, [path.join(__dirname, "server.js")], { env, stdio: ["ignore", "pipe", "pipe"] });
  children.push(child);
  let stderr = "";
  child.stderr.on("data", (chunk) => { stderr += chunk; });
  const base = await new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error(`Startup timeout: ${stderr}`)), 10000);
    child.once("exit", () => { clearTimeout(timeout); reject(new Error(`Startup failed: ${stderr}`)); });
    child.stdout.on("data", (chunk) => {
      const match = String(chunk).match(/listening on (http:\/\/\S+)/);
      if (match) { clearTimeout(timeout); resolve(match[1]); }
    });
  });
  return { child, base, prefix: edition === "exterior" ? "/exterior" : "", cookie: "",
    async request(endpoint, options = {}, status = 200) {
      const headers = { Origin: base, Cookie: this.cookie, ...options.headers };
      if (options.body && typeof options.body !== "string") {
        headers["Content-Type"] = "application/json";
        options = { ...options, body: JSON.stringify(options.body) };
      }
      const response = await fetch(`${base}${this.prefix}${endpoint}`, { ...options, headers });
      const text = await response.text();
      assert.equal(response.status, status, `${edition} ${endpoint}: ${text}`);
      const cookie = response.headers.get("set-cookie");
      if (cookie) this.cookie = cookie.split(";", 1)[0];
      return { response, json: response.headers.get("content-type")?.includes("application/json") ? JSON.parse(text) : null, text };
    },
  };
}
async function stop(child) {
  if (child.exitCode !== null || child.signalCode !== null) return;
  const stopped = once(child, "exit"); child.kill(); await stopped;
}
const register = (app, email, password, extra = {}) => app.request("/api/auth/register", {
  method: "POST", body: { email, displayName: email.split("@")[0], password, ...extra },
}, 201);
const login = (app, email, password, status = 200) => app.request("/api/auth/login", { method: "POST", body: { email, password } }, status);
const put = (app, endpoint, body, status = 200) => app.request(endpoint, { method: "PUT", body }, status);

async function main() {
  const interior = await start("interior");
  const exterior = await start("exterior");
  await register(interior, "first@example.com", "interior-first-123");
  const inner = (await register(interior, "shared@example.com", "interior-shared-123", { favorites: ["inner-favorite"], clientId: "client-interior-123456" })).json.user;
  const oldInnerCookie = interior.cookie;
  await put(interior, "/api/interactions/same1/like", { liked: true, clientId: "client-interior-123456" });
  const outer = (await register(exterior, "shared@example.com", "old-exterior-123", { mailSubscribed: true, favorites: ["outer-favorite"], clientId: "client-exterior-123456" })).json.user;
  const oldOuterCookie = exterior.cookie;
  await put(exterior, "/api/interactions/same1/like", { liked: true, clientId: "client-exterior-123456" });
  await exterior.request("/api/interactions/same1/comments", { method: "POST", body: { text: "Exterior comment", clientId: "client-exterior-123456" } }, 201);
  await exterior.request("/api/access", { method: "POST", body: { clientId: "client-exterior-123456" } });
  await register(exterior, "exterior-only@example.com", "exterior-only-123");
  assert.notEqual(inner.id, outer.id, "Fixture must exercise overlapping IDs with different owners");
  await stop(interior.child); await stop(exterior.child);
  const before = migrate(dbFile("interior"), dbFile("exterior"));
  assert.equal(before.exteriorOnlyAccounts, 1);
  assert.equal(before.exteriorRecipients, 1);
  const applied = migrate(dbFile("interior"), dbFile("exterior"), true);
  assert.equal(applied.exteriorRecipients, before.exteriorRecipients);
  assert.equal(applied.interiorRecipients, before.interiorRecipients);
  assert.equal(applied.backups.length, 2);
  assert.ok(applied.backups.every((file) => fs.existsSync(file)));
  assert.equal(migrate(dbFile("interior"), dbFile("exterior"), true).alreadyMigrated, true);
  const db = new DatabaseSync(dbFile("exterior"));
  assert.equal(db.prepare("SELECT COUNT(*) AS n FROM sessions").get().n, 0);
  assert.equal(db.prepare("SELECT user_id FROM comments").get().user_id, outer.id);
  db.close();

  let a = await start("interior", true);
  let b = await start("exterior", true);
  a.cookie = oldInnerCookie; b.cookie = oldInnerCookie;
  for (const app of [a, b]) assert.equal((await app.request("/api/config")).json.sharedIdentity, true);
  assert.equal((await a.request("/api/auth/me")).json.user.id, inner.id);
  const exteriorMe = (await b.request("/api/auth/me")).json.user;
  assert.equal(exteriorMe.id, outer.id);
  assert.equal(exteriorMe.identityId, inner.id);
  assert.deepEqual(exteriorMe.subscriptions, { interior: true, exterior: true });
  assert.deepEqual((await a.request("/api/me/activity")).json.favorites, ["inner-favorite"]);
  assert.deepEqual((await b.request("/api/me/activity")).json.favorites, ["outer-favorite"]);
  assert.equal((await b.request("/api/me/activity")).json.comments.length, 1);
  assert.equal((await a.request("/api/me/activity")).json.comments.length, 0);
  assert.equal((await a.request("/api/access")).json.total, 0);
  assert.equal((await b.request("/api/access")).json.total, 1);
  assert.equal((await b.request("/api/auth/me", { headers: { Cookie: oldOuterCookie } })).json.authenticated, false);
  await login(b, "shared@example.com", "old-exterior-123", 401);
  const commonLogin = await login(b, "shared@example.com", "interior-shared-123");
  assert.match(commonLogin.response.headers.get("set-cookie"), /^dailynews_session=.+; Path=\/;/);
  a.cookie = b.cookie;
  await a.request("/news_data.js");
  await b.request("/api/me/subscriptions", { headers: { Cookie: "" } }, 401);
  await b.request("/api/me/subscriptions", { method: "PUT", headers: { Cookie: "" }, body: { subscriptions: { interior: true, exterior: true } } }, 401);
  await put(b, "/api/me/subscriptions", { subscriptions: { interior: true } }, 400);
  await put(b, "/api/me/subscriptions", { subscriptions: { interior: false, exterior: "true" } }, 400);
  for (const choices of [{ interior: true, exterior: false }, { interior: false, exterior: true }, { interior: true, exterior: true }, { interior: false, exterior: false }]) {
    assert.deepEqual((await put(b, "/api/me/subscriptions", { subscriptions: choices, email: "first@example.com" })).json.subscriptions, choices);
    assert.deepEqual((await a.request("/api/me/subscriptions")).json.subscriptions, choices);
    for (const [app, edition] of [[a, "interior"], [b, "exterior"]]) {
      const list = (await app.request("/api/admin/mailing-list")).json;
      assert.equal(list.recipients.find((row) => row.email === "shared@example.com").enabled, choices[edition]);
    }
  }
  // A stale form in another edition must not re-enable a subscription that was stopped.
  const baseline = { interior: true, exterior: false };
  const currentChoices = { interior: false, exterior: false };
  await put(a, "/api/me/subscriptions", { subscriptions: baseline });
  await put(a, "/api/me/subscriptions", { subscriptions: currentChoices, expectedSubscriptions: baseline });
  const conflict = await put(b, "/api/me/subscriptions", {
    subscriptions: { interior: true, exterior: true }, expectedSubscriptions: baseline,
  }, 409);
  assert.equal(conflict.json.error.code, "subscription_conflict");
  assert.deepEqual((await b.request("/api/me/subscriptions")).json.subscriptions, currentChoices);
  await put(b, "/api/me/subscriptions", { subscriptions: baseline, expectedSubscriptions: { interior: true } }, 400);
  await put(b, "/api/me/subscriptions", { subscriptions: currentChoices, expectedSubscriptions: currentChoices });
  // Existing singular endpoint remains compatible and changes only its own edition.
  await put(b, "/api/me/subscription", { enabled: true });
  assert.deepEqual((await a.request("/api/me/subscriptions")).json.subscriptions, { interior: false, exterior: true });
  await put(b, "/api/me/subscriptions", { subscriptions: { interior: false, exterior: false } });
  await put(b, "/api/auth/profile", { displayName: "Common Name" });
  assert.equal((await a.request("/api/auth/me")).json.user.displayName, "Common Name");
  assert.equal((await b.request("/api/interactions/same1")).json.commentItems[0].user, "Common Name");
  await put(b, "/api/auth/password", { currentPassword: "wrong-pass-123", newPassword: "new-shared-123" }, 401);
  const revokedCookie = b.cookie;
  await put(b, "/api/auth/password", { currentPassword: "interior-shared-123", newPassword: "new-shared-123" });
  assert.notEqual(b.cookie, revokedCookie);
  assert.equal((await a.request("/api/auth/me")).json.authenticated, false);
  assert.equal((await a.request("/api/auth/me", { headers: { Cookie: oldInnerCookie } })).json.authenticated, false);
  await login(a, "shared@example.com", "interior-shared-123", 401);
  await login(a, "shared@example.com", "new-shared-123");
  assert.deepEqual((await a.request("/api/me/subscriptions")).json.subscriptions, { interior: false, exterior: false });
  await register(b, "fresh@example.com", "fresh-common-123", { subscriptions: { interior: false, exterior: false } });
  await a.request("/api/auth/register", { method: "POST", body: { email: "fresh@example.com", displayName: "dupe", password: "different-123" } }, 409);
  a.cookie = b.cookie;
  assert.deepEqual((await a.request("/api/me/subscriptions")).json.subscriptions, { interior: false, exterior: false });
  await b.request("/api/auth/logout", { method: "POST", body: {} });
  assert.equal((await a.request("/api/auth/me")).json.authenticated, false);
  await login(a, "exterior-only@example.com", "exterior-only-123");
  assert.deepEqual((await a.request("/api/me/subscriptions")).json.subscriptions, { interior: false, exterior: false });
  const savedCookie = a.cookie;
  await stop(a.child); await stop(b.child);
  a = await start("interior", true); b = await start("exterior", true);
  a.cookie = savedCookie; b.cookie = savedCookie;
  assert.deepEqual((await b.request("/api/me/subscriptions")).json.subscriptions, { interior: false, exterior: false });
  await login(b, "shared@example.com", "new-shared-123");
  assert.deepEqual((await b.request("/api/me/subscriptions")).json.subscriptions, { interior: false, exterior: false });
  const list = (await b.request("/api/admin/mailing-list")).json;
  assert.equal(list.activeCount, 0, "Login and restart must not restore subscriptions");
  console.log("Shared identity tests passed: migration, old interior sessions, colliding local IDs, common login/logout/password, all subscription choices, export compatibility, restart and isolated activity/metrics.");
}
main().catch((error) => { console.error(error); process.exitCode = 1; }).finally(async () => {
  await Promise.all(children.map(stop));
  if (path.dirname(root) !== path.resolve(os.tmpdir()) || !path.basename(root).startsWith("dailynews-shared-")) throw new Error("Unsafe cleanup path");
  fs.rmSync(root, { recursive: true, force: true });
});
