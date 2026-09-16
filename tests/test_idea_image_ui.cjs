const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const html = fs.readFileSync(path.join(__dirname, '..', '内装製品デイリーニュース.html'), 'utf8');
const context = vm.createContext({window: {DAILYNEWS_CONFIG: {id: 'interior', imageGenerationEnabled: true}}});
for (const name of ['escapeHtml', 'ideaImageLabel', 'renderIdeaImage']) {
  const start = html.indexOf(`        function ${name}(`);
  assert(start >= 0, name);
  const end = html.indexOf('\n        }', start) + '\n        }'.length;
  vm.runInContext(html.slice(start, end), context);
}

const idea = {title: '照明と加飾', img: 'images/concept.png'};
assert.match(context.renderIdeaImage({...idea, imageProvider: 'exabase'}), /AI生成イメージ（exaBase）/);
assert.match(context.renderIdeaImage({...idea, imageProvider: 'api', imageModel: 'test-model'}), /AI生成イメージ（API）/);
assert.equal(context.ideaImageLabel(idea), 'AI生成イメージ');
assert.equal(context.ideaImageLabel({...idea, imageProvider: 'unknown'}), 'AI生成イメージ');
assert.equal(context.ideaImageLabel({...idea, img: 'images/exabase_interior_2026-09-16_42.webp'}), 'AI生成イメージ（exaBase）');
assert.equal(context.ideaImageLabel({...idea, img: 'images/exabase_exterior_2026-09-15_9.png'}), 'AI生成イメージ（exaBase）');
assert.equal(context.ideaImageLabel({...idea, img: 'images/exabase_exterior_2026-09-15_9.png', imageProvider: 'api'}), 'AI生成イメージ（API）');
assert.equal(context.renderIdeaImage({...idea, img: ''}), '');

const escaped = context.renderIdeaImage({...idea, title: '照明"<試作>', img: 'images/concept.png?x="&y=1'});
assert.match(escaped, /alt="照明&quot;&lt;試作&gt;のAI生成イメージ"/);
assert.match(escaped, /src="images\/concept.png\?x=&quot;&amp;y=1"/);

context.window.DAILYNEWS_CONFIG = {id: 'exterior', imageGenerationEnabled: false};
assert.equal(context.renderIdeaImage(idea), '');
assert.match(context.renderIdeaImage({...idea, img: 'images/exabase_exterior_2026-09-15_9.png'}), /AI生成イメージ（exaBase）/);
console.log('Idea image UI: provider attribution, legacy unknown images, escaping and visibility PASS');
