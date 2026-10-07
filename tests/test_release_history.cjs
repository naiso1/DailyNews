const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const script = fs.readFileSync(path.join(__dirname, '..', 'release_history.js'), 'utf8');
const sample = (title = '新しい機能') => ({date: '2026-10-07', title, items: ['改善しました']});

function fixture({edition = 'interior', user = {id: 1, identityId: 10}, ready = true,
  cache = new Map(), remote = [], entries, migration = false, fail = false, block = false} = {}) {
  const nodes = new Map(), timers = new Map(), requests = [];
  let nextTimer = 0, document;
  function events(target = {}) {
    target.listeners = {};
    target.addEventListener = (name, fn) => (target.listeners[name] ||= []).push(fn);
    target.emit = (name, event = {}) => { for (const fn of target.listeners[name] || []) fn(event); };
    return target;
  }
  function element() {
    const classes = new Set(), children = new Map();
    return events({style: {}, childNodes: [], hidden: false,
      classList: {contains: n => classes.has(n), add: n => classes.add(n), remove: n => classes.delete(n)},
      appendChild(node) { this.childNodes.push(node); if (node.id) nodes.set(node.id, node); },
      insertBefore(node) { this.appendChild(node); },
      querySelector(selector) { if (!children.has(selector)) children.set(selector, element()); return children.get(selector); },
      getClientRects() { return []; },
      focus() { document.activeElement = this; }, matches() { return false; },
    });
  }
  const actions = element(), body = element(), head = element(), root = element(), blocker = element();
  blocker.getClientRects = () => block ? [{}] : [];
  if (migration) root.classList.add('github-pages-migration');
  document = events({head, body, documentElement: root, activeElement: element(), hidden: false,
    createElement: element, getElementById: id => nodes.get(id),
    querySelector: selector => selector === '.header-top-actions' ? actions : null,
    querySelectorAll: selector => selector.includes('role=') ? [blocker] : []});
  const account = {user, ready};
  const window = events({DAILYNEWS_CONFIG: {id: edition, sharedIdentity: true, allowGuestRead: edition === 'exterior',
    apiBase: edition === 'exterior' ? '/exterior/api' : '/api'}, dailyNewsAccount: account});
  const context = vm.createContext({window, document, console, AbortController,
    localStorage: {getItem: key => { if (cache === null) throw Error('storage blocked'); return cache.get(key) || null; },
      setItem: (key, val) => { if (cache === null) throw Error('storage blocked'); cache.set(key, val); }},
    setTimeout(fn, ms) { const id = ++nextTimer; timers.set(id, {fn, ms}); return id; },
    clearTimeout: id => timers.delete(id),
    MutationObserver: class { constructor(fn) { this.fn = fn; } observe() {} },
    fetch: async (url, options) => {
      requests.push({url, ...options});
      if (fail) throw Error('offline');
      const payload = options.body ? JSON.parse(options.body) : null;
      if (payload) remote = [...new Set([...remote, ...payload.seen])];
      return {ok: true, json: async () => ({userId: account.user?.identityId, seen: remote})};
    },
  });
  vm.runInContext(script, context);
  if (entries) window.DAILYNEWS_RELEASE_HISTORY = entries;
  document.emit('DOMContentLoaded');
  const overlay = nodes.get('releaseHistoryOverlay');
  return {window, account, nodes, document, context, cache, requests, actions, head, overlay,
    key: entry => { context.entry = entry; return vm.runInContext('releaseEntryKey(entry)', context); },
    open: () => Boolean(overlay?.classList.contains('open')),
    confirm: () => overlay.querySelector('.release-history-confirm').emit('click'),
    list: () => overlay.querySelector('.release-history-list').innerHTML,
    unblock: () => { block = false; window.emit('dailynews:account-dialog-closed'); },
    async settle() {
      for (let i = 0; i < 4; i++) {
        await new Promise(resolve => setImmediate(resolve));
        for (const [id, timer] of [...timers]) if (timer.ms === 180) { timers.delete(id); timer.fn(); }
      }
    },
  };
}

