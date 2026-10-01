const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const html = fs.readFileSync(path.join(__dirname, '..', '内装製品デイリーニュース.html'), 'utf8');
const elements = {lastUpdated: {}, lastUpdatedLabel: {}};
const context = vm.createContext({window: {DAILYNEWS_CONFIG: {id: 'exterior'}}, NEW_DATE_RANGE: {},
  NEWS_DATA: [], document: {getElementById: id => elements[id]}});
for (const name of ['normalizeExteriorPublication', 'isNewContent',
                    'isNewInsightDate', 'setNewDateRangeFromNews', 'normalizeIsNewFlags',
                    'getLatestDate', 'formatDateTime', 'updateUpdatedAt']) {
  const start = html.indexOf(`        function ${name}(`);
  assert(start >= 0, name);
  const end = html.indexOf('\n        }', start) + '\n        }'.length;
  vm.runInContext(html.slice(start, end), context);
}
const receipt = {edition_id: 'exterior', status: 'published', processed_through: '2026-09-15',
  issue_date: '2026-09-15', lookback_start: '2026-09-09', target_dates: ['2026-09-15'],
  source_dates: ['2026-09-09', '2026-09-15'], selected_count: 2, supplemental_count: 1,
  selected_news_ids: ['jp2', 'cn3']};
assert(context.normalizeExteriorPublication(receipt));
const paperReceipt = {...receipt, papers_enabled: true, paper_lookback_start: '2026-08-17', maximum_papers: 5,
  selected_paper_count: 1, selected_news_ids: ['jp2', 'paper3'], source_dates: ['2026-08-20', '2026-09-15'], supplemental_count: 0};
assert(context.normalizeExteriorPublication(paperReceipt));
for (const change of [{papers_enabled: false}, {selected_paper_count: 0}, {maximum_papers: 0},
                      {paper_lookback_start: '2026-08-16'}, {source_dates: ['2026-08-16']}]) {
  assert.equal(context.normalizeExteriorPublication({...paperReceipt, ...change}), null);
}
for (const change of [{selected_news_ids: ['jp2', 'jp2']}, {lookback_start: '2026-09-08'},
                      {source_dates: ['2026-09-16']}, {supplemental_count: 3}]) {
  assert.equal(context.normalizeExteriorPublication({...receipt, ...change}), null);
}
context.window.EXTERIOR_PUBLICATION_STATUS = receipt;
context.setNewDateRangeFromNews([]);
assert.equal(context.NEW_DATE_RANGE.start, '2026-09-15');
assert.equal(context.NEW_DATE_RANGE.end, '2026-09-15');
const news = [{id: 'jp2', date: '2026-09-15'}, {id: 'cn3', date: '2026-09-09'},
              {id: 'jp1', date: '2026-09-14'}];
context.normalizeIsNewFlags(news);
assert.deepEqual(news.map(row => row.isNew), [true, true, false]);
assert.equal(context.isNewInsightDate('2026-09-15'), true);
assert.equal(context.isNewInsightDate('2026-09-09'), false);
context.window.EXTERIOR_PUBLICATION_STATUS.updated_at = '2026-10-01T05:29:20+09:00';
context.updateUpdatedAt();
assert.equal(elements.lastUpdatedLabel.textContent, '更新');
assert.equal(elements.lastUpdated.textContent, context.formatDateTime(new Date('2026-10-01T05:29:20+09:00')));
assert(!html.includes('exteriorPublicationStatus'), 'no exterior-only issue/count banner');
assert(!html.includes('editionMailSettings'), 'mail preferences use the shared account UI');
assert(!html.includes('contentCategoryRow'), 'both editions use the same filter rows');
context.window.EXTERIOR_PUBLICATION_STATUS.updated_at = 'invalid';
context.NEWS_DATA = news;
context.updateUpdatedAt();
assert.equal(elements.lastUpdated.textContent, '2026-09-15', 'fallback is the article date, not a fabricated update time');
context.window.DAILYNEWS_CONFIG.id = 'interior';
context.window.NEWS_UPDATED_AT = '2026-10-01 01:30';
context.updateUpdatedAt();
assert.equal(elements.lastUpdatedLabel.textContent, '更新');
assert.equal(elements.lastUpdated.textContent, '2026-10-01 01:30');
context.NEW_DATE_RANGE = {start: '2026-09-15', end: '2026-09-15'};
assert.equal(context.isNewContent(news[0]), true);
assert.equal(context.isNewContent(news[1]), false);
console.log('Edition UI: common header, issue IDs, original dates, update timestamps and interior behavior PASS');
