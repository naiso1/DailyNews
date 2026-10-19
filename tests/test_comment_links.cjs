const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '..', 'dailynews_client.js'), 'utf8');
const ctx = vm.createContext({URL});
for (const name of ['escapeHtml', 'formatCommentText']) {
  const start = source.indexOf(`function ${name}(`);
  const end = source.indexOf('\n}', start) + 2;
  assert(start >= 0 && end > start);
  vm.runInContext(source.slice(start, end), ctx);
}
const format = ctx.formatCommentText;
assert.equal(format('URLのないコメント & <確認>'), 'URLのないコメント &amp; &lt;確認&gt;');
const two = format('参考：https://example.com/a?x=1&y=2。\nこちらも http://IEWEB01/exterior/');
assert.equal((two.match(/<a /g) || []).length, 2);
assert(two.includes('href="https://example.com/a?x=1&amp;y=2"'));
assert(two.includes('</a>。\nこちらも '));
assert.equal((two.match(/target="_blank" rel="noopener noreferrer"/g) || []).length, 2);
for (const [input, expected] of [
  ['(https://example.com/a_(b)).', 'https://example.com/a_(b)'],
  ['（https://example.com/資料）。', 'https://example.com/資料'],
  ['https://example.com/report.pdf#page=4,', 'https://example.com/report.pdf#page=4'],
  ['https://[::1]/path]', 'https://[::1]/path'],
  ['HTTPS://EXAMPLE.COM/path', 'HTTPS://EXAMPLE.COM/path'],
]) assert(format(input).includes(`href="${expected}"`), input);
for (const text of ['http://', 'https://.', 'javascript:alert(1)', 'data:text/html,<script>alert(1)</script>']) {
  assert(!format(text).includes('<a '), text);
}
const unsafe = format('<img src=x onerror=alert(1)> https://example.com/?x=<script>alert(1)</script> " onmouseover="alert(1)');
assert(!unsafe.includes('<img') && !unsafe.includes('<script'));
assert(unsafe.includes('&lt;img') && unsafe.includes('&lt;script'));
assert(!unsafe.includes('href="javascript:'));
console.log('PASS: comment URLs, query strings, Japanese punctuation, balanced brackets, multiple links, and escaped markup.');
