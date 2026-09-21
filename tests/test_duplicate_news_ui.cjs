const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const html = fs.readFileSync(path.join(__dirname, '..', '内装製品デイリーニュース.html'), 'utf8');
const account = fs.readFileSync(path.join(__dirname, '..', 'dailynews_account.js'), 'utf8');
const activity = fs.readFileSync(path.join(__dirname, '..', 'dailynews_activity.js'), 'utf8');
const rows = [
  {id: 'jp1', date: '2026-09-17', title: 'Original representative', url: 'https://primary.test/story'},
  {id: 'jp2', date: '2026-09-20', title: 'Syndicated article', duplicateOf: 'jp1', url: 'https://syndicated.test/story?a=1&b="quoted"'},
  {id: 'jp3', date: '2026-09-20', duplicateOf: 'jp2'},
  {id: 'eu1', country: 'eu', date: '2026-09-20', title: 'Different product'},
  {id: 'cn1', country: 'cn', title: 'Hidden representative'},
  {id: 'cn2', country: 'cn', duplicateOf: 'cn1'},
  {id: 'jp4', duplicateOf: 'jp1', url: 'https://hidden.test/story'},
  {id: 'in1', duplicateOf: 'missing'},
  {id: 'us1', duplicateOf: 'us2'},
  {id: 'us2', duplicateOf: 'us1'},
  {id: 'eu2', duplicateOf: 'eu2'},
  {id: 'paper1', country: 'paper', title: 'Separate paper'},
  {id: 'jp5', duplicateOf: 'paper1'},
  {id: 'paper2', country: 'paper', duplicateOf: 'jp1'},
].map(n => ({country: 'jp', date: '2026-09-17', img: 'image.png', desc: 'Description', tags: [], ...n}));
rows[0].relatedUrls = [rows[0].url, rows[1].url, rows[1].url, rows[6].url,
  'javascript:alert(1)', 'data:text/html,hidden', '/relative', 'https://user:password@secret.test/path',
  'http://second.test/article#part', {url: 'https://not-a-string.test/'}];
const elements = Object.fromEntries(['searchInput', 'contentCategory', 'dateFrom', 'dateTo', 'dateBasis', 'sortOrder', 'favoritesToggle']
  .map(id => [id, {value: '', textContent: '', classList: {toggle() {}}, setAttribute() {}}]));
const noop = () => {};
const storageWrites = [], serverWrites = [];
const ctx = vm.createContext({URL, URLSearchParams, console, NEWS_DATA: rows,
  window: {DAILYNEWS_CONFIG: {id: 'exterior'}, LOADED_NEWS_DATA: rows,
    interactionsData: {cn1: {hidden: true}, jp4: {hidden: true}},
    dailyNewsAccount: {async setFavorite(id, enabled) {serverWrites.push([id, enabled]);}},
    DAILY_INSIGHTS: []},
  document: {getElementById: id => elements[id] || null, querySelectorAll: () => []},
  localStorage: {getItem: () => JSON.stringify(['jp2', 'jp3']), setItem: (...args) => storageWrites.push(args)},
  FAVORITES_STORAGE_KEY: 'test-favorites', favoriteIds: new Set(), selectedFavoriteKeys: new Set(),
  favoritesOnly: false, newOnly: true, visibleLimit: 30, insightsVisibleLimit: 1,
  activeCountries: new Set(['world']), activeTags: new Set(['all']),
  NEW_DATE_RANGE: {start: '2026-09-20', end: '2026-09-20'},
  beginInternalNavigation: noop, updateCountryChips: noop, updateTagChips: noop,
  updateRankingVisibility: noop, updateFavoritesActionsState: noop,
  updateFavoritesActionsVisibility: noop,
  applyFilters: noop, updateURL: noop, setTimeout: noop,
});
function extract(source, name, indent = '        ') {
  const start = source.indexOf(`${indent}function ${name}(`);
  assert(start >= 0, name);
  const marker = `\n${indent}}`;
  return source.slice(start, source.indexOf(marker, start) + marker.length);
}
for (const name of ['isGloballyHidden', 'getNewsLookup', 'resolveNewsItem', 'isNewsListItem',
  'visibleNewsData', 'isNewContent', 'getNewCounts', 'describeExteriorPublication',
  'safeNewsSourceUrl', 'relatedNewsUrls', 'renderRelatedNewsSources', 'escapeHtml',
  'showNewsItem', 'resolvedFavoriteKey', 'isFavorite', 'loadFavorites', 'saveFavorites',
  'updateFavoriteButton', 'updateFavoritesToggle', 'buildIdeaIndex', 'getFavoriteItems',
  'normalizeAnalysisRefs', 'makeAnalysisRefLinks', 'extractAnalysisRefIds']) {
  vm.runInContext(extract(html, name), ctx);
}
ctx.getNewsImageUrl = n => n.img;
ctx.window.getNewsImageUrl = ctx.getNewsImageUrl;
ctx.window.resolveDailyNewsItem = id => ctx.resolveNewsItem(id);
for (const name of ['accountItemIndex', 'activityEntries']) vm.runInContext(extract(account, name, ''), ctx);
vm.runInContext(extract(activity, 'activityItemIndex', ''), ctx);
const favoriteStart = html.indexOf('        window.toggleFavorite = async ');
assert(favoriteStart >= 0);
vm.runInContext(html.slice(favoriteStart, html.indexOf('\n        };', favoriteStart) + '\n        };'.length), ctx);

