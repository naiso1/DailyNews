'use strict';
// Browser doubles only: no login, upload, provider, or external network.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const vm = require('node:vm');
const { test } = require('node:test');
const extension = require('../deployment/workstation/exabase/reference-generation');

function fixture(t, options = {}) {
  const outputDir = fs.mkdtempSync(path.join(os.tmpdir(), 'exa-ref-test-'));
  t.after(() => fs.rmSync(outputDir, { recursive: true, force: true }));
  const file = path.join(outputDir, 'reference_jp1.jpg');
  fs.writeFileSync(file, Buffer.alloc(1200, 7));
  const referenceImage = { mode: 'source-image-v1', file, sourceNewsId: 'jp1', mime: 'image/jpeg',
    sha256: crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex') };
  const events = [];
  let clock = 100, sent = 0, uploaded = 0;
  const now = Date.now;
  Date.now = () => clock;
  t.after(() => { Date.now = now; });
  const input = {
    fill: async () => events.push('fill'),
    locator: () => ({ screenshot: async () => events.push('screenshot') }),
  };
  const page = {
    url: () => clock < 1100 ? 'https://gai.exabase.ai/conversation' : 'https://gai.exabase.ai/conversation/12345678-1234-1234-1234-123456789abc',
    evaluate: async (fn, argument) => {
      const code = String(fn);
      if (code.includes('input.files.length')) return !options.rejected && uploaded === 1;
      if (code.includes('const response = await fetch')) {
        assert.equal(argument, 'generated-src');
        return { mime: 'image/jpeg', base64: Buffer.alloc(1200, 9).toString('base64') };
      }
      if (code.includes('document.images')) return options.uploadOnly ? [] : ['generated-src'];
      throw Error('Unexpected page evaluation');
    },
    waitForTimeout: async ms => { clock += ms; },
    locator: selector => {
      if (selector === 'input[type="file"]') return {
        count: async () => 1, getAttribute: async () => options.unsupported ? 'application/pdf' : 'image/*',
        setInputFiles: async value => { assert.equal(value, file); uploaded++; events.push('upload'); },
      };
      if (selector === 'button[aria-label="Send Message Button"]') return {
        count: async () => 1, waitFor: async () => {}, isEnabled: async () => true,
        click: async () => { sent++; events.push('click'); if (options.uncertain) throw Error('unknown delivery'); },
      };
      throw Error('Unexpected locator: ' + selector);
    },
    getByRole: () => ({ first: () => ({ isVisible: async () => false }) }),
  };
  const engine = { _test: {
    startNewConversation: async () => events.push('new'), enableImageGeneration: async () => events.push('tool'),
    visibleChatInput: async () => input, collectPageImageSources: async () => ['attachment-src'],
    getConversationIdentity: async () => 'before',
    waitForPromptSubmission: async () => { assert.equal(sent, 1); events.push('accepted'); },
    collectImageRecords: async () => [{ src: 'attachment-src' }, { src: 'generated-src' }],
  } };
  const settings = { referenceImage, outputDir, prompt: 'Synthetic reference test', timeoutMs: 10000,
    isCancelled: () => false, onProgress: value => events.push(value.status) };
  return { settings, page, engine, events, outputDir, referenceImage,
    sent: () => sent, uploaded: () => uploaded,
    run: () => extension.generateWithReference(page, settings, engine) };
}

test('reference upload accepted before one send; output is distinct and receipt stays private', async t => {
  const f = fixture(t);
  const result = await f.run();
  assert.equal(f.sent(), 1); assert.equal(f.uploaded(), 1);
  assert.ok(f.events.indexOf('upload') < f.events.indexOf('sending'));
  assert.ok(f.events.indexOf('sending') < f.events.indexOf('click'));
  assert.ok(f.events.indexOf('accepted') < f.events.indexOf('done'));
  assert.equal(result.files.length, 1);
  const receipt = JSON.parse(fs.readFileSync(path.join(f.outputDir, 'attachment.json')));
  assert.equal(receipt.composerAccepted, true); assert.equal(receipt.promptAccepted, true);
  assert.equal(receipt.sha256, f.referenceImage.sha256);
  assert.equal(receipt.conversationPath, '/conversation/12345678-1234-1234-1234-123456789abc');
});

for (const rejected of ['rejected', 'unsupported']) test(`${rejected} attachment never sends`, async t => {
  const f = fixture(t, { [rejected]: true });
  await assert.rejects(f.run(), error => /^REFERENCE_/.test(error.safeCode));
  assert.equal(f.sent(), 0);
});

test('uncertain click has no retry or Enter fallback', async t => {
  const f = fixture(t, { uncertain: true });
  await assert.rejects(f.run(), /unknown delivery/);
  assert.equal(f.sent(), 1);
  assert.equal(f.events.filter(event => event === 'sending').length, 1);
  assert.equal(f.events.includes('done'), false);
});

test('an input thumbnail alone never counts as generated output', async t => {
  const f = fixture(t, { uploadOnly: true });
  await assert.rejects(f.run(), error => error.safeCode === 'GENERATION_TIMEOUT');
  assert.equal(f.sent(), 1);
  assert.equal(fs.existsSync(path.join(f.outputDir, 'generated-reference.jpg')), false);
});

test('changed image or image outside the job directory is rejected before browser work', t => {
  const f = fixture(t);
  assert.throws(() => extension.validateReference({ ...f.referenceImage, file: path.join(f.outputDir, '..', 'elsewhere.jpg') }, f.outputDir), /REFERENCE_INVALID_IMAGE/);
  fs.appendFileSync(f.referenceImage.file, 'changed');
  assert.throws(() => extension.validateReference(f.referenceImage, f.outputDir), /REFERENCE_CHANGED/);
  assert.deepEqual(f.events, []);
});

test('React-cleared file input is accepted only with one decoded matching thumbnail', async () => {
  const photo = { alt: 'reference_jp1.jpg', complete: true, naturalWidth: 800, naturalHeight: 533,
    getBoundingClientRect: () => ({ width: 70 }) };
  const input = { files: [] };
  const dom = { querySelectorAll: () => [input], images: [photo] };
  const page = { evaluate: async (callback, name) => vm.runInNewContext(`(${callback})(${JSON.stringify(name)})`, { document: dom }) };
  assert.equal(await extension.attachmentAccepted(page, photo.alt), true);
  input.files = [{ name: 'unexpected.jpg' }];
  assert.equal(await extension.attachmentAccepted(page, photo.alt), false);
  input.files = [];
  photo.complete = false;
  assert.equal(await extension.attachmentAccepted(page, photo.alt), false);
});

test('provider filename output after generated marker is accepted while upload stays excluded', async () => {
  const upload = { alt:'reference_jp1.jpg',src:'upload-src',closest:()=>null };
  const output = { alt:'tmp1ex_okec.jpeg',src:'output-src',closest:()=>null };
  const marker = {innerText:'Nano Bananaで生成された画像です！',compareDocumentPosition: image => image===output ? 4 : 2};
  const dom = {querySelectorAll:()=>[marker],images:[upload,output]};
  const page = {evaluate:async(callback,name)=>vm.runInNewContext(`(${callback})(${JSON.stringify(name)})`,{
    document:dom,Node:{DOCUMENT_POSITION_FOLLOWING:4}})};
  assert.deepEqual(Array.from(await extension.generatedSources(page,upload.alt)),['output-src']);
});

test('explicit recovery downloads a matching completed conversation without upload or send', async t => {
  const f=fixture(t);
  const evaluate=f.page.evaluate;
  f.page.evaluate=async(fn,arg)=>String(fn).includes('normalize(document.body.innerText)')?true:evaluate(fn,arg);
  const result=await extension.recoverReference(f.page,f.settings,f.engine);
  assert.equal(result.files.length,1);
  assert.equal(f.sent(),0);assert.equal(f.uploaded(),0);
  assert.equal(f.events.includes('new'),false);
});
