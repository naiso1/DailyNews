const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const html = fs.readFileSync(path.join(__dirname, '..', '内装製品デイリーニュース.html'), 'utf8');
const context = vm.createContext({window: {DAILYNEWS_CONFIG: {id: 'exterior'}}, NEW_DATE_RANGE: {}});
for (const name of ['normalizeExteriorPublication', 'describeExteriorPublication', 'isNewContent',
                    'isNewInsightDate', 'setNewDateRangeFromNews', 'normalizeIsNewFlags']) {
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
assert.equal(context.describeExteriorPublication(receipt, news), '2026-09-15号：2件');
context.window.DAILYNEWS_CONFIG.id = 'interior';
context.NEW_DATE_RANGE = {start: '2026-09-15', end: '2026-09-15'};
assert.equal(context.isNewContent(news[0]), true);
assert.equal(context.isNewContent(news[1]), false);
console.log('Exterior issue UI: IDs, original dates, issue counts, legacy interior behavior PASS');
