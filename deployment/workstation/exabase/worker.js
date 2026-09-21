'use strict';

// A separate, ephemeral Edge context. Never attach to the user's everyday browser.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { spawn } = require('node:child_process');
const { createRequire } = require('node:module');
const RUNTIME = path.join(process.env.LOCALAPPDATA || '', 'DailyNewsRuntime', 'exabase');
const AUTH = path.join(RUNTIME, 'auth.bin');
const ENGINE = path.join(RUNTIME, 'engine', 'playwright_engine.js');
const HASH = '481517dd4230ab85afd490e5b3db491b0f599cd46f4e1e550aacaf8571353d76';
const URL = 'https://gai.exabase.ai/conversation';
delete process.env.EXABASE_DIAGNOSTICS_DIR;

function emit(value) { process.stdout.write(`${JSON.stringify(value)}\n`); }
function atomicJson(file, value) {
  const temp = `${file}.${process.pid}.tmp`;
  fs.writeFileSync(temp, JSON.stringify(value), 'utf8');
  fs.renameSync(temp, file);
}
function fail(code) { return Object.assign(new Error(code), { safeCode: code }); }
function runtime() {
  if (process.platform !== 'win32' || !process.env.LOCALAPPDATA) throw fail('WINDOWS_REQUIRED');
  if (!fs.existsSync(ENGINE)) throw fail('RUNTIME_MISSING');
  if (crypto.createHash('sha256').update(fs.readFileSync(ENGINE)).digest('hex') !== HASH) throw fail('ENGINE_CHANGED');
  const engine = require(ENGINE);
  const { chromium } = createRequire(ENGINE)('playwright-core');
  const edge = [process.env['ProgramFiles(x86)'], process.env.ProgramFiles, process.env.LOCALAPPDATA]
    .filter(Boolean).map(base => path.join(base, 'Microsoft', 'Edge', 'Application', 'msedge.exe'))
    .find(file => fs.existsSync(file));
  if (!edge) throw fail('EDGE_MISSING');
  return { engine, chromium, edge };
}
function acquireLock() {
  const file = path.join(RUNTIME, 'worker.lock');
  try {
    const fd = fs.openSync(file, 'wx');
    fs.writeFileSync(fd, String(process.pid)); fs.closeSync(fd);
  } catch (error) {
    if (error.code !== 'EEXIST') throw error;
    const owner = Number(fs.readFileSync(file, 'utf8'));
    if (!Number.isSafeInteger(owner) || owner <= 0) throw fail('BUSY');
    try { process.kill(owner, 0); throw fail('BUSY'); }
    catch (check) { if (check.code !== 'ESRCH') throw fail('BUSY'); }
    fs.unlinkSync(file);
    const oldSession = path.join(RUNTIME, `session-${owner}.json`);
    if (fs.existsSync(oldSession)) fs.unlinkSync(oldSession);
    return acquireLock();
  }
  return () => { try { fs.unlinkSync(file); } catch (_) {} };
}
function dpapi(buffer, protect) {
  const method = protect ? 'Protect' : 'Unprotect';
  const script = `Add-Type -AssemblyName System.Security; $b=[Convert]::FromBase64String([Console]::In.ReadToEnd().Trim()); $r=[Security.Cryptography.ProtectedData]::${method}($b,$null,[Security.Cryptography.DataProtectionScope]::CurrentUser); [Console]::Out.Write([Convert]::ToBase64String($r))`;
  return new Promise((resolve, reject) => {
    const child = spawn('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', script], {
      windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'],
    });
    const chunks = []; let size = 0;
    const timer = setTimeout(() => { child.kill(); reject(fail('SESSION_UNAVAILABLE')); }, 30000);
    child.stdout.on('data', chunk => { size += chunk.length; if (size > 4 * 1024 * 1024) child.kill(); else chunks.push(chunk); });
    child.stderr.resume(); // Never forward authentication/PowerShell diagnostics.
    child.on('error', () => { clearTimeout(timer); reject(fail('SESSION_UNAVAILABLE')); });
    child.on('close', code => { clearTimeout(timer); code === 0
      ? resolve(Buffer.from(Buffer.concat(chunks).toString('utf8').trim(), 'base64'))
      : reject(fail('SESSION_UNAVAILABLE')); });
    child.stdin.end(buffer.toString('base64'));
  });
}
async function sessionState() {
  if (!fs.existsSync(AUTH)) throw fail('AUTH_REQUIRED');
  try { return JSON.parse((await dpapi(fs.readFileSync(AUTH), false)).toString('utf8')); }
  catch (_) { throw fail('AUTH_REQUIRED'); }
}
async function saveSessionState(state) {
  const encrypted = await dpapi(Buffer.from(JSON.stringify(state), 'utf8'), true);
  const temporary = `${AUTH}.${process.pid}.tmp`;
  try {
    fs.writeFileSync(temporary, encrypted);
    fs.renameSync(temporary, AUTH);
  } finally {
    if (fs.existsSync(temporary)) fs.unlinkSync(temporary);
  }
}
async function captureSessionState(context) {
  // Supported by the pinned Playwright 1.55.0; tokens may also live in IndexedDB.
  return context.storageState({ indexedDB: true });
}
async function authenticated(page, engine) {
  return page.url().startsWith(URL) && Boolean(await engine._test.visibleChatInput(page));
}
async function login(dependencies) {
  const { chromium, edge, engine } = dependencies;
  const browser = await chromium.launch({ executablePath: edge, headless: false });
  try {
    const context = await browser.newContext();
    const page = await context.newPage();
    await page.goto(URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
    emit({ status: 'LOGIN_REQUIRED', timeoutSeconds: 600 });
    const deadline = Date.now() + 600000;
    while (Date.now() < deadline) {
      for (const candidate of context.pages()) {
        if (!candidate.isClosed() && await authenticated(candidate, engine)) {
          const refreshed = await captureSessionState(context);
          if (candidate.isClosed() || !await authenticated(candidate, engine)) throw fail('AUTH_REQUIRED');
          await saveSessionState(refreshed);
          emit({ status: 'SESSION_SAVED' }); return;
        }
      }
      await new Promise(resolve => setTimeout(resolve, 500));
    }
    throw fail('LOGIN_TIMEOUT');
  } finally { await browser.close().catch(() => {}); }
}
async function checkSession(dependencies, state) {
  const { chromium, edge, engine } = dependencies;
  const browser = await chromium.launch({ executablePath: edge, headless: true });
  try {
    const context = await browser.newContext({ storageState: state });
    const page = await context.newPage();
    await page.goto(URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
    const deadline = Date.now() + 15000;
    while (Date.now() < deadline) {
      if (await authenticated(page, engine)) {
        // Navigation may refresh cookies or local storage. Persist only after
        // the signed-in conversation is confirmed, and use this state below.
        const refreshed = await captureSessionState(context);
        if (page.isClosed() || !await authenticated(page, engine)) throw fail('AUTH_REQUIRED');
        await saveSessionState(refreshed);
        return refreshed;
      }
      if (/login|signin|microsoftonline/i.test(page.url())) throw fail('AUTH_REQUIRED');
      await new Promise(resolve => setTimeout(resolve, 500));
    }
    throw fail('AUTH_REQUIRED');
  } finally { await browser.close().catch(() => {}); }
}
async function readRequest() {
  const chunks = []; let size = 0;
  for await (const chunk of process.stdin) { size += chunk.length; if (size > 65536) throw fail('INVALID_REQUEST'); chunks.push(chunk); }
  try { return JSON.parse(Buffer.concat(chunks).toString('utf8')); } catch (_) { throw fail('INVALID_REQUEST'); }
}
async function generate(dependencies, request, state, recoveryOnly = false) {
  if (!/^[a-f0-9]{64}$/.test(request.key || '') || typeof request.prompt !== 'string'
      || !request.prompt.trim() || request.prompt.length > 12000 || !path.isAbsolute(request.outputDir || '')) throw fail('INVALID_REQUEST');
  if (recoveryOnly && (!request.referenceImage
      || !/^\/conversation\/[a-f0-9-]{36}$/.test(request.conversationPath || ''))) throw fail('INVALID_REQUEST');
  fs.mkdirSync(request.outputDir, { recursive: true });
  const { chromium, edge, engine } = dependencies;
  let browser, context, page, stopWatching;
  let cancelled = false;
  const timeout = Math.max(30000, Math.min(Number(request.timeoutMs || 420000), 600000));
  const timer = setTimeout(() => { cancelled = true; }, timeout);
  try {
    if (cancelled) throw fail('GENERATION_TIMEOUT');
    // Own only the browser lifecycle; keep the pinned engine's generation flow.
    browser = await chromium.launch({ executablePath: edge, headless: true });
    stopWatching = engine._test.watchCancellation(browser, () => cancelled);
    context = await browser.newContext({ storageState: state, viewport: { width: 1440, height: 1000 } });
    page = await context.newPage();
    await page.goto(recoveryOnly ? 'https://gai.exabase.ai' + request.conversationPath : URL,
      { waitUntil: 'domcontentloaded', timeout: 60000 });
    if (recoveryOnly) await page.waitForFunction(text => {
      const normalize = value => String(value || '').replace(/\s+/g, ' ').trim();
      return normalize(document.body.innerText).includes(normalize(text));
    }, request.prompt, { timeout: 30000 });
    const settings = {
      prompt: request.prompt, outputDir: request.outputDir, count: 1,
      timeoutMs: timeout, isCancelled: () => cancelled,
      onProgress: progress => {
        if (!['sending', 'submitted', 'done'].includes(progress.status)) return;
        const event = { event: progress.status, key: request.key };
        atomicJson(path.join(request.outputDir, 'phase.json'), event);
        emit(event);
      },
    };
    const result = recoveryOnly
      ? await require('./reference-generation').recoverReference(page, { ...settings, referenceImage: request.referenceImage }, engine)
      : request.referenceImage
      ? await require('./reference-generation').generateWithReference(page, { ...settings, referenceImage: request.referenceImage }, engine)
      : await engine._test.generateOnPage(page, settings);
    if (result.files.length !== 1 || result.errors.length) throw fail('GENERATION_FAILED');
    const file = path.resolve(result.files[0]);
    if (path.dirname(file) !== path.resolve(request.outputDir)) throw fail('INVALID_IMAGE_PATH');
    const receipt = { status: 'DONE', key: request.key, file, ...(recoveryOnly ? { recoveredFromConversation: true } : {}) };
    atomicJson(path.join(request.outputDir, 'result.json'), receipt);
    emit(receipt);
  } catch (error) {
    if (cancelled) throw fail('GENERATION_TIMEOUT');
    throw error;
  } finally {
    clearTimeout(timer);
    if (stopWatching) stopWatching();
    try {
      // A cancelled/closed/signed-out context must not replace the saved session.
      if (!cancelled && context && page && !page.isClosed() && await authenticated(page, engine)) {
        const refreshed = await captureSessionState(context);
        if (!page.isClosed() && await authenticated(page, engine)) await saveSessionState(refreshed);
      }
    } catch (_) {
      // The image and DONE receipt are already durable. Do not trigger a paid
      // fallback because saving an otherwise usable session failed.
      emit({ event: 'warning', code: 'SESSION_REFRESH_FAILED', key: request.key });
    } finally {
      if (browser) await browser.close().catch(() => {});
    }
  }
}
async function main() {
  const mode = process.argv[2] || '--status';
  const dependencies = runtime();
  if (mode === '--status') { emit({ status: fs.existsSync(AUTH) ? 'SESSION_PRESENT' : 'AUTH_REQUIRED', engineSha256: HASH }); return; }
  const release = acquireLock();
  try {
    if (mode === '--login') return await login(dependencies);
    const state = await checkSession(dependencies, await sessionState());
    if (mode === '--check-session') { emit({ status: 'AUTHENTICATED' }); return; }
    if (!['--generate', '--recover-reference'].includes(mode)) throw fail('INVALID_MODE');
    await generate(dependencies, await readRequest(), state, mode === '--recover-reference');
  } finally { release(); }
}
if (require.main === module) main().catch(error => {
  emit({ status: 'ERROR', code: error.safeCode || 'EXABASE_UNAVAILABLE' }); process.exitCode = 1;
});
module.exports = { atomicJson };
