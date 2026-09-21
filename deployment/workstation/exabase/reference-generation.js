'use strict';

// Project-owned extension. The shared, hash-pinned text engine stays unchanged.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const fail = code => Object.assign(new Error(code), { safeCode: code });
const VERSION = 'source-image-v1';

function validateReference(reference, outputDir) {
  if (!reference || reference.mode !== VERSION || !/^[a-f0-9]{64}$/.test(reference.sha256 || '')
      || !['image/jpeg', 'image/png', 'image/webp'].includes(reference.mime)
      || !path.isAbsolute(reference.file || '')
      || path.dirname(path.resolve(reference.file)) !== path.resolve(outputDir)) throw fail('REFERENCE_INVALID_IMAGE');
  const info = fs.statSync(reference.file);
  if (!info.isFile() || info.size < 1000 || info.size > 10 * 1024 * 1024
      || crypto.createHash('sha256').update(fs.readFileSync(reference.file)).digest('hex') !== reference.sha256) {
    throw fail('REFERENCE_CHANGED');
  }
}

async function attachmentAccepted(page, fileName) {
  return page.evaluate(name => {
    const inputs = [...document.querySelectorAll('input[type="file"]')];
    const input = inputs.length === 1 ? inputs[0] : null;
    const images = [...document.images].filter(image => image.alt === name && image.complete
      && image.naturalWidth >= 256 && image.naturalHeight >= 256 && image.getBoundingClientRect().width > 0);
    // React clears the native file input after reading it; the decoded composer
    // thumbnail is the acceptance signal. Reject an unexpected remaining file.
    return Boolean(input && input.files.length <= 1 && (input.files.length === 0 || input.files[0].name === name)
      && images.length === 1);
  }, fileName);
}

async function generatedSources(page, referenceFileName) {
  return page.evaluate(fileName => {
    const markers = [...document.querySelectorAll('p, span, div')].filter(el => {
      const text = String(el.innerText || '').trim();
      return text.length < 300 && /Nano\s*Banana.*生成.*画像|生成された画像です/i.test(text);
    }).sort((a, b) => a.innerText.length - b.innerText.length);
    const marker = markers[0];
    return [...document.images].filter(image => {
      if (image.alt === fileName || /^reference[_-]/i.test(image.alt || '')) return false;
      return /生成.*画像|generated image|image result/i.test(image.alt || '')
        || Boolean(image.closest('[data-message-author-role="assistant"], [class*="chat-message-markdown"]'))
        || Boolean(marker && marker.compareDocumentPosition(image) & Node.DOCUMENT_POSITION_FOLLOWING);
    }).map(image => image.currentSrc || image.src);
  }, referenceFileName);
}

async function waitForGeneratedImage(page, engine, previous, prompt, timeoutMs, isCancelled, referenceFileName = '', onPoll = () => {}) {
  const deadline = Date.now() + timeoutMs;
  let stable = '', since = 0;
  while (Date.now() < deadline) {
    if (isCancelled()) throw fail('GENERATION_TIMEOUT');
    await page.waitForTimeout(1000);
    onPoll();
    const records = await engine._test.collectImageRecords(page, prompt);
    // Attachment thumbnails can be re-created after submission with a new URL.
    // Require an assistant/generated-image context, never the user's upload.
    const allowed = await generatedSources(page, referenceFileName);
    const fresh = records.filter(record => !previous.has(record.src) && allowed.includes(record.src));
    if (!fresh.length) continue;
    const candidate = fresh[fresh.length - 1];
    if (candidate.src !== stable) { stable = candidate.src; since = Date.now(); continue; }
    if (Date.now() - since < 2500 || await page.getByRole('button', { name: /停止|Stop|Cancel/i }).first().isVisible().catch(() => false)) continue;
    return candidate;
  }
  throw fail('GENERATION_TIMEOUT');
}

async function saveGeneratedImage(page, record, outputDir) {
  // Only an observed generated-image src is fetched, through its owning context.
  const payload = await page.evaluate(async source => {
    const response = await fetch(source, { credentials: 'include' });
    if (!response.ok) throw new Error('download failed');
    const blob = await response.blob();
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(blob.type) || blob.size > 25 * 1024 * 1024) throw new Error('invalid image');
    const bytes = new Uint8Array(await blob.arrayBuffer());
    let binary = '';
    for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
    return { mime: blob.type, base64: btoa(binary) };
  }, record.src);
  const extension = { 'image/jpeg': '.jpg', 'image/png': '.png', 'image/webp': '.webp' }[payload.mime];
  if (!extension) throw fail('INVALID_IMAGE');
  const file = path.join(outputDir, 'generated-reference' + extension);
  fs.writeFileSync(file + '.tmp', Buffer.from(payload.base64, 'base64'));
  fs.renameSync(file + '.tmp', file);
  return file;
}