async function main() {
  for (const edition of ['interior', 'exterior']) {
    const f = fixture({edition}); await f.settle();
    assert(f.open(), 'unread updates open after account resolution');
    assert.match(f.list(), /未読のシステム更新をアクセス時に表示/);
    assert(!f.list().includes('2026-09-30'), 'old history does not flood first notice');
    assert.equal(f.requests.filter(r => r.method === 'PUT').length, 0, 'opening is not acknowledgement');
    f.confirm(); await f.settle();
    assert(!f.open()); assert.equal(f.document.body.style.overflow, '');
    assert.equal(f.requests.filter(r => r.method === 'PUT').length, 1);
    assert.equal(f.requests.at(-1).url, `${edition === 'exterior' ? '/exterior' : ''}/api/me/release-history`);
    f.nodes.get('releaseHistoryButton').emit('click');
    assert.match(f.list(), /TG社員・派遣社員の方は誰でも登録可能です。/);
    assert.match(f.list(), /39キーワード/); assert.match(f.list(), /2026-09-30/);
    f.overlay.emit('keydown', {key: 'Escape', preventDefault() {}}); assert(!f.open());
    f.document.emit('DOMContentLoaded'); assert.equal(f.actions.childNodes.length, 1); assert.equal(f.head.childNodes.length, 1);
    f.nodes.get('releaseHistoryButton').emit('click'); f.overlay.emit('click', {target: f.overlay}); assert(!f.open());
  }
  const first = fixture({entries: [sample()]}); await first.settle(); first.confirm(); await first.settle();
  const acknowledged = JSON.parse(first.requests.at(-1).body).seen;
  const otherDevice = fixture({edition: 'exterior', remote: acknowledged, entries: [sample()]});
  await otherDevice.settle(); assert(!otherDevice.open(), 'same account is read on another edition/device');
  const anotherUser = fixture({cache: first.cache, user: {id: 2, identityId: 20}, entries: [sample()]});
  await anotherUser.settle(); assert(anotherUser.open(), 'same browser does not mix accounts');
  const revised = fixture({remote: acknowledged, entries: [sample('同日追記'), sample()]});
  await revised.settle(); assert(revised.open()); assert.match(revised.list(), /同日追記/);
  assert(!revised.list().includes('新しい機能'), 'show only unread entries');
  assert.notEqual(revised.key(sample()), revised.key({...sample(), items: ['内容を訂正']}), 'same-day content changes are detected');
  const empty = fixture({entries: []}); await empty.settle(); assert(!empty.open());
  const old = fixture({entries: [{...sample(), date: '2026-10-06'}]}); await old.settle(); assert(!old.open());
  const pending = fixture({ready: false}); await pending.settle(); assert(!pending.open()); assert.equal(pending.requests.length, 0);
  pending.account.ready = true; pending.window.emit('dailynews:account-ready'); await pending.settle(); assert(pending.open());
  const typing = fixture({block: true}); await typing.settle(); assert(!typing.open());
  typing.document.activeElement = {matches: () => true}; typing.unblock(); await typing.settle(); assert(!typing.open(), 'input focus defers automatic modal');
  typing.document.activeElement = null; typing.document.emit('focusout'); await typing.settle(); assert(typing.open());
  const draft = fixture();
  const draftInput = {value: 'コメントを作成中', getClientRects: () => [{}]};
  draft.document.querySelectorAll = selector => selector.includes('role=') ? [] : [draftInput];
  await draft.settle(); assert(!draft.open(), 'an unfocused unsent comment also defers the notice');
  draftInput.value = ''; draft.document.emit('focusout'); await draft.settle(); assert(draft.open());
  const guest = fixture({edition: 'exterior', user: null, entries: [sample()]}); await guest.settle(); assert(guest.open());
  guest.confirm(); await guest.settle(); assert.equal(guest.requests.length, 0);
  const returningGuest = fixture({edition: 'exterior', user: null, cache: guest.cache, entries: [sample()]});
  await returningGuest.settle(); assert(!returningGuest.open());
  const guestLogin = fixture({cache: guest.cache, entries: [sample()]}); await guestLogin.settle(); assert(guestLogin.open(), 'guest history is not assigned to a signed-in person');
  const requiredLogin = fixture({user: null}); await requiredLogin.settle(); assert(!requiredLogin.open());
  const offline = fixture({cache: first.cache, entries: [sample()], fail: true}); await offline.settle(); assert(!offline.open(), 'account cache covers temporary outages');
  const noStorage = fixture({edition: 'exterior', user: null, cache: null, entries: [sample()]});
  await noStorage.settle(); assert(noStorage.open()); noStorage.confirm(); await noStorage.settle();
  noStorage.window.emit('focus'); await noStorage.settle(); assert(!noStorage.open(), 'blocked storage still remembers within page');
  const changedAccount = fixture({entries: [sample()]}); await changedAccount.settle();
  changedAccount.account.user = {id: 2, identityId: 20}; changedAccount.confirm(); await changedAccount.settle();
  assert.equal(changedAccount.requests.filter(r => r.method === 'PUT').length, 0, 'stale dialog cannot acknowledge another account');
  assert.equal(fixture({migration: true}).nodes.has('releaseHistoryButton'), false);
  console.log('Release history PASS: unread-only, same-day changes, account/device/edition isolation, guest fallback, input deferral, acknowledgement, outage, empty history and manual access.');
}
main().catch(error => { console.error(error); process.exitCode = 1; });
