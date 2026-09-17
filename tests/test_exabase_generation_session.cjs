'use strict';

// Only synthetic state, an in-memory filesystem, and browser/engine doubles.
// No real auth files, DPAPI, browser, network, or image generation are used.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

const code = fs.readFileSync(path.join(__dirname, '../deployment/workstation/exabase/worker.js'), 'utf8');

function fixture(options = {}) {
  const runtime = path.join('C:/generation-session-test-only', 'DailyNewsRuntime', 'exabase');
  const auth = path.join(runtime, 'auth.bin');
  const outputDir = path.resolve('C:/generation-session-test-only/output');
  const image = path.join(outputDir, 'fixture.png');
  const files = new Map([[auth, Buffer.from('old-encrypted-fixture')]]);
  const events = [], emitted = [];
  const state = { cookies: [], origins: [] };
  const refreshed = { cookies: [{ name: 'fixture', value: 'updated-fixture' }], origins: [{
    origin: 'https://example.test', localStorage: [{ name: 'fixture', value: 'local-fixture' }],
    indexedDB: [{ name: 'fixture-db', version: 1, stores: [] }],
  }] };
  const request = { key: 'a'.repeat(64), prompt: 'synthetic test prompt', outputDir, timeoutMs: 45000 };
  let pageClosed = false, signedOut = Boolean(options.signedOut);
  let timeoutCallback, cancellationCheck, snapshots = 0, closeCount = 0;
  const page = {
    goto: async (url, settings) => {
      assert.equal(url, 'https://gai.exabase.ai/conversation');
      assert.equal(settings.waitUntil, 'domcontentloaded');
      assert.equal(settings.timeout, 60000);
      events.push('navigate');
    },
    url: () => signedOut ? 'https://login.microsoftonline.com/test' : 'https://gai.exabase.ai/conversation',
    isClosed: () => pageClosed,
  };
  const browserContext = {
    newPage: async () => page,
    storageState: async settings => {
      assert.equal(settings.indexedDB, true);
      snapshots += 1; events.push('snapshot');
      if (options.failSnapshot) throw new Error('private fixture snapshot error');
      if (options.signOutDuringSnapshot) signedOut = true;
      return refreshed;
    },
  };
  const browser = {
    newContext: async settings => {
      assert.equal(settings.storageState, state);
      assert.equal(settings.viewport.width, 1440);
      assert.equal(settings.viewport.height, 1000);
      return browserContext;
    },
    close: async () => { pageClosed = true; closeCount += 1; events.push('close'); },
  };
  const dependencies = {
    edge: 'never-launched-edge-fixture',
    chromium: { launch: async settings => {
      assert.equal(settings.executablePath, 'never-launched-edge-fixture');
      assert.equal(settings.headless, true);
      events.push('launch'); return browser;
    } },
    engine: {
      generateBatch: async () => { throw new Error('Legacy lifecycle must not be used'); },
      _test: {
        visibleChatInput: async received => {
          assert.equal(received, page);
          return !options.noChatInput;
        },
        watchCancellation: (receivedBrowser, isCancelled) => {
          assert.equal(receivedBrowser, browser);
          cancellationCheck = isCancelled;
          events.push('watch');
          return () => events.push('stop-watch');
        },
        generateOnPage: async (receivedPage, settings) => {
          assert.equal(receivedPage, page);
          assert.equal(settings.prompt, request.prompt);
          assert.equal(settings.outputDir, outputDir);
          assert.equal(settings.count, 1);
          assert.equal(settings.timeoutMs, 45000);
          assert.equal(settings.isCancelled(), false);
          events.push('generate');
          for (const status of ['preparing', 'sending', 'submitted']) {
            settings.onProgress({ status, message: 'private provider fixture diagnostic' });
          }
          if (options.cancel) {
            timeoutCallback();
            assert.equal(cancellationCheck(), true);
            assert.equal(settings.isCancelled(), true);
            await browser.close(); // The pinned cancellation watcher closes it.
            throw new Error('private fixture cancellation');
          }
          if (options.generationError) throw new Error('private fixture generation error');
          files.set(image, Buffer.from('synthetic image fixture'));
          if (options.closedPage) pageClosed = true;
          settings.onProgress({ status: 'done', filePath: image });
          return { files: [image], errors: [] };
        },
      },
    },
  };
  const fakeFs = {
    mkdirSync: () => {},
    existsSync: file => files.has(file),
    writeFileSync: (file, bytes) => {
      assert.equal(/session-\d+\.json$/.test(file), false, 'state stays in memory');
      files.set(file, Buffer.from(bytes));
    },
    renameSync: (source, target) => {
      if (target === auth && options.failRename) throw new Error('private fixture disk error');
      files.set(target, files.get(source)); files.delete(source);
      events.push(target === auth ? 'save-auth' : path.basename(target));
    },
    unlinkSync: file => files.delete(file),
  };
  function fakeRequire(name) {
    if (name === 'node:fs') return fakeFs;
    if (name === 'node:child_process') return { spawn: () => { throw new Error('No real process allowed'); } };
    return require(name);
  }
  fakeRequire.main = {};
  const context = vm.createContext({
    require: fakeRequire, module: { exports: {} }, Buffer,
    setTimeout: callback => { timeoutCallback = callback; return 1; },
    clearTimeout: () => events.push('clear-timeout'),
    process: { env: { LOCALAPPDATA: 'C:/generation-session-test-only' }, pid: 12345,
      argv: ['node', 'worker', '--generate'], stdout: { write: value => emitted.push(JSON.parse(value)) } },
  });
  vm.runInContext(code, context, { filename: 'worker-generation-under-test.js' });
  context.runtime = () => dependencies;
  context.sessionState = async () => state;
  context.checkSession = async () => state;
  context.acquireLock = () => { events.push('lock'); return () => events.push('unlock'); };
  context.readRequest = async () => request;
  context.dpapi = async (plain, protect) => {
    assert.equal(protect, true);
    assert.deepEqual(JSON.parse(plain.toString('utf8')), refreshed);
    assert.equal(events.includes('unlock'), false, 'saving stays under the worker lock');
    assert.equal(pageClosed, false, 'capture/encryption precedes browser close');
    events.push('encrypt');
    if (options.failEncryption) throw new Error('private fixture encryption error');
    return Buffer.from('new-encrypted-fixture');
  };
  return { context, files, auth, outputDir, events, emitted, request,
    run: () => vm.runInContext('main()', context),
    snapshots: () => snapshots, closes: () => closeCount };
}

