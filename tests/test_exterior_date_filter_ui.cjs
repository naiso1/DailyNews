const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const html = fs.readFileSync(path.join(__dirname, '..', '内装製品デイリーニュース.html'), 'utf8');
const elements = Object.fromEntries(['dateFrom', 'dateTo', 'dateBasis', 'searchInput', 'sortOrder', 'contentCategory']
  .map(id => [id, {value: '', hidden: false}]));
const location = {pathname: '/exterior/', search: ''};
const history = {state: {}, pushState(state, title, url) {
  this.state = state;
  location.search = new URL(url, 'https://example.test').search;
}, replaceState(state, title, url) { this.pushState(state, title, url); }};
const noop = () => {};
const context = vm.createContext({
  window: {DAILYNEWS_CONFIG: {id: 'exterior'}, location, scrollY: 0, scrollTo: noop},
  document: {getElementById: id => elements[id]}, location, history, URLSearchParams, setTimeout: noop,
  NEW_DATE_RANGE: {}, INITIAL_DATE_RANGE_OVERRIDES: {}, ONE_DAY_NEW_DATE_RANGE_OVERRIDES: {},
  NEW_DATE_RANGE_OVERRIDE: {start: '2026-09-17', end: '2026-09-17'},
  NEWS_DATA: [], activeCountries: new Set(['world']), activeTags: new Set(['all']),
  favoritesOnly: false, newOnly: false, visibleLimit: 30, insightsVisibleLimit: 1, rankingBackState: null,
  updateCountryChips: noop, updateTagChips: noop, updateFavoritesToggle: noop,
  updateFavoritesActionsVisibility: noop, scheduleRankingUpdate: noop, setRankingBackVisibility: noop,
  newsCategoryLabel: item => item.contentCategory || 'product', isFavorite: () => true,
});
for (const name of ['getTodayKey', 'getLatestDate', 'setNewDateRangeFromNews', 'getDateFilterBasis',
  'getNewsFilterDate', 'matchesNewsDateRange', 'isShowingDefaultNewRange', 'isNewContent',
  'isGloballyHidden', 'getNewCounts', 'applyFilters', 'restoreFilterStateFromURL', 'updateURL',
  'captureFilterState', 'restoreRankingState', 'handleCountryClick', 'handleTagClick', 'loadMore']) {
  const start = html.indexOf(`        function ${name}(`);
  assert(start >= 0, name);
  const end = html.indexOf('\n        }', start) + '\n        }'.length;
  vm.runInContext(html.slice(start, end), context);
}

// Stop the production filter immediately before sorting/rendering; exercise its real predicate.
const stopAfterFilter = new Error('filter captured');
const realApplyFilters = context.applyFilters;
let filtered = [];
context.applyFilters = () => {
  try { realApplyFilters(); } catch (error) { if (error !== stopAfterFilter) throw error; }
};
function installNews(rows) {
  context.NEWS_DATA = rows;
  Object.defineProperty(rows, 'filter', {configurable: true, value(predicate) {
    filtered = Array.prototype.filter.call(this, predicate);
    throw stopAfterFilter;
  }});
}
function show() { context.applyFilters(); return filtered.map(item => item.id); }
function open(search = '') { location.search = search; context.restoreFilterStateFromURL({render: false}); }
const countries = ['jp', 'cn', 'in', 'us', 'eu'];
const issue = Array.from({length: 46}, (_, i) => ({
  id: `issue${i}`, date: i < 35 ? '2026-09-17' : '2026-09-16', digestDate: '2026-09-17',
  country: countries[i % countries.length], tags: ['照明'], title: `記事${i}`, desc: '説明',
}));
// Current publication membership is authoritative even when a legacy item lacks digestDate.
delete issue[45].digestDate;
const archives = [{id: 'archive1', date: '2026-09-14', digestDate: '2026-09-16',
  country: 'jp', tags: ['照明'], title: '過去号の記事', desc: '説明'},
  {id: 'legacy1', date: '2026-09-15', country: 'jp', tags: [], title: '旧形式の記事', desc: '説明'}];
