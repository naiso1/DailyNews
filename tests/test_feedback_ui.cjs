const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.join(__dirname,'..');
for (const file of ['内装製品デイリーニュース.html','content/exterior/内装製品デイリーニュース.html']) {
  const html=fs.readFileSync(path.join(root,file),'utf8');
  for (const match of html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)) {
    if (match[1].trim()) new vm.Script(match[1]);
  }
  const context=vm.createContext({window:{DAILYNEWS_CONFIG:{id:'interior'}}});
  for(const name of ['getSearchBlob','classifyLighting','deriveLocalTags']) {
    const start=html.indexOf(`        function ${name}(`);
    const end=html.indexOf('\n        }',start)+'\n        }'.length;
    vm.runInContext(html.slice(start,end),context);
  }
  vm.runInContext(`const LOCAL_TAG_RULES=[{tag:'イルミ',words:['イルミ','照明','led']},{tag:'HMI',words:['hmi']}];
    const EXTERIOR_TAG_RULES=[{tag:'灯火・照明',words:['ヘッドライト','アンビエント']}];`,context);
  assert.equal(context.classifyLighting({title:'車室内の照明に透光加飾'}),'interior');
  assert.equal(context.classifyLighting({title:'ヘッドライトと発光エンブレム'}),'exterior');
  assert.equal(context.classifyLighting({title:'ヘッドライトと室内灯を刷新'}),'both');
  assert.equal(context.classifyLighting({title:'照明製品を発売'}),'');
  assert.equal(context.classifyLighting({title:'外装アンビエント照明を搭載'}),'exterior');
  assert.equal(context.classifyLighting({title:'コンソールの造形を変更。外装照明を刷新した。'}),'exterior');
  assert.equal(context.classifyLighting({title:'Dashboard redesigned. Exterior lighting refreshed.'}),'exterior');
  assert.ok(context.deriveLocalTags({title:'LEDヘッドライト',tags:['イルミ']}).every(t=>t!=='イルミ'));
  assert.ok(context.deriveLocalTags({title:'大型OLEDディスプレイ',tags:['イルミ']}).every(t=>t!=='イルミ'));
  assert.ok(context.deriveLocalTags({title:'室内灯とヘッドライト',tags:[]}).includes('イルミ'));
  assert.ok(context.deriveLocalTags({title:'Cabin ambient lighting',tags:[]}).includes('イルミ'));
  context.window.DAILYNEWS_CONFIG.id='exterior';
  assert.ok(context.deriveLocalTags({title:'ヘッドライト',tags:[]}).includes('灯火・照明'));
  assert.match(html,/openFeedback\('\$\{n\.id\}', 'news'\)/);
  assert.match(html,/openFeedback\('\$\{idea\.id\}', 'idea'\)/);
  assert.match(html,/availableIdeas = ideas.filter\(idea => !isGloballyHidden\(idea.id\)/);
  assert.match(html,/tag === "イルミ"[\s\S]{0,80}n.tags.includes\(tag\)/);
}

const client=fs.readFileSync(path.join(root,'dailynews_client.js'),'utf8');
const start=client.indexOf('async function submitArticleRemoval(');
const end=client.indexOf('\nwindow.requestArticleRemoval',start);
let sent;
const fields={
  '#articleRemovalReason':{value:'写真と記事が一致しません'},
  '#articleRemovalReasonCode':{value:'image_mismatch'},
  '#articleRemovalError':{},'.article-removal-submit':{},
};
const overlay={dataset:{itemId:'123',itemKind:'idea',sourceUrl:''},querySelector:s=>fields[s],_closeRemovalDialog(){}};
const context=vm.createContext({window:{DAILYNEWS_CONFIG:{id:'exterior'},dispatchEvent(){}},
  CustomEvent:function(){},getClientId:()=> 'test-client',mergeInteractionData(){},
  apiRequest:async(url,options)=>{sent={url,...options};return{};}});
vm.runInContext(client.slice(start,end),context);
(async()=>{
  await context.submitArticleRemoval({preventDefault(){},currentTarget:{closest:()=>overlay}});
  assert.equal(sent.url,'/interactions/123/hidden');
  assert.equal(sent.body.reasonCode,'image_mismatch');assert.equal(sent.body.itemKind,'idea');
  assert.equal(sent.body.edition,'exterior');assert.equal(sent.body.reason,fields['#articleRemovalReason'].value);
  assert.equal(fields['.article-removal-submit'].disabled,false);
  console.log('Feedback UI: target bindings, reason payload, archive lighting tags and inline script syntax PASS');
})().catch(error=>{console.error(error);process.exitCode=1;});
