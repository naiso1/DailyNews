"use strict";

// Isolated real HTTP/SQLite coverage; no production data or email is touched.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawn } = require("node:child_process");
const { once } = require("node:events");
const vm = require("node:vm");

const roots = [];
const children = [];
const repo = path.resolve(__dirname, "../..");
const html = fs.readFileSync(path.join(repo, "内装製品デイリーニュース.html"), "utf8");

function checkFrontend() {
  const bootstrap = [...html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/g)]
    .find((match) => match[2].includes("window.dailyNewsStorageKey"))[2];
  for (const id of ["interior", "exterior"]) {
    const exterior = id === "exterior";
    const nodes = new Map();
    const node = (name) => {
      if (!nodes.has(name)) nodes.set(name, {
        textContent: "", innerHTML: "", style: {},
        classes: new Set(),
        classList: {
          add(value) { nodes.get(name).classes.add(value); },
          remove(value) { nodes.get(name).classes.delete(value); },
          contains(value) { return nodes.get(name).classes.has(value); },
          toggle(value, enabled) { enabled ? this.add(value) : this.remove(value); },
        },
        querySelector() { return { addEventListener() {} }; },
      });
      return nodes.get(name);
    };
    const context = vm.createContext({
      window: { addEventListener() {} },
      location: { pathname: exterior ? "/exterior/" : "/", hostname: "localhost" },
      document: {
        documentElement: { dataset: {}, classList: { add() {} } },
        body: { style: {} },
        addEventListener() {},
        getElementById: node,
      },
    });
    vm.runInContext(fs.readFileSync(path.join(repo, "dailynews_config.js"), "utf8"), context);
    vm.runInContext(bootstrap, context);
    vm.runInContext(fs.readFileSync(path.join(repo, "dailynews_account.js"), "utf8"), context);
    assert.equal(vm.runInContext("ACCOUNT_API_BASE", context), exterior ? "/exterior/api" : "/api");
    for (const key of ["favorites_v1", "liked_jp1", "local_access_stats", "dailynews_client_id_v1"]) {
      assert.equal(vm.runInContext(`window.dailyNewsStorageKey(${JSON.stringify(key)})`, context), exterior ? `dailynews_exterior:${key}` : key);
    }
    vm.runInContext('renderAuth("register")', context);
    const form = node("accountBody").innerHTML;
    const mailCheckbox = form.match(/<input name="mailSubscribed"[^>]*>/)?.[0];
    assert.equal(Boolean(mailCheckbox), exterior);
    if (exterior) assert.ok(!mailCheckbox.includes("checked"), "Exterior opt-in must start unchecked");
    vm.runInContext('accountState.authResolved = true; renderAuth = () => {}; updateRegistrationPrompt();', context);
    assert.equal(node("accountOverlay").classes.has("auth-required"), !exterior);
    assert.equal(node("accountOverlay").classes.has("open"), !exterior);
    const clientPrefix = fs.readFileSync(path.join(repo, "dailynews_client.js"), "utf8").split("const JST_OFFSET_MS")[0];
    vm.runInContext(clientPrefix, context);
    assert.equal(vm.runInContext("CLIENT_ID_KEY === ACCOUNT_CLIENT_ID_KEY", context), true);
    assert.equal(vm.runInContext("LOCAL_ACCESS_MARK_KEY", context), `${exterior ? "dailynews_exterior:" : ""}local_access_mark_date_v3`);
  }
  for (const match of html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/g)) {
    if (!match[1].includes("src=")) new vm.Script(match[2]);
  }
}

