'use strict';

const fs = require('node:fs');
const path = require('node:path');
const { selectImageModel } = require('./image-model');
const { waitForGeneratedImage, saveGeneratedImage } = require('./reference-generation');
const fail = code => Object.assign(new Error(code), { safeCode: code });

async function generateWithModel(page, settings, engine) {
  const { prompt, outputDir, imageModels, timeoutMs, isCancelled, onProgress } = settings;
  if (isCancelled()) throw fail('GENERATION_TIMEOUT');
  await engine._test.startNewConversation(page);
  const modelSelection = await selectImageModel(page, imageModels, engine, outputDir);
  const input = await engine._test.visibleChatInput(page);
  if (!input) throw fail('AUTH_REQUIRED');
  await input.fill(prompt);
  const send = page.locator('button[aria-label="Send Message Button"]');
  if (await send.count() !== 1) throw fail('GENERATION_FAILED');
  await send.waitFor({ state: 'visible', timeout: 15000 });
  const deadline = Date.now() + 15000;
  while (!await send.isEnabled()) {
    if (isCancelled() || Date.now() >= deadline) throw fail('GENERATION_FAILED');
    await page.waitForTimeout(200);
  }
  const previous = new Set(await engine._test.collectPageImageSources(page));
  const identity = await engine._test.getConversationIdentity(page);
  if (isCancelled()) throw fail('GENERATION_TIMEOUT');
  // One submission only. Any uncertainty is left for review, never retried here.
  onProgress({ status: 'sending' });
  await send.click({ timeout: 15000 });
  await engine._test.waitForPromptSubmission(page, input, prompt, identity);
  const observeConversation = () => {
    const route = new URL(page.url()).pathname;
    if (/^\/conversation\/[a-f0-9-]{36}$/.test(route)) {
      fs.writeFileSync(path.join(outputDir, 'conversation.json'), JSON.stringify({ conversationPath: route }));
    }
  };
  observeConversation();
  onProgress({ status: 'submitted' });
  const record = await waitForGeneratedImage(page, engine, previous, prompt, timeoutMs, isCancelled, '', observeConversation);
  const file = await saveGeneratedImage(page, record, outputDir);
  onProgress({ status: 'done' });
  return { files: [file], errors: [], modelSelection };
}

module.exports = { generateWithModel };