function assertDone(f) {
  const receipt = JSON.parse(f.files.get(path.join(f.outputDir, 'result.json')).toString());
  assert.equal(receipt.status, 'DONE');
  assert.equal(receipt.key, f.request.key);
  // Python selects the last event containing status; warnings must not replace it.
  assert.equal(f.emitted.filter(value => 'status' in value).at(-1).status, 'DONE');
  assert.equal(JSON.stringify(f.emitted).includes('private'), false);
  assert.equal(JSON.stringify(f.emitted).includes('updated-fixture'), false);
}

test('generation saves updated cookies/localStorage/IndexedDB after durable DONE and before close', async () => {
  const f = fixture();
  await f.run();
  assertDone(f);
  assert.equal(f.files.get(f.auth).toString(), 'new-encrypted-fixture');
  assert.equal(f.snapshots(), 1);
  assert.equal(f.closes(), 1);
  assert.ok(f.events.indexOf('result.json') < f.events.indexOf('snapshot'));
  assert.ok(f.events.indexOf('save-auth') < f.events.indexOf('close'));
  assert.ok(f.events.indexOf('stop-watch') < f.events.indexOf('close'));
  assert.equal(f.events.at(-1), 'unlock');
  assert.equal([...f.files.keys()].some(file => file.endsWith('.tmp')), false);
});

for (const failure of ['failSnapshot', 'failEncryption', 'failRename']) {
  test(`${failure} retains DONE and previous auth with a safe warning`, async () => {
    const f = fixture({ [failure]: true });
    await f.run();
    assertDone(f);
    assert.equal(f.files.get(f.auth).toString(), 'old-encrypted-fixture');
    assert.deepEqual(f.emitted.at(-1), { event: 'warning', code: 'SESSION_REFRESH_FAILED', key: f.request.key });
    assert.equal(f.closes(), 1);
    assert.equal(f.events.at(-1), 'unlock');
    assert.equal([...f.files.keys()].some(file => file.endsWith('.tmp')), false);
  });
}

for (const condition of ['signedOut', 'noChatInput', 'closedPage', 'signOutDuringSnapshot']) {
  test(`${condition} cannot overwrite saved authentication`, async () => {
    const f = fixture({ [condition]: true });
    await f.run();
    assertDone(f);
    assert.equal(f.files.get(f.auth).toString(), 'old-encrypted-fixture');
    assert.equal(f.events.includes('encrypt'), false);
    assert.equal(f.snapshots(), condition === 'signOutDuringSnapshot' ? 1 : 0);
    assert.equal(f.closes(), 1);
  });
}

test('cancellation preserves prior auth, reports timeout, stops watcher, and closes browser', async () => {
  const f = fixture({ cancel: true });
  await assert.rejects(f.run(), error => error.safeCode === 'GENERATION_TIMEOUT');
  assert.equal(f.files.get(f.auth).toString(), 'old-encrypted-fixture');
  assert.equal(f.snapshots(), 0);
  assert.equal(f.files.has(path.join(f.outputDir, 'result.json')), false);
  assert.equal(f.events.includes('stop-watch'), true);
  assert.equal(f.closes(), 2);
  assert.equal(f.events.at(-1), 'unlock');
});

test('a generation error still preserves a legitimately refreshed authenticated session', async () => {
  const f = fixture({ generationError: true });
  await assert.rejects(f.run(), /private fixture generation error/);
  assert.equal(f.files.get(f.auth).toString(), 'new-encrypted-fixture');
  assert.equal(f.files.has(path.join(f.outputDir, 'result.json')), false);
  assert.equal(f.snapshots(), 1);
  assert.equal(f.closes(), 1);
  assert.equal(f.events.at(-1), 'unlock');
});

test('session saving failure cannot hide an earlier generation failure', async () => {
  const f = fixture({ generationError: true, failEncryption: true });
  await assert.rejects(f.run(), /private fixture generation error/);
  assert.equal(f.files.get(f.auth).toString(), 'old-encrypted-fixture');
  assert.equal(f.files.has(path.join(f.outputDir, 'result.json')), false);
  assert.equal(f.emitted.at(-1).code, 'SESSION_REFRESH_FAILED');
  assert.equal(f.closes(), 1);
  assert.equal(f.events.at(-1), 'unlock');
});