const originalDates = issue.map(item => item.date);
installNews([...issue, ...archives]);
context.window.EXTERIOR_PUBLICATION_STATUS = {issue_date: '2026-09-17', processed_through: '2026-09-17',
  target_dates: ['2026-09-17'], lookback_start: '2026-09-11', selected_count: 46,
  selected_news_ids: issue.map(item => item.id)};
context.setNewDateRangeFromNews(context.NEWS_DATA);

open();
assert.equal(elements.dateFrom.value, '2026-09-17');
assert.equal(elements.dateTo.value, '2026-09-17');
assert.equal(elements.dateBasis.hidden, false);
assert.equal(elements.dateBasis.value, 'issue');
assert.equal(context.visibleLimit, 46);
assert.equal(context.isShowingDefaultNewRange(), true);
assert.deepEqual(show(), issue.map(item => item.id), 'single issue includes all 11 earlier source dates');
assert.deepEqual(issue.map(item => item.date), originalDates, 'filter must never redate original articles');

context.handleCountryClick({target: {closest: () => ({dataset: {country: 'jp'}})}});
assert.equal(context.newOnly, false);
assert.deepEqual(filtered.map(item => item.id), issue.filter(item => item.country === 'jp').map(item => item.id));
assert.match(location.search, /dateBasis=issue/);
const countryURL = location.search;
open(countryURL);
assert.deepEqual(show(), issue.filter(item => item.country === 'jp').map(item => item.id), 'URL round trip retains issue basis');
context.handleTagClick({target: {closest: () => ({dataset: {tag: '照明'}})}});
assert.equal(elements.dateBasis.value, 'issue');
assert.equal(filtered.length, 10, 'tag change retains lookback items from the selected issue');

open();
context.rankingBackState = context.captureFilterState();
elements.dateBasis.value = 'source';
elements.dateFrom.value = '';
context.restoreRankingState({fromPopState: true});
assert.equal(elements.dateBasis.value, 'issue');
assert.equal(filtered.length, 46, 'return from detail restores the complete issue');

// Old links continue to mean original source dates; explicit basis is preserved in shared links.
open('?from=2026-09-17&to=2026-09-17');
assert.equal(elements.dateBasis.value, 'source');
assert.equal(show().length, 35);
assert.equal(context.isShowingDefaultNewRange(), false);
context.updateURL('push');
assert.match(location.search, /dateBasis=source/);
open(location.search);
assert.equal(show().length, 35);
open('?dateBasis=source&from=2026-09-16&to=2026-09-16');
assert.equal(show().length, 11);
open('?dateBasis=issue&from=2026-09-16&to=2026-09-16');
assert.deepEqual(show(), ['archive1'], 'older issue uses its digest date, not source date');
assert.equal(context.getNewsFilterDate(archives[1]), '2026-09-15', 'legacy records remain accessible');

open();
context.loadMore();
assert.equal(elements.dateFrom.value, '');
assert.equal(elements.dateBasis.value, 'issue');
assert.equal(filtered.length, 48, 'load more opens older issues without losing current lookback items');
const archiveURL = location.search;
open(archiveURL);
assert.equal(show().length, 48, 'archive range survives URL restore, including its blank start');

// An inverted range clears the lower bound before filtering, matching the displayed inputs.
open('?dateBasis=source&from=2026-09-18&to=2026-09-17');
assert.equal(show().length, 48);
assert.equal(elements.dateFrom.value, '');

context.window.DAILYNEWS_CONFIG.id = 'interior';
context.setNewDateRangeFromNews(context.NEWS_DATA);
open();
assert.equal(elements.dateBasis.hidden, true);
assert.equal(elements.dateBasis.value, 'source');
assert.equal(context.isShowingDefaultNewRange(), true);
assert.equal(show().length, 35, 'interior retains original publication-date filtering');
open('?dateBasis=issue&from=2026-09-16&to=2026-09-16');
assert.equal(context.getDateFilterBasis(), 'source');
assert.equal(show().length, 11, 'exterior URL parameter cannot change interior date semantics');
console.log('Exterior date UI: 46-item issue, original dates, countries/tags, URLs, detail return, archives, interior PASS');
