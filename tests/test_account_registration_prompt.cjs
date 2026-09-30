const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const script = fs.readFileSync(path.join(__dirname, '..', 'dailynews_account.js'), 'utf8');

function fixture(edition, sharedIdentity = true) {
  function element() {
    const classes = new Set();
    return {style: {}, listeners: {}, children: new Map(), renderCount: 0,
      classList: {contains: name => classes.has(name), add: name => classes.add(name),
        remove: name => classes.delete(name),
        toggle(name, enabled) { if (enabled) classes.add(name); else classes.delete(name); }},
      set innerHTML(value) { this.html = value; this.children.clear(); this.renderCount++; },
      get innerHTML() { return this.html || ''; },
      querySelector(selector) {
        assert(selector.startsWith('#'));
        if (!this.innerHTML.includes(`id="${selector.slice(1)}"`)) return null;
        if (!this.children.has(selector)) this.children.set(selector, element());
        return this.children.get(selector);
      },
      addEventListener(name, listener) { this.listeners[name] = listener; },
    };
  }
  const overlay = element(), body = element(), title = element(), button = element();
  const nodes = {accountOverlay: overlay, accountBody: body, accountTitle: title, accountOpenButton: button};
  const document = {body: element(), documentElement: element(), getElementById: id => nodes[id], addEventListener() {}};
  const window = {DAILYNEWS_CONFIG: {id: edition, allowGuestRead: edition === 'exterior', sharedIdentity},
    addEventListener() {}, dispatchEvent() {}};
  const context = vm.createContext({window, document, console, CustomEvent: class {},
    localStorage: {getItem() { return null; }, setItem() {}, removeItem() {}},
    fetch: async () => ({ok: true, json: async () => ({})}),
  });
  vm.runInContext(script, context);
  return {overlay, body, title, document, run: code => vm.runInContext(code, context)};
}

async function main() {
  for (const edition of ['interior', 'exterior']) {
    for (const sharedIdentity of [true, false]) {
      const f = fixture(edition, sharedIdentity);
      f.run('updateRegistrationPrompt()');
      assert(!f.overlay.classList.contains('open'), 'wait for session lookup');
      f.run('accountState.authResolved = true; updateRegistrationPrompt()');
      assert(f.overlay.classList.contains('open'), `${edition}: unauthenticated visitors see welcome`);
      assert.equal(f.overlay.classList.contains('auth-required'), edition === 'interior');
      assert.equal(f.title.textContent, 'IE開発デイリーニュースをご利用の方へ');
      assert.match(f.body.innerHTML, /TG社員・派遣社員の方は誰でも登録可能です。/);

      f.body.querySelector('#accountStartRegister').listeners.click();
      assert.equal(f.title.textContent, '新規登録');
      assert.match(f.body.innerHTML, /TG社員・派遣社員の方は誰でも登録可能です。/);
      const form = f.body.querySelector('#accountAuthForm');
      form.draft = '入力中の表示名';
      f.run('updateRegistrationPrompt()');
      assert.equal(f.body.querySelector('#accountAuthForm'), form, 'session updates must preserve the form and input');
      assert.equal(form.draft, '入力中の表示名');
      if (sharedIdentity) {
        const interior = f.body.innerHTML.match(/<input name="subscriptionInterior"[^>]*>/)[0];
        const exterior = f.body.innerHTML.match(/<input name="subscriptionExterior"[^>]*>/)[0];
        assert.equal(interior.includes('checked'), edition === 'interior');
        assert(!exterior.includes('checked'), 'exterior mail remains opt-in');
      } else if (edition === 'exterior') {
        assert(!f.body.innerHTML.match(/<input name="mailSubscribed"[^>]*>/)[0].includes('checked'));
      }

      f.run('renderAuth("welcome")');
      const guest = f.body.querySelector('#accountContinueGuest');
      if (edition === 'exterior') {
        guest.listeners.click();
        assert(!f.overlay.classList.contains('open'));
        assert.equal(f.document.body.style.overflow, '');
        f.run('updateRegistrationPrompt()');
        assert(!f.overlay.classList.contains('open'), 'dismissed prompt must stay closed on the current page');
        await f.run('openAccount("login")');
        assert(f.overlay.classList.contains('open'), 'manual login is still available');
        assert.equal(f.title.textContent, 'ログイン');
        const count = f.body.renderCount;
        f.run('updateRegistrationPrompt()');
        assert.equal(f.body.renderCount, count);
      } else {
        assert.equal(guest, null);
        f.run('closeAccount()');
        assert(f.overlay.classList.contains('open'), 'interior still requires login');
      }

      f.run('accountState.user = {id: 1, displayName: "利用者"}; updateRegistrationPrompt()');
      assert(!f.overlay.classList.contains('open'));
      assert(!f.overlay.classList.contains('auth-required'));
      await f.run('logoutAccount()');
      assert(f.overlay.classList.contains('open'), 'logout shows a fresh welcome, not stale account details');
      assert.equal(f.title.textContent, 'IE開発デイリーニュースをご利用の方へ');
    }
    const signedIn = fixture(edition);
    signedIn.run('accountState.authResolved = true; accountState.user = {id: 1}; updateRegistrationPrompt()');
    assert(!signedIn.overlay.classList.contains('open'), 'existing signed-in visitors see no registration prompt');
    assert.equal(signedIn.body.renderCount, 0);
  }
  console.log('Registration prompt: both editions, session states, dismissal, form preservation, logout, copy and mail opt-in PASS');
}
main().catch(error => { console.error(error); process.exitCode = 1; });
