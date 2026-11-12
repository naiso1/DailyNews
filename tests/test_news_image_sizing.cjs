const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const html = fs.readFileSync(path.join(__dirname, '..', '内装製品デイリーニュース.html'), 'utf8');
const ctx = vm.createContext({URL});
for (const name of ['getDisplayImageUrl', 'setNewsImageSource', 'retryOriginalNewsImage']) {
  const start = html.indexOf(`        function ${name}(`);
  const end = html.indexOf('\n        }', start) + '\n        }'.length;
  assert(start >= 0, name);
  vm.runInContext(html.slice(start, end), ctx);
}
const display = ctx.getDisplayImageUrl;
const hearst = 'https://hips.hearstapps.com/hmg-prod/images/interior.jpg';
const valnet = 'https://static0.topspeedimages.com/wordpress/wp-content/uploads/2026/interior.jpg';
const pr = 'https://prcdn.freetls.fastly.net/release_image/1/2/interior.jpg';
assert.equal(new URL(display(hearst)).searchParams.get('resize'), '980:*');
const cropped = new URL(display(hearst+'?crop=1xw:0.75xh;0,0.1xh&resize=2000:1500&quality=90#photo'));
assert.equal(cropped.searchParams.get('resize'), '980:735');
assert.equal(cropped.searchParams.get('crop'), '1xw:0.75xh;0,0.1xh');
assert.equal(cropped.searchParams.get('quality'), '90');
assert.equal(cropped.hash, '#photo');
for (const host of ['topspeedimages', 'carbuzzimages']) {
  const url = new URL(display(valnet.replace('topspeedimages', host)+'?w=1600&h=900&fit=crop'));
  assert.equal(url.searchParams.get('w'), '980');
  assert.equal(url.searchParams.get('h'), '551');
  assert.equal(url.searchParams.get('fit'), 'crop');
}
const press = new URL(display(pr+'?width=2400&height=1260&fit=bounds&auto=webp'));
assert.equal(press.searchParams.get('width'), '980');
assert.equal(press.searchParams.get('height'), '515');
assert.equal(press.searchParams.get('auto'), 'webp');
for (const unchanged of [
  undefined, '', 'images/copilot_concept.png', 'data:image/png;base64,AA==',
  'https://example.com/photo.jpg?width=4000',
  hearst+'?resize=640:*', hearst+'?resize=980:*', hearst+'?resize=*:400',
  valnet+'?w=640&h=360', valnet+'?h=600', valnet+'?w=auto', pr+'?width=536',
  hearst.replace('hips.hearstapps.com', 'hips.hearstapps.com.example.invalid'),
  hearst.replace('https://', 'https://user:pass@'), hearst.replace('.jpg', '.gif'),
  hearst.replace('.jpg', '.svg'), hearst.replace('/hmg-prod/images/', '/other/'),
  ...['X-Amz-Signature', 'X-Goog-Credential', 'sig', 'Signature', 's', 'token', 'access_token', 'Expires'].map(k => hearst+'?'+k+'=fixture'),
]) assert.equal(display(unchanged), unchanged, String(unchanged));
assert.equal(display('https://example.com/a.jpg?a=1&amp;b=2'), 'https://example.com/a.jpg?a=1&b=2');
for (const original of [hearst, valnet, pr]) {
  const result = display(original);
  assert.equal(new URL(result).origin, new URL(original).origin, 'must stay on publisher CDN');
  assert.equal(display(result), result, 'normalization is idempotent');
}
assert.equal(display('https://images.cdn.autocar.co.uk/sites/files/styles/car_review_image_190/public/a.jpg?itok=x'),
  'https://images.cdn.autocar.co.uk/sites/files/a.jpg');
assert.match(display('https://media.autoexpress.co.uk/image/private/s--x--/t_rss_image_w_845/a.jpg'), /f_auto,t_content-image-full-desktop@1/);

const img = {dataset: {}, src: '', getAttribute(name) { return this[name]; }};
ctx.setNewsImageSource(img, hearst);
assert.equal(img.dataset.originalSrc, hearst, 'retain original URL for editing and retry');
assert.notEqual(img.src, hearst);
assert.equal(ctx.retryOriginalNewsImage(img), true);
assert.equal(img.src, hearst);
assert.equal(ctx.retryOriginalNewsImage(img), false, 'never retry in a loop');
ctx.setNewsImageSource(img, valnet);
assert.equal(ctx.retryOriginalNewsImage(img), true, 'carousel switching resets retry state');
ctx.setNewsImageSource(img, 'https://example.com/photo.jpg');
assert.equal(ctx.retryOriginalNewsImage(img), false, 'unknown publisher gets no redundant retry');
console.log('News image sizing PASS: verified CDNs, width/aspect/crop, original URLs, signatures, unknown/local images and bounded retry');