const ids = values => Array.from(values, n => n.id);
assert.deepEqual(ids(ctx.visibleNewsData()), ['jp1', 'eu1', 'paper1']);
assert.equal(ctx.resolveNewsItem('jp2').id, 'jp1');
assert.equal(ctx.resolveNewsItem('jp3').id, 'jp1');
assert.equal(ctx.resolveNewsItem('jp1').date, '2026-09-17', 'do not move historical representative into the new issue');
for (const id of ['cn1', 'cn2', 'jp4', 'in1', 'us1', 'us2', 'eu2', 'jp5', 'paper2', 'missing']) {
  assert.equal(ctx.resolveNewsItem(id), null, id);
}
assert.equal(ctx.resolveNewsItem('paper1').id, 'paper1', 'ordinary paper remains available in its own category');
assert.equal(ctx.isNewContent(rows[1]), false);
assert.equal(ctx.getNewCounts(rows).world, 1);
ctx.window.EXTERIOR_PUBLICATION_STATUS = {issue_date: '2026-09-20', processed_through: '2026-09-20',
  target_dates: ['2026-09-20'], status: 'published', selected_count: 3, selected_news_ids: ['jp2', 'jp3', 'eu1']};
assert.equal(ctx.describeExteriorPublication(ctx.window.EXTERIOR_PUBLICATION_STATUS, rows), '2026-09-20号：1件');

ctx.showNewsItem('jp3');
assert.equal(elements.searchInput.value, 'jp1');
assert.equal(elements.dateFrom.value, '');
assert.equal(elements.dateTo.value, '');
elements.searchInput.value = 'unchanged';
ctx.showNewsItem('cn2');
assert.equal(elements.searchInput.value, 'unchanged', 'hidden representative cannot be navigated to');

const related = ctx.renderRelatedNewsSources(rows[0]);
assert.match(related, /関連出典（2件）/);
assert.match(related, /a=1&amp;b=%22quoted%22/);
assert.match(related, /target="_blank" rel="noopener noreferrer"/);
assert(!related.includes('hidden.test'));
assert(!related.includes('javascript:'));
assert(!related.includes('password'));
assert.equal(ctx.renderRelatedNewsSources(rows[1]), '');
assert.equal(ctx.renderRelatedNewsSources(rows[3]), '', 'legacy cards gain no extra UI');

const map = new Map(rows.map(n => [n.id, n]));
const links = ctx.makeAnalysisRefLinks('[jp2,cn2,us1]', map);
assert.match(links, /Original representative/);
assert.match(links, /showNewsItemFromRef\('jp2'\)/, 'historical citation ID is retained');
assert(!links.includes('cn2'));
assert(!links.includes('us1'));
assert.deepEqual(Array.from(ctx.extractAnalysisRefIds('[jp2,jp3,jp1,cn2]', map)), ['jp1']);

ctx.loadFavorites();
assert.deepEqual([...ctx.favoriteIds], ['jp2', 'jp3']);
assert.equal(storageWrites.length, 0);
assert.equal(serverWrites.length, 0, 'reading old favorites must not migrate stored IDs');
assert.equal(ctx.isFavorite('jp1'), true);
assert.equal(ctx.isFavorite('jp2'), true);
assert.deepEqual(ids(ctx.getFavoriteItems()), ['jp1']);
ctx.updateFavoritesToggle();
assert.match(elements.favoritesToggle.textContent, /\(1\)/);

ctx.accountState = {activity: {favorites: ['jp2', 'jp3', 'jp1', 'cn2', 'us1'], likes: ['jp2', 'jp1']}};
const accountIndex = ctx.accountItemIndex();
assert.equal(accountIndex.get('jp2').targetId, 'jp1');
assert.equal(accountIndex.get('jp2').title, 'Original representative');
assert(!accountIndex.has('cn2'));
assert(!accountIndex.has('us1'));
assert.equal(ctx.accountItemIndex({includeHidden: true}).get('cn1').title, 'Hidden representative', 'admin-only raw index is preserved');
assert.deepEqual(ids(ctx.activityEntries('favorites')), ['jp1']);
assert.equal(ctx.activityEntries('favorites')[0].activityId, 'jp2', 'saved historical identity remains unchanged');
assert.deepEqual(ids(ctx.activityEntries('likes')), ['jp1']);
assert.equal(ctx.activityItemIndex().get('jp3').targetId, 'jp1');
assert(!ctx.activityItemIndex().has('cn2'));

(async () => {
  await ctx.window.toggleFavorite('jp1', null);
  assert.equal(ctx.favoriteIds.size, 0);
  assert.deepEqual(serverWrites, [['jp2', false], ['jp3', false]], 'explicit removal clears only stored alias IDs');
  await ctx.window.toggleFavorite('jp2', null);
  assert.deepEqual([...ctx.favoriteIds], ['jp1']);
  assert.deepEqual(serverWrites[2], ['jp1', true]);
  console.log('Duplicate news UI: listing/counts, historical navigation, safe chains, sources, citations, favorites and activity PASS');
})().catch(error => { console.error(error); process.exitCode = 1; });
