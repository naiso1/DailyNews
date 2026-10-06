'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');
const { selectImageModel, validatePriority } = require('../deployment/workstation/exabase/image-model');

function fixture(t, options = {}) {
  const outputDir = fs.mkdtempSync(path.join(os.tmpdir(), 'exa-model-test-'));
  t.after(() => fs.rmSync(outputDir, { recursive: true, force: true }));
  let clock = 0, open = false;
  const now = Date.now;
  Date.now = () => clock;
  t.after(() => { Date.now = now; });
  const events = [];
  const controls = [
    { id: 'nano-banana', name: '画像生成（高速, Nano Banana）', on: true },
    { id: 'gpt-image', name: '画像生成（高性能, GPT-image）', on: false },
  ].filter(item => item.id !== options.missing);
  function locator(items) {
    return {
      count: async () => items.length,
      nth: index => locator([items[index]]),
      first: () => locator(items.slice(0, 1)),
      isVisible: async () => Boolean(items.length && (items[0].tools || open)),
      isEnabled: async () => items[0].id !== options.disabled,
      click: async () => {
        const item = items[0];
        events.push(item.tools ? 'tools' : item.id);
        if (item.tools) open = true;
        else if (item.id !== options.stuck) item.on = !item.on;
        if (options.dual && item.id === 'gpt-image') controls[0].on = true;
      },
      evaluate: async fn => fn({ getAttribute: name => name === 'aria-checked'
        ? (options.unknown === items[0].id ? null : String(items[0].on)) : null }),
      and: () => locator([]), filter: () => locator([]), getByText: () => locator([]),
      locator: selector => selector === '..' ? locator(items) : locator(items),
    };
  }
  const page = {
    getByRole: (role, query = {}) => {
      if (role === 'button' && query.name?.test('ツール')) return locator([{ tools: true }]);
      if (role === 'switch' && !options.unlabeled) return locator(controls.filter(item => query.name.test(item.name)));
      return locator([]);
    },
    getByText: name => locator(options.unlabeled ? controls.filter(item => name.test(item.name)) : []),
    locator: () => locator([]), waitForTimeout: async ms => { clock += ms; },
    keyboard: { press: async key => { assert.equal(key, 'Escape'); open = false; } },
  };
  const engine = { _test: { dismissReleaseNotes: async () => {} } };
  return { page, engine, outputDir, controls, events,
    run: () => selectImageModel(page, ['gpt-image', 'nano-banana'], engine, outputDir) };
}

test('GPT-image wins over the first Nano row, switches are exclusive, and proof is recorded', async t => {
  const f = fixture(t);
  const result = await f.run();
  assert.equal(result.selected, 'gpt-image');
  assert.deepEqual(result.states, { 'gpt-image': true, 'nano-banana': false });
  assert.deepEqual(f.events, ['tools', 'nano-banana', 'gpt-image']);
  assert.equal(JSON.parse(fs.readFileSync(path.join(f.outputDir, 'model-selection.json'))).verified, true);
});

test('a text-labeled row works when the switch has no accessible model name', async t => {
  const f = fixture(t, { unlabeled: true });
  assert.equal((await f.run()).selected, 'gpt-image');
});

for (const reason of ['missing', 'disabled']) test(`Nano fallback only when GPT is ${reason} before sending`, async t => {
  const f = fixture(t, { [reason]: 'gpt-image' });
  const result = await f.run();
  assert.equal(result.selected, 'nano-banana');
  assert.equal(result.unavailable[0].model, 'gpt-image');
});

for (const option of ['stuck', 'unknown', 'dual']) test(`${option} toggle state prevents generation`, async t => {
  const f = fixture(t, { [option]: option === 'dual' ? true : 'gpt-image' });
  await assert.rejects(f.run(), error => error.safeCode === 'IMAGE_MODEL_NOT_ENABLED');
  assert.equal(fs.existsSync(path.join(f.outputDir, 'model-selection.json')), false);
});

test('rejects invalid and duplicate priority', () => {
  for (const value of [[], ['unknown'], ['gpt-image', 'gpt-image'], 'gpt-image']) {
    assert.throws(() => validatePriority(value), /INVALID_MODEL_CONFIG/);
  }
});

test('selected model is returned and uncertain send is never retried', async t => {
  const file = path.join(__dirname, '../deployment/workstation/exabase/model-generation.js');
  const f = fixture(t);
  let sent = 0;
  const events = [];
  const selection = { selected: 'gpt-image', verified: true };
  const module = { exports: {} };
  vm.runInNewContext(fs.readFileSync(file, 'utf8'), { module, URL, Date, require: name => {
    if (name === './image-model') return { selectImageModel: async () => selection };
    if (name === './reference-generation') return {
      waitForGeneratedImage: async () => ({ src: 'image' }), saveGeneratedImage: async () => 'image.png',
    };
    return require(name);
  } });
  let uncertain = false;
  const page = { url: () => 'https://gai.exabase.ai/conversation', locator: () => ({
    count: async () => 1, waitFor: async () => {}, isEnabled: async () => true,
    click: async () => { sent++; if (uncertain) throw Error('unknown delivery'); },
  }) };
  const engine = { _test: { startNewConversation: async () => {},
    visibleChatInput: async () => ({ fill: async () => {} }), collectPageImageSources: async () => [],
    getConversationIdentity: async () => '', waitForPromptSubmission: async () => {},
  } };
  const settings = { outputDir: f.outputDir, imageModels: ['gpt-image'], prompt: 'test', timeoutMs: 10000,
    isCancelled: () => false, onProgress: item => events.push(item.status) };
  const result = await module.exports.generateWithModel(page, settings, engine);
  assert.equal(result.modelSelection, selection);
  assert.equal(sent, 1);
  assert.deepEqual(events, ['sending', 'submitted', 'done']);
  uncertain = true;
  events.length = 0;
  await assert.rejects(module.exports.generateWithModel(page, settings, engine), /unknown delivery/);
  assert.equal(sent, 2);
  assert.deepEqual(events, ['sending']);
});
