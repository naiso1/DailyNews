'use strict';

// In-memory filesystem, browser/context doubles, and a fake encryption boundary.
// Never read auth.bin, start Edge, invoke DPAPI, or contact an image provider.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

const code = fs.readFileSync(path.join(__dirname, '../deployment/workstation/exabase/worker.js'), 'utf8');

function fixture(options = {}) {
  const runtime = path.join('C:/session-test-only', 'DailyNewsRuntime', 'exabase');
  const auth = path.join(runtime, 'auth.bin');
  const files = new Map([[auth, Buffer.from('old-encrypted-test-state')]]);
  const emitted = [];
  const events = [];
  const previous = { cookies: [{ name: 'test-session', value: 'old-fixture' }], origins: [] };
  const refreshed = { cookies: [{ name: 'test-session', value: 'updated-fixture' }], origins: [] };
  let storedSnapshots = 0;
  let closed = 0;
  const fakeFs = {
    existsSync: file => files.has(file),
    writeFileSync: (file, bytes) => { files.set(file, Buffer.from(bytes)); events.push('write-encrypted'); },
    renameSync: (source, target) => {
      if (options.failRename) throw new Error('simulated disk failure');
      files.set(target, files.get(source)); files.delete(source); events.push('save');
    },
    unlinkSync: file => files.delete(file),
  };
  const page = {
    goto: async () => events.push('navigate'),
    url: () => options.unauthenticated ? 'https://login.microsoftonline.com/test' : 'https://gai.exabase.ai/conversation',
  };
  const browser = {
    newContext: async config => {
      assert.equal(config.storageState, previous);
      return { newPage: async () => page, storageState: async () => { storedSnapshots += 1; return refreshed; } };
    },
    close: async () => { closed += 1; },
  };
  const dependencies = {
    edge: 'never-launched-test-edge',
    chromium: { launch: async () => browser },
    engine: { _test: { visibleChatInput: async () => true } },
  };
  function fakeRequire(name) {
    if (name === 'node:fs') return fakeFs;
    if (name === 'node:child_process') return { spawn: () => { throw new Error('No real process allowed'); } };
    return require(name);
  }
  fakeRequire.main = {};
  const context = vm.createContext({
    require: fakeRequire, module: { exports: {} }, Buffer, setTimeout, clearTimeout,
    process: { env: { LOCALAPPDATA: 'C:/session-test-only' }, pid: 12345,
      argv: ['node', 'worker', options.mode || '--generate'],
      stdout: { write: value => emitted.push(value) } },
  });
  vm.runInContext(code, context, { filename: 'worker-session-under-test.js' });
  context.dpapi = async (plain, protect) => {
    assert.equal(protect, true);
    assert.deepEqual(JSON.parse(plain.toString('utf8')), refreshed);
    if (options.failEncryption) throw new Error('simulated encryption failure');
    events.push('encrypt');
    return Buffer.from('new-encrypted-test-state');
  };
  context.runtime = () => dependencies;
  context.sessionState = async () => previous;
  context.acquireLock = () => { events.push('lock'); return () => events.push('unlock'); };
  context.readRequest = async () => ({ fixtureRequest: true });
  context.generate = async (receivedDependencies, request, state) => {
    assert.equal(receivedDependencies, dependencies);
    assert.equal(request.fixtureRequest, true);
    assert.equal(state, refreshed);
    assert.notEqual(state, previous);
    assert.equal(files.get(auth).toString(), 'new-encrypted-test-state');
    assert.equal(events.includes('unlock'), false);
    events.push('generate');
  };
  return { context, files, auth, refreshed, emitted, events,
    snapshots: () => storedSnapshots, closed: () => closed };
}

test('successful check saves refreshed state and passes it to generation under the worker lock', async () => {
  const f = fixture();
  await vm.runInContext('main()', f.context);
  assert.deepEqual(f.events, ['lock', 'navigate', 'encrypt', 'write-encrypted', 'save', 'generate', 'unlock']);
  assert.equal(f.snapshots(), 1);
  assert.equal(f.closed(), 1);
  assert.equal(f.files.size, 1);
  assert.equal(f.emitted.join(''), '');
});

test('check-session alone persists refreshed state without starting generation or exposing it', async () => {
  const f = fixture({ mode: '--check-session' });
  await vm.runInContext('main()', f.context);
  assert.equal(f.files.get(f.auth).toString(), 'new-encrypted-test-state');
  assert.equal(f.events.includes('generate'), false);
  assert.deepEqual(f.emitted.map(line => JSON.parse(line)), [{ status: 'AUTHENTICATED' }]);
});

test('failed authentication keeps the old encrypted session and releases the lock', async () => {
  const f = fixture({ unauthenticated: true });
  await assert.rejects(vm.runInContext('main()', f.context), error => error.safeCode === 'AUTH_REQUIRED');
  assert.equal(f.files.get(f.auth).toString(), 'old-encrypted-test-state');
  assert.equal(f.snapshots(), 0);
  assert.deepEqual(f.events, ['lock', 'navigate', 'unlock']);
  assert.equal(f.closed(), 1);
});

for (const failure of ['failEncryption', 'failRename']) {
  test(`${failure} preserves the original session and does not invoke generation`, async () => {
    const f = fixture({ [failure]: true });
    await assert.rejects(vm.runInContext('main()', f.context));
    assert.equal(f.files.get(f.auth).toString(), 'old-encrypted-test-state');
    assert.equal(f.files.size, 1);
    assert.equal(f.events.includes('generate'), false);
    assert.equal(f.events.at(-1), 'unlock');
    assert.equal(f.closed(), 1);
    assert.equal(f.emitted.join(''), '');
  });
}
