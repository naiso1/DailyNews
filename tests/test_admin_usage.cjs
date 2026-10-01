"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const script = fs.readFileSync(path.join(__dirname, "..", "dailynews_account.js"), "utf8");

function fixture(edition) {
  const requests = [], docEvents = {}, windowEvents = {};
  const list = { innerHTML: "", querySelector: () => ({addEventListener() {}}), querySelectorAll: () => [] };
  const document = {hidden: false, visibilityState: "visible", documentElement: {classList: {contains: () => false}},
    getElementById: id => id === "accountActivityList" ? list : null,
    addEventListener: (event, callback) => { docEvents[event] = callback; }};
  const window = {DAILYNEWS_CONFIG: {id: edition, apiBase: edition === "exterior" ? "/exterior/api" : "/api", sharedIdentity: true},
    location: {search: "?admin=1"}, addEventListener: (event, callback) => { windowEvents[event] = callback; }};
  const usage = {startedAt: "2026-09-30 16:00:00", today: {users: 2, visits: 3}, last7Days: {users: 2, visits: 7}, last30Days: {users: 2, visits: 8}, totalVisits: 100,
    daily: [{date: "2026-10-01", users: 2, visits: 3}, {date: "2026-09-30", users: 0, visits: 4}]};
  let fail = false, isAdmin = true;
  const context = vm.createContext({window, document, URLSearchParams, console,
    fetch: async (url, options) => {
      requests.push({url, options});
      return {ok: !fail, status: fail ? 503 : 200,
        json: async () => url.endsWith("/auth/me") ? {user: {id: 12, isAdmin}} : {edition: {id: edition}, totals: {}, usage}};
    }});
  const run = code => vm.runInContext(code, context);
  run(script);
  run('accountState.user = {id: 12, isAdmin: true}; accountState.authResolved = true; renderEditorialAdmin = async () => {};');
  return {run, document, window, requests, docEvents, windowEvents, list,
    setFail: value => { fail = value; }, setAdmin: value => { isAdmin = value; }};
}

async function main() {
  for (const edition of ["interior", "exterior"]) {
    const f = fixture(edition), base = edition === "exterior" ? "/exterior/api" : "/api";
    await f.run("renderAdminPanel()");
    assert.equal(f.requests[0].url, `${base}/admin/overview`);
    assert.match(f.list.innerHTML, new RegExp(`${edition === "exterior" ? "外装" : "内装"}版の利用状況`));
    assert.match(f.list.innerHTML, /href="\/\?admin=1"/);
    assert.match(f.list.innerHTML, /href="\/exterior\/\?admin=1"/);
    assert.equal((f.list.innerHTML.match(/aria-current="page"/g) || []).length, 1);
    assert.match(f.list.innerHTML, /2026-09-30<\/td><td>計測前/);
    assert.match(f.list.innerHTML, /2026-10-01<\/td><td>2人/);
    assert(!f.requests.some(request => request.url.endsWith("/me/usage")), "Rendering a report must not count as use");
    f.requests.length = 0;
    f.document.hidden = true;
    await f.run("recordEditionUsage()");
    assert.equal(f.requests.length, 0, "Background tabs are not counted");
    f.document.hidden = false;
    await f.run("recordEditionUsage()");
    await f.run("recordEditionUsage()");
    assert.equal(f.requests.length, 1, "Duplicate foreground events are throttled");
    assert.equal(f.requests[0].url, `${base}/me/usage`);
    assert.equal(f.requests[0].options.method, "POST");
    f.run("accountUsageLastSent -= 61000");
    await f.docEvents.pointerdown();
    assert.equal(f.requests.length, 2, "Actual activity extends edition-local last use");
    f.run("accountState.user = null");
    await f.docEvents.keydown();
    assert.equal(f.requests.length, 2, "Guests do not create authenticated usage");
    f.run("accountState.user = {id: 13};");
    f.setFail(true);
    await f.run("recordEditionUsage()");
    f.setFail(false);
    await f.run("recordEditionUsage()");
    assert.equal(f.requests.length, 4, "A changed user or failed request must not be suppressed");
    f.run(`injectAccountUi = () => {}; updateRegistrationPrompt = () => {}; updateAccountButton = () => {};
      afterAuthentication = async () => {}; openAccountTab = tab => { window.openedTab = tab; };`);
    await f.run("initializeAccount()");
    assert.equal(f.window.openedTab, "admin", "Edition link opens destination management after authentication");
    f.window.openedTab = null;
    f.setAdmin(false);
    await f.run("initializeAccount()");
    assert.equal(f.window.openedTab, null, "URL parameter cannot grant administrator access");
  }
  console.log("Edition admin UI: API scoping, links, start date, foreground tracking, throttling, retry and admin routing PASS");
}
main().catch(error => { console.error(error); process.exitCode = 1; });
