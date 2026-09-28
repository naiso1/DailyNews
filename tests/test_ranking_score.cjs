const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const html = fs.readFileSync(path.join(__dirname, '..', '内装製品デイリーニュース.html'), 'utf8');
const elements = Object.fromEntries([
  'rankingList', 'rankingBody', 'rankingSort', 'rankingScope',
  'paperRankingList', 'paperRankingBody', 'paperRankingSort', 'paperRankingScope',
].map(id => [id, {innerHTML: '', value: id.endsWith('Scope') ? 'all' : 'score'}]));
const counts = {
  popular: {likes: 0, comments: 0, reads: 10000},
  liked: {likes: 1, comments: 0, reads: 1},
  discussed: {likes: 0, comments: 1, reads: 1},
  quiet: {likes: 0, comments: 0, reads: 0},
  viewed: {likes: 0, comments: 0, reads: 2},
  local: {likes: 0, comments: 0},
};
const interactions = {};
const rows = ['jp', 'paper'].flatMap(country => Object.keys(counts).map(key => {
  const id = `${country}-${key}`;
  interactions[id] = counts[key];
  return {id, country, date: '2026-09-28', title: id, img: ''};
}));
const ctx = vm.createContext({
  window: {interactionsData: interactions, getLocalReadCount: id => id.endsWith('-local') ? 3 : 0},
  document: {getElementById: id => elements[id]},
  visibleNewsData: () => rows,
  getLatestDate: items => items.map(n => n.date).sort().at(-1),
  activeCountries: new Set(['world']),
  updateRankingHeight() {},
  getDisplayImageUrl: src => src,
  getNewsImageUrl: n => n.img,
  COUNTRY_FLAGS: {}, COUNTRY_NAMES: {}, FALLBACK_SRC: '',
});
function extract(name) {
  const start = html.indexOf(`        function ${name}(`);
  assert(start >= 0, name);
  const marker = '\n        }';
  const end = html.indexOf(marker, start);
  assert(end > start, name);
  return html.slice(start, end + marker.length);
}
for (const name of [
  'calculateRankingScore', 'compareRankingItems', 'getRankingMetricValue',
  'filterRankingByCountry', 'getRankingEmptyMessage', 'getRankingScopeValue',
  'getRankingSortKey', 'getPaperRankingScopeValue', 'getPaperRankingSortKey',
  'renderRanking', 'renderPaperRanking',
]) vm.runInContext(extract(name), ctx);

const score = ctx.calculateRankingScore;
assert(score(0, 0, 1000000) < score(1, 0, 0), 'views alone must not outweigh a like');
assert(score(0, 0, 1000000) < score(0, 1, 0), 'views alone must not outweigh a comment');
assert(score(1, 0, 1000000) < score(0, 1, 0), 'a comment outweighs a like even with many reads');
assert.equal(score(0, 0, 20), score(0, 0, 10000), 'read contribution is capped');
assert(score(0, 0, 2) > score(0, 0, 1), 'reads still contribute before the cap');
assert.equal(score(0, 0, 0), 0);
assert.equal(score(-1, NaN, Infinity), 0, 'invalid counts cannot poison the score');

// Exercise both actual render paths so changing one calculation cannot leave
// the other ranking on the old view-dominated formula.
for (const [country, prefix, render] of [
  ['jp', 'ranking', ctx.renderRanking], ['paper', 'paperRanking', ctx.renderPaperRanking],
]) {
  const rankedIds = () => Array.from(elements[`${prefix}List`].innerHTML.matchAll(/data-news-id="([^"]+)"/g), m => m[1]);
  const expectOrder = suffixes => assert.deepEqual(rankedIds(), suffixes.map(s => `${country}-${s}`));
  render();
  expectOrder(['discussed', 'liked', 'popular', 'local', 'viewed']);
  for (const [sort, expected] of [
    ['reads', ['popular', 'local', 'viewed', 'liked', 'discussed']],
    ['likes', ['liked']], ['comments', ['discussed']],
  ]) {
    elements[`${prefix}Sort`].value = sort;
    render();
    expectOrder(expected);
  }
  elements[`${prefix}Sort`].value = 'score';
}
ctx.window.interactionsData = {};
ctx.window.getLocalReadCount = () => 0;
ctx.renderRanking();
ctx.renderPaperRanking();
assert.match(elements.rankingList.innerHTML, /ranking-empty/);
assert.match(elements.paperRankingList.innerHTML, /ranking-empty/);
console.log('PASS: reaction-first scores, read cap, news/paper rendering, explicit sorts, local reads, empty rankings');