function checkPublicationStatus() {
  const statusScript = [...html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/g)]
    .find((match) => match[2].includes("function normalizeExteriorPublication"))[2];
  const context = vm.createContext({ window: { DAILYNEWS_CONFIG: { id: "interior" } } });
  vm.runInContext(statusScript, context);
  const zero = { edition_id: "exterior", processed_through: "2026-09-14", target_dates: ["2026-09-14"], selected_count: 0, status: "no_matching_news" };
  const mixed = { ...zero, target_dates: ["2026-09-12", "2026-09-13", "2026-09-14"], selected_count: 2, status: "published" };
  const building = { edition_id: "exterior", status: "building", processed_through: "" };
  const normalize = (payload) => vm.runInContext(`normalizeExteriorPublication(${JSON.stringify(payload)})`, context);
  const describe = (payload, news) => vm.runInContext(`describeExteriorPublication(${JSON.stringify(payload)}, ${JSON.stringify(news)})`, context);
  assert.equal(normalize(zero).processed_through, "2026-09-14");
  assert.equal(normalize(building).processed_through, "");
  assert.match(describe(building, []), /初回ニュースを作成中です/);
  assert.doesNotMatch(describe(building, []), /収集・選定済み/);
  assert.match(describe(zero, [{ date: "2026-09-11" }]), /2026-09-14まで収集・選定済み/);
  assert.match(describe(zero, []), /条件に合う記事がありませんでした/);
  assert.match(describe(mixed, [{ date: "2026-09-12" }, { date: "2026-09-13" }]), /採用は2件/);
  assert.match(describe(mixed, [{ date: "2026-09-12" }]), /2026-09-14付の新しい掲載記事はありません/);
  assert.doesNotMatch(describe(mixed, [{ date: "2026-09-14" }]), /新しい掲載記事はありません/);
  for (const invalid of [null, { ...zero, edition_id: "interior" }, { ...zero, processed_through: "2026-02-30" }, { ...zero, status: "failed" }, { ...zero, selected_count: 5 }, { ...zero, target_dates: ["2026-09-13"] }]) {
    assert.equal(normalize(invalid), null);
  }
  assert.match(describe(null, []), /収集状況を確認できませんでした/);
  const rangeFunction = html.match(/        function setNewDateRangeFromNews\(data\) \{[\s\S]*?(?=        function normalizeIsNewFlags)/)[0];
  vm.runInContext('let NEW_DATE_RANGE; window.DAILYNEWS_CONFIG.id = "exterior";', context);
  vm.runInContext(rangeFunction, context);
  for (const [payload, start, end] of [[zero, "2026-09-14", "2026-09-14"], [mixed, "2026-09-12", "2026-09-14"], [normalize(building), null, null], [null, null, null]]) {
    context.window.EXTERIOR_PUBLICATION_STATUS = payload;
    vm.runInContext('setNewDateRangeFromNews([{date:"2026-09-11"}]);', context);
    assert.equal(vm.runInContext("NEW_DATE_RANGE.start", context), start);
    assert.equal(vm.runInContext("NEW_DATE_RANGE.end", context), end);
  }
}

async function start(edition, existingRoot) {
  const root = existingRoot || fs.mkdtempSync(path.join(os.tmpdir(), `dailynews-editions-${edition}-`));
  if (!existingRoot) {
    roots.push(root);
    const release = path.join(root, "releases", "abcdef1");
    fs.mkdirSync(path.join(release, "images"), { recursive: true });
    fs.writeFileSync(path.join(root, "active-release.txt"), "abcdef1\n");
    fs.writeFileSync(path.join(release, "index.html"), html);
    fs.writeFileSync(path.join(release, "news_data.js"), `window.LOADED_NEWS_DATA=[{id:'shared1',edition:'${edition}'}];`);
    fs.writeFileSync(path.join(release, "insights_data.js"), "window.DAILY_INSIGHTS=[];");
    fs.writeFileSync(path.join(release, "images", "sample.svg"), "<svg/>");
  }
  const child = spawn(process.execPath, [path.join(__dirname, "server.js")], {
    env: { ...process.env, DAILYNEWS_EDITION: edition, DAILYNEWS_ROOT: root, DAILYNEWS_HOST: "127.0.0.1", DAILYNEWS_PORT: "0", DAILYNEWS_ALLOWED_CLIENTS: "127.0.0.1,::1", DAILYNEWS_ADMIN_EMAILS: "admin@example.com" },
    stdio: ["ignore", "pipe", "pipe"],
  });
  children.push(child);
  let errors = "";
  child.stderr.on("data", (data) => { errors += data; });
  const base = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`Server startup timed out: ${errors}`)), 10000);
    child.stdout.on("data", (data) => {
      const match = String(data).match(/listening on (http:\/\/[^\s]+)/);
      if (match) { clearTimeout(timer); resolve(match[1]); }
    });
    child.once("exit", (code) => { clearTimeout(timer); reject(new Error(`Startup exited ${code}: ${errors}`)); });
  });
  return {
    root, child, base, prefix: edition === "exterior" ? "/exterior" : "", cookie: "",
    async request(endpoint, options = {}, expected = 200) {
      const headers = { Origin: base, ...options.headers };
      if (this.cookie && !Object.hasOwn(headers, "Cookie")) headers.Cookie = this.cookie;
      if (options.body && typeof options.body !== "string") {
        headers["Content-Type"] = "application/json";
        options = { ...options, body: JSON.stringify(options.body) };
      }
      const response = await fetch(`${base}${this.prefix}${endpoint}`, { ...options, headers });
      const body = await response.text();
      assert.equal(response.status, expected, `${edition} ${endpoint}: ${body}`);
      const cookie = response.headers.get("set-cookie");
      if (cookie) this.cookie = cookie.split(";", 1)[0];
      return { response, body, json: response.headers.get("content-type")?.includes("application/json") ? JSON.parse(body) : null };
    },
  };
}

async function stop(child) {
  if (child.exitCode !== null || child.signalCode !== null) return;
  const ended = once(child, "exit");
  child.kill();
  await ended;
}

