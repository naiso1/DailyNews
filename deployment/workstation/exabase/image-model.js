'use strict';

// Select a named exaBase tool, never the first generic image-generation switch.
const fs = require('node:fs');
const path = require('node:path');
const MODELS = Object.freeze({ 'gpt-image': 'GPT-image', 'nano-banana': 'Nano Banana' });
const VERSION = 'named-image-tool-v1';
const fail = code => Object.assign(new Error(code), { safeCode: code });

function validatePriority(priority) {
  if (!Array.isArray(priority) || !priority.length || priority.length > 2
      || new Set(priority).size !== priority.length || priority.some(id => !Object.hasOwn(MODELS, id))) {
    throw fail('INVALID_MODEL_CONFIG');
  }
  return priority;
}

async function uniqueVisible(locator) {
  const matches = [];
  for (let i = 0; i < await locator.count(); i++) {
    const item = locator.nth(i);
    if (await item.isVisible()) matches.push(item);
  }
  if (matches.length > 1) throw fail('IMAGE_MODEL_AMBIGUOUS');
  return matches[0] || null;
}

async function findSwitch(page, id) {
  const model = id === 'gpt-image' ? 'GPT[-\\s]*image' : 'Nano\\s*Banana';
  const name = new RegExp('(画像\\s*生成|image\\s*generation).*' + model, 'i');
  for (const role of ['switch', 'checkbox', 'menuitemcheckbox']) {
    const named = await uniqueVisible(page.getByRole(role, { name }));
    if (named) return named;
  }
  const pressed = await uniqueVisible(page.getByRole('button', { name }).and(page.locator('[aria-pressed]')));
  if (pressed) return pressed;
  // The visible menu labels may not be accessible names of their switches.
  const label = await uniqueVisible(page.getByRole('menuitem').filter({ hasText: name }))
    || await uniqueVisible(page.getByRole('menu').getByText(name))
    || await uniqueVisible(page.getByText(new RegExp('^\\s*' + name.source, 'i')));
  if (!label) return null;
  let row = label;
  for (let level = 0; level < 4; level++) {
    const controls = row.locator('[role="switch"], [role="checkbox"], [role="menuitemcheckbox"], input[type="checkbox"], button[aria-pressed]');
    // Never ascend into a whole menu and accidentally choose another tool.
    if (await controls.count() > 1) return null;
    if (await controls.count() === 1) return uniqueVisible(controls);
    row = row.locator('..');
  }
  return null;
}

async function isOn(control) {
  return control.evaluate(el => {
    if (typeof el.checked === 'boolean') return el.checked;
    for (const attr of ['aria-checked', 'aria-pressed']) {
      const value = el.getAttribute(attr);
      if (value === 'true') return true;
      if (value === 'false') return false;
    }
    const value = el.getAttribute('data-state');
    if (value === 'checked' || value === 'on') return true;
    if (value === 'unchecked' || value === 'off') return false;
    return null;
  });
}

async function setOn(page, control, desired) {
  const initial = await isOn(control);
  if (initial === null) throw fail('IMAGE_MODEL_NOT_ENABLED');
  if (initial === desired) return;
  if (!await control.isEnabled()) throw fail('IMAGE_MODEL_NOT_ENABLED');
  await control.click({ timeout: 15000 });
  const deadline = Date.now() + 5000;
  while (Date.now() < deadline) {
    if (await isOn(control) === desired) return;
    await page.waitForTimeout(100);
  }
  throw fail('IMAGE_MODEL_NOT_ENABLED');
}

async function selectImageModel(page, priority, engine, outputDir) {
  validatePriority(priority);
  await engine._test.dismissReleaseNotes(page);
  let controls = {};
  const discover = async () => {
    controls = {};
    for (const id of Object.keys(MODELS)) controls[id] = await findSwitch(page, id);
  };
  await discover();
  if (!Object.values(controls).some(Boolean)) {
    const name = /^\s*(ツール|tools)\s*$/i;
    const tools = await uniqueVisible(page.getByRole('button', { name }))
      || await uniqueVisible(page.getByText(name));
    if (!tools) throw fail('IMAGE_MODEL_UNAVAILABLE');
    await tools.click({ timeout: 15000 });
    const deadline = Date.now() + 15000;
    do {
      await discover();
      if (Object.values(controls).some(Boolean)) break;
      await page.waitForTimeout(200);
    } while (Date.now() < deadline);
  }
  const unavailable = [];
  let selected;
  for (const id of priority) {
    if (!controls[id]) unavailable.push({ model: id, reason: 'not-visible' });
    else if (!await controls[id].isEnabled()) unavailable.push({ model: id, reason: 'disabled' });
    else { selected = id; break; }
  }
  if (!selected) throw fail('IMAGE_MODEL_UNAVAILABLE');
  for (const [id, control] of Object.entries(controls)) {
    if (id !== selected && control) await setOn(page, control, false);
  }
  await setOn(page, controls[selected], true);
  const states = {};
  for (const [id, control] of Object.entries(controls)) {
    states[id] = control ? await isOn(control) : null;
    if (control && states[id] !== (id === selected)) throw fail('IMAGE_MODEL_NOT_ENABLED');
  }
  const receipt = { version: VERSION, priority, selected, label: MODELS[selected], verified: true,
    states, unavailable, selectedAt: new Date().toISOString() };
  fs.writeFileSync(path.join(outputDir, 'model-selection.json'), JSON.stringify(receipt));
  await page.keyboard.press('Escape');
  return receipt;
}

module.exports = { VERSION, MODELS, validatePriority, findSwitch, selectImageModel };
