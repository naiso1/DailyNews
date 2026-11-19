'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');

// Exercise the real renderer with an in-memory DOM; no accounts or provider calls.
class Node {
  constructor(tag){this.tag=tag;this.children=[];this.dataset={};this.hidden=false;this.classes=new Set();this.classList={toggle:(name,on)=>on?this.classes.add(name):this.classes.delete(name)};}
  set textContent(text){this.text=String(text);this.children=[];}
  get textContent(){return (this.text||'')+this.children.map(n=>n.textContent).join('');}
  append(...nodes){this.children.push(...nodes);}
  replaceChildren(...nodes){this.text='';this.children=nodes;}
  get childElementCount(){return this.children.length;}
}
function fixture(shared=true){
  const publicReply=shared?new Node('div'):null,privateReply=new Node('div'),button=new Node('button');
  if(publicReply){publicReply.dataset.copilotPublicAnswer='waiting';publicReply.textContent='回答を待っています。';}
  const comment={querySelector:()=>publicReply};
  const box={closest:()=>comment,querySelector:s=>s==='.copilot-question'?button:privateReply};
  let refreshed=0,requests=0;
  const window={DAILYNEWS_CONFIG:{},addEventListener(){},dailyNewsRefreshCommentAnswers:()=>{refreshed++;return Promise.resolve();}};
  const document={querySelectorAll:()=>[box],createElement:tag=>new Node(tag),createTextNode:text=>{const n=new Node('text');n.textContent=text;return n;}};
  const script=fs.readFileSync(require.resolve('../../dailynews_copilot.js'),'utf8')
    .replace('  window.dailyNewsCopilot={','  window.testRender=render;\n  window.dailyNewsCopilot={');
  vm.runInNewContext(script,{window,document,location:{search:'?copilot=classic',protocol:'http:',hash:''},URLSearchParams,Map,
    fetch:()=>{requests++;throw Error('Unexpected provider/API request');}});
  return {publicReply,privateReply,button,render:window.testRender,refreshes:()=>refreshed,requests:()=>requests};
}
test('one comment answer slot from initial loading through pending and saved completion',()=>{
  const f=fixture(),state={key:'jp1-1',itemId:'jp1',own:true,job:null};
  f.render(state);assert.match(f.publicReply.textContent,/回答を待っています/);
  for(const job of [null,{status:'queued'},{status:'submitted'}]){
    Object.assign(state,{loading:!job,job});f.render(state);
    assert.equal(f.privateReply.hidden,true);assert.equal(f.privateReply.childElementCount,0);
    assert.match(f.publicReply.textContent,/Copilotの回答/);
    assert.doesNotMatch(f.publicReply.textContent,/自分だけ|みんなに|公開済み/);
  }
  state.loading=false;state.job={status:'done',answer:'回答',publicCommentAnswer:{status:'published',answer:'保存した回答'}};
  f.render(state);f.render(state);
  assert.match(f.publicReply.textContent,/保存した回答/);assert.equal(f.privateReply.hidden,true);
  assert.equal(f.refreshes(),1);assert.equal(f.requests(),0);
});
test('connection errors and explicit retry survive without a second answer or exposed conversation link',()=>{
  const f=fixture(),state={key:'jp1-1',itemId:'jp1',own:true,error:'接続を確認してください。'};
  f.render(state);assert.match(f.publicReply.textContent,/接続を確認/);assert.equal(f.privateReply.hidden,true);
  state.error='';state.job={status:'needs_review',conversationUrl:'https://copilot.cloud.microsoft/chat/conversation/example'};
  f.render(state);
  assert.match(f.publicReply.textContent,/自動再送を停止/);
  assert.equal(f.privateReply.hidden,false);assert.ok(f.privateReply.classes.has('copilot-answer-actions'));
  assert.ok(f.privateReply.children.some(n=>n.textContent==='確認して再試行'&&typeof n.onclick==='function'));
  assert.ok(f.privateReply.children.some(n=>n.tag==='a'));
  assert.equal(f.publicReply.children.some(n=>n.tag==='a'),false);
  assert.equal(f.requests(),0);
});
test('legacy private answers keep their explicit share action and saved answers are not overwritten',()=>{
  const f=fixture(false);f.render({key:'jp1-1',own:true,job:{status:'done',answer:'以前の回答',completedAt:'2026-11-19T00:00:00Z'}});
  assert.equal(f.privateReply.hidden,false);assert.match(f.privateReply.textContent,/以前の回答/);
  assert.ok(f.privateReply.children.some(n=>n.className==='copilot-share'));
  assert.doesNotMatch(f.privateReply.textContent,/自分だけ|みんなに/);
  const saved=fixture();saved.publicReply.dataset.copilotPublicAnswer='published';saved.publicReply.textContent='保存済みの回答';
  saved.render({key:'jp1-1',job:{status:'submitted'}});
  assert.equal(saved.publicReply.textContent,'保存済みの回答');assert.equal(saved.privateReply.hidden,true);
});
