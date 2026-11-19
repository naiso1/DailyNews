'use strict';
const assert=require('node:assert/strict');
const {buildQuestion,validateQuestion,buildCommentPrompt}=require('./copilot-context');
const news=(id,date,title,extra={})=>({id,date,title,desc:'製品の要約',url:'https://example.com/'+id,tags:[],...extra});
const catalog={range:{start:'2026-11-17',end:'2026-11-17'},rows:[
 news('jp1','2026-11-17','内装のアンビエント照明'),news('us1','2026-11-16','内装イルミの制御'),
 news('eu1','2026-11-17','内装シート'),news('cn1','2026-11-10','古い発表の特別掲載',{supplementIssueDate:'2026-11-17'}),
 news('in1','2026-11-17','重複',{duplicateOf:'jp1'}),news('in2','2026-11-16','外装フェンダー')
]};
const personal={scope:'new',question:'今日のニュースで私に関係するニュースをピックアップして'};
let result=buildQuestion(personal,catalog);
assert.deepEqual(result.sources.map(s=>s.id).sort(),['cn1','eu1','jp1']);
assert.equal(result.context.used,3);assert.match(result.prompt,/本人のCopilotで利用可能/);
for(const question of ['今日のニュースの考察教えて','本日のニュースを分析して','重要な変化と開発への示唆は？','私に関係するニュースをピックアップして','照明担当として気になる話題を整理して','宇宙ロケットの話はある？']){
 result=buildQuestion({scope:'new',question},catalog);
 assert.deepEqual(result.sources.map(s=>s.id).sort(),['cn1','eu1','jp1'],question);
 assert.equal(result.context.matched,result.context.total);
}
result=buildQuestion({scope:'all',question:'ニュース全体の考察を教えて'},catalog);
assert.equal(result.context.used,5);assert.match(result.prompt,/製品開発への示唆/);
result=buildQuestion({scope:'all',question:'内装イルミに関するトレンドを教えて'},catalog);
assert.deepEqual(result.sources.map(s=>s.id).sort(),['jp1','us1']);assert.equal(result.context.total,5);
assert.throws(()=>buildQuestion({scope:'all',question:'宇宙ロケット'},catalog),{safeCode:'NO_RELEVANT_NEWS'});
assert.deepEqual(buildQuestion({scope:'all',question:'内装イルミの考察と分析を教えて'},catalog).sources.map(s=>s.id).sort(),['jp1','us1']);
result=buildQuestion(personal,{...catalog,newIds:['us1','in2']});assert.deepEqual(result.sources.map(s=>s.id).sort(),['cn1','in2','us1']);
assert.throws(()=>buildQuestion(personal,{...catalog,newIds:[],range:{}}),{safeCode:'NO_NEWS'});
assert.notEqual(buildQuestion(personal,catalog).fingerprint,buildQuestion(personal,{...catalog,range:{start:'2026-11-18',end:'2026-11-18'},newIds:['jp1']}).fingerprint);
assert.equal(buildQuestion(personal,catalog).fingerprint,buildQuestion(personal,{...catalog,rows:catalog.rows.slice(0,3)}).fingerprint);
const large={...catalog,rows:Array.from({length:100},(_,i)=>news('jp'+i,'2026-11-17','イルミ'.repeat(60),{desc:'長い要約'.repeat(200),url:'https://example.com/?'+('a'.repeat(2500))}))};
result=buildQuestion(personal,large);assert.ok(result.prompt.length<30000);assert.ok(result.sources.length<=80);assert.ok(result.sources.every(s=>!s.url));
assert.equal(buildQuestion({scope:'all',question:'イルミ'},large).sources.length,30);
console.log('PASS: NEW range and supplementation, exterior selected IDs, topical retrieval, duplicate exclusion, bounds, no invented matches, per-issue idempotency');
const general={scope:'general',question:'なぜ車に乗ると酔うの？'};
result=buildQuestion(general,{rows:[],range:{}});
assert.equal(result.context.scope,'general');assert.equal(result.context.used,0);
assert.deepEqual(result.sources,[]);assert.equal(result.maxAnswerChars,400);
assert.ok(result.prompt.length<30000);assert.match(result.prompt,/記事との関連付けは不要/);
assert.equal(result.fingerprint,buildQuestion(general,{rows:catalog.rows,range:{}}).fingerprint);
assert.notEqual(result.fingerprint,buildQuestion({...general,question:'PETとABSの違いは？'},{rows:[],range:{}}).fingerprint);
for(const body of [{...general,itemId:'jp1'},{...general,article:{title:'偽の資料'}},{...general,userId:9},{...general,question:' '},{...general,scope:'anything'}])assert.throws(()=>validateQuestion(body),{safeCode:'INVALID_REQUEST'});
const commentPayload={article:{title:'車内エンタメ',summary:'筆者は否定的',url:'https://example.com/article'},question:'@Copilot 読者コメントの評価は？'};
const commentPrompt=buildCommentPrompt(commentPayload);
assert.deepEqual(JSON.parse(commentPrompt.split('\n').at(-1)),commentPayload);
assert.match(commentPrompt,/日本語200文字以内/);assert.match(commentPrompt,/一般知識でも答え/);
assert.match(commentPrompt,/読者コメントと記事筆者の論調は別/);
assert.match(commentPrompt,/URLが渡されただけで閲覧済みとは扱わず/);
assert.match(commentPrompt,/個人向けメモリは参照も記載もしない/);
console.log('PASS: general questions without articles, source/identity validation, bounded answers and public-comment source separation');