async function main() {
  checkFrontend();
  checkPublicationStatus();
  const [interior, exterior] = await Promise.all([start("interior"), start("exterior")]);
  for (const app of [interior, exterior]) {
    const isExterior = app === exterior;
    const config = (await app.request("/api/config")).json;
    assert.equal(config.allowGuestRead, isExterior);
    assert.equal(config.imageGenerationEnabled, !isExterior);
    assert.equal(config.apiBase, `${app.prefix}/api`);
    await app.request("/");
    for (const file of ["news_data.js", "insights_data.js", "images/sample.svg"]) {
      await app.request(`/${file}`, {}, isExterior ? 200 : 401);
    }
    assert.match((await app.request("/dailynews_config.js")).body, new RegExp(`"id":"${config.id}"`));
    await app.request("/api/me/subscription", {}, 401);
    await app.request("/api/activity/recent", {}, isExterior ? 200 : 401);
    await app.request("/api/notifications", {}, 401);
    await app.request("/api/me/subscription", { method: "PUT", body: { enabled: true } }, 401);
    await app.request("/api/interactions/shared1/like", { method: "PUT", body: { liked: true, clientId: "shared-browser-123456" } }, 401);
    await app.request("/api/access/reset-today", { method: "POST" }, 401);
    if (isExterior) await app.request("/api/interactions/shared1/comments/1?clientId=shared-browser-123456", { method: "DELETE" }, 401);
    const registered = await app.request("/api/auth/register", { method: "POST", body: { email: "reader@example.com", displayName: "Reader", password: "test-password-123" } }, 201);
    assert.equal(registered.json.user.mailSubscribed, !isExterior);
    assert.match(registered.response.headers.get("set-cookie"), isExterior ? /^dailynews_exterior_session=.+; Path=\/exterior\// : /^dailynews_session=.+; Path=\//);
    await app.request("/news_data.js");
  }
  // Same host, same user IDs and same item/client IDs cannot merge separate edition metrics or sessions.
  assert.equal((await exterior.request("/api/auth/me", { headers: { Cookie: interior.cookie } })).json.authenticated, false);
  assert.equal((await interior.request("/api/auth/me", { headers: { Cookie: exterior.cookie } })).json.authenticated, false);
  await exterior.request("/api/access", { method: "POST", body: { clientId: "shared-browser-123456" } });
  await exterior.request("/api/access", { method: "POST", body: { clientId: "shared-browser-123456" } });
  assert.equal((await exterior.request("/api/access")).json.total, 1);
  assert.equal((await interior.request("/api/access")).json.total, 0);
  await exterior.request("/api/interactions/shared1/like", { method: "PUT", body: { liked: true, clientId: "shared-browser-123456" } });
  assert.equal((await exterior.request("/api/interactions")).json.interactions.shared1.likes, 1);
  assert.equal((await interior.request("/api/interactions")).json.interactions.shared1, undefined);

  await exterior.request("/api/me/subscription", { method: "PUT", body: { enabled: "true" } }, 400);
  const enabled = await exterior.request("/api/me/subscription", { method: "PUT", body: { enabled: true, email: "someone-else@example.com" } });
  assert.equal(enabled.json.enabled, true);
  assert.equal((await exterior.request("/api/auth/me")).json.user.mailSubscribed, true);
  await exterior.request("/api/me/subscription", { method: "PUT", body: { enabled: false } });
  await exterior.request("/api/auth/logout", { method: "POST", body: {} });
  await exterior.request("/api/auth/login", { method: "POST", body: { email: "reader@example.com", password: "test-password-123" } });
  assert.equal((await exterior.request("/api/me/subscription")).json.enabled, false);
  const savedCookie = exterior.cookie;
  await stop(exterior.child);
  const restarted = await start("exterior", exterior.root);
  restarted.cookie = savedCookie;
  assert.equal((await restarted.request("/api/me/subscription")).json.enabled, false, "Startup must preserve opt-out");
  const secondUser = await restarted.request("/api/auth/register", { method: "POST", body: { email: "optin@example.com", displayName: "Opt in", password: "test-password-123", mailSubscribed: true } }, 201);
  assert.equal(secondUser.json.user.mailSubscribed, true);
  const unprefixed = await fetch(`${restarted.base}/api/config`);
  assert.equal((await unprefixed.json()).id, "exterior", "Prefix-stripped proxy requests retain edition");
  console.log("Edition tests passed: guest access, opt-in/out, restart persistence, isolated cookies/DB/metrics and legacy defaults.");
}

main().catch((error) => { console.error(error); process.exitCode = 1; }).finally(async () => {
  await Promise.all(children.map(stop));
  for (const root of roots) {
    if (path.dirname(path.resolve(root)) !== path.resolve(os.tmpdir()) || !path.basename(root).startsWith("dailynews-editions-")) throw new Error("Unsafe test cleanup path");
    fs.rmSync(root, { recursive: true, force: true });
  }
});