async function generateWithReference(page, settings, engine) {
  const { referenceImage, outputDir, prompt, timeoutMs, isCancelled, onProgress } = settings;
  validateReference(referenceImage, outputDir);
  if (isCancelled()) throw fail('GENERATION_TIMEOUT');
  await engine._test.startNewConversation(page);
  await engine._test.enableImageGeneration(page);
  const input = await engine._test.visibleChatInput(page);
  if (!input) throw fail('AUTH_REQUIRED');
  const upload = page.locator('input[type="file"]');
  if (await upload.count() !== 1 || !/image\/\*/.test(await upload.getAttribute('accept') || '')) throw fail('REFERENCE_UNSUPPORTED');
  const fileName = path.basename(referenceImage.file);
  await upload.setInputFiles(referenceImage.file);
  const deadline = Date.now() + 30000;
  while (!await attachmentAccepted(page, fileName)) {
    if (isCancelled() || Date.now() > deadline) throw fail('REFERENCE_NOT_ACCEPTED');
    await page.waitForTimeout(200);
  }
  await input.fill(prompt);
  const send = page.locator('button[aria-label="Send Message Button"]');
  if (await send.count() !== 1) throw fail('REFERENCE_UNSUPPORTED');
  await send.waitFor({ state: 'visible', timeout: 15000 });
  // Upload preview URLs may be replaced by the server while the prompt is filled.
  // Wait for the final decoded thumbnail as well as an enabled send control.
  while (!await send.isEnabled() || !await attachmentAccepted(page, fileName)) {
    if (isCancelled() || Date.now() > deadline) throw fail('REFERENCE_NOT_ACCEPTED');
    await page.waitForTimeout(200);
  }
  const receipt = { mode: VERSION, fileName, sha256: referenceImage.sha256,
    sourceNewsId: referenceImage.sourceNewsId, composerAccepted: true, acceptedAt: new Date().toISOString() };
  fs.writeFileSync(path.join(outputDir, 'attachment.json'), JSON.stringify(receipt));
  const composer = input.locator('xpath=ancestor::div[.//button[@aria-label="Send Message Button"]][1]');
  await composer.screenshot({ path: path.join(outputDir, 'attachment-accepted.png') });
  const previous = new Set(await engine._test.collectPageImageSources(page));
  const identity = await engine._test.getConversationIdentity(page);
  if (isCancelled()) throw fail('GENERATION_TIMEOUT');
  // The durable sending receipt precedes the only send attempt. No Enter fallback.
  onProgress({ status: 'sending' });
  await send.click({ timeout: 15000 });
  await engine._test.waitForPromptSubmission(page, input, prompt, identity);
  receipt.promptAccepted = true;
  const observeConversation = () => {
    const route = new URL(page.url()).pathname;
    if (/^\/conversation\/[a-f0-9-]{36}$/.test(route) && receipt.conversationPath !== route) {
      receipt.conversationPath = route;
      fs.writeFileSync(path.join(outputDir, 'attachment.json'), JSON.stringify(receipt));
    }
  };
  observeConversation();
  fs.writeFileSync(path.join(outputDir, 'attachment.json'), JSON.stringify(receipt));
  onProgress({ status: 'submitted' });
  const record = await waitForGeneratedImage(page, engine, previous, prompt, timeoutMs, isCancelled, fileName, observeConversation);
  const file = await saveGeneratedImage(page, record, outputDir);
  observeConversation();
  receipt.generatedAt = new Date().toISOString();
  fs.writeFileSync(path.join(outputDir, 'attachment.json'), JSON.stringify(receipt));
  onProgress({ status: 'done' });
  return { files: [file], errors: [] };
}

async function recoverReference(page, settings, engine) {
  const { referenceImage, outputDir, prompt, timeoutMs, isCancelled } = settings;
  validateReference(referenceImage, outputDir);
  // Called only for an explicitly selected existing conversation, with no send.
  const matching = await page.evaluate(({ text, name }) => {
    const normalize = value => String(value || '').replace(/\s+/g, ' ').trim();
    return normalize(document.body.innerText).includes(normalize(text))
      && [...document.images].some(image => image.alt === name);
  }, { text: prompt, name: path.basename(referenceImage.file) });
  if (!matching) throw fail('REFERENCE_CHANGED');
  const record = await waitForGeneratedImage(page, engine, new Set(), prompt, Math.min(timeoutMs, 60000),
    isCancelled, path.basename(referenceImage.file));
  const file = await saveGeneratedImage(page, record, outputDir);
  return { files: [file], errors: [] };
}

module.exports = { VERSION, validateReference, attachmentAccepted, generatedSources, waitForGeneratedImage,
  generateWithReference, recoverReference };
