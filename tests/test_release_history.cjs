const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const script = fs.readFileSync(path.join(__dirname, '..', 'release_history.js'), 'utf8');

function fixture(edition, migration = false) {
  const nodes = new Map();
  function element() {
    const classes = new Set();
    return {style: {}, children: [], listeners: {}, classList: {
      contains: name => classes.has(name), add: name => classes.add(name), remove: name => classes.delete(name),
    }, appendChild(node) { this.children.push(node); if (node.id) nodes.set(node.id, node); },
    insertBefore(node) { this.appendChild(node); },
    addEventListener(event, handler) { this.listeners[event] = handler; },
    querySelector(selector) { assert.equal(selector, '.release-history-close'); return this.close ||= element(); }};
  }
  const actions = element(), body = element(), head = element(), root = element();
  if (migration) root.classList.add('github-pages-migration');
  const document = {head, body, documentElement: root,
    createElement: element, getElementById: id => nodes.get(id),
    querySelector: selector => selector === '.header-top-actions' ? actions : null,
    addEventListener(name, handler) { assert.equal(name, 'DOMContentLoaded'); this.ready = handler; }};
  const context = vm.createContext({window: {DAILYNEWS_CONFIG: {id: edition}}, document});
  vm.runInContext(script, context);
  document.ready();
  return {nodes, actions, body, head, document, context};
}

for (const edition of ['interior', 'exterior']) {
  const f = fixture(edition);
  const button = f.nodes.get('releaseHistoryButton'), overlay = f.nodes.get('releaseHistoryOverlay');
  assert(button, `${edition}: history entry point is visible`);
  assert.equal(button.textContent, '更新履歴');
  assert.equal(f.context.window.DAILYNEWS_RELEASE_HISTORY[0].title, 'AI生成イメージの表示と生成指定を1:1に統一');
  assert.equal(f.context.window.DAILYNEWS_RELEASE_HISTORY[0].date, '2026-10-05');
  assert.match(overlay.innerHTML, /TG社員・派遣社員の方は誰でも登録可能です。/);
  assert.match(overlay.innerHTML, /39キーワード/);
  assert.match(overlay.innerHTML, /2026-09-30/);
  assert.match(overlay.innerHTML, /外装版でもヘッダー/);
  button.listeners.click();
  assert(overlay.classList.contains('open'));
  assert.equal(f.body.style.overflow, 'hidden');
  overlay.close.listeners.click();
  assert(!overlay.classList.contains('open'));
  assert.equal(f.body.style.overflow, '');
  button.listeners.click();
  overlay.listeners.click({target: overlay});
  assert(!overlay.classList.contains('open'));
  f.document.ready();
  assert.equal(f.actions.children.length, 1, 'initialization must not duplicate the button');
  assert.equal(f.head.children.length, 1);
}
assert.equal(fixture('exterior', true).nodes.has('releaseHistoryButton'), false);
console.log('Release history: both editions, latest entry, open/close and duplicate initialization PASS');
