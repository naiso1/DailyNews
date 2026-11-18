'use strict';
const assert=require('node:assert/strict');
const {preparePrompt}=require('./copilot-service');
async function main(){
 let fills=0,trials=0,clicks=0,value='';
 let focused=false,overlay=true,pointerAway=false;
 const input={boundingBox:async()=>({x:200,y:200,width:500,height:50}),click:async()=>{assert.equal(overlay,false);focused=true;},innerText:async()=>value};
 const page={url:()=> 'https://copilot.cloud.microsoft/chat/',waitForTimeout:async()=>{},
  locator:s=>s.includes('markdown')?{count:async()=>0}:input,
  mouse:{move:async()=>{pointerAway=true;}},
  keyboard:{press:async key=>{if(key==='Escape'){assert.ok(pointerAway);overlay=false;}else{assert.equal(key,'Control+A');assert.ok(focused);}},insertText:async text=>{fills++;value=fills===1?'':text+'\u200b\u200c';}},
  getByRole:()=>({click:async options=>{if(options?.trial)trials++;else clicks++;}})};
 const r=await preparePrompt(page,'確認する質問\n資料');assert.equal(r.attempt,2);assert.equal(fills,2);assert.equal(trials,1);assert.equal(clicks,0);
 await r.send.click();assert.equal(clicks,1);
 let focusAttempts=0;input.click=async()=>{if(++focusAttempts===1)throw Object.assign(new Error('covered'),{name:'TimeoutError'});};
 const focusRetry=await preparePrompt(page,'入力欄の再準備');assert.equal(focusRetry.attempt,2);assert.equal(clicks,1);
 page.keyboard.insertText=async()=>{value='';fills++;};const before=fills;
 await assert.rejects(preparePrompt(page,'失われる下書き'),{safeCode:'SEND_NOT_READY'});assert.equal(fills-before,3);assert.equal(clicks,1);
 page.url=()=> 'https://copilot.cloud.microsoft/chat/conversation/old-123';
 await assert.rejects(preparePrompt(page,'新規質問'),{safeCode:'NOT_A_FRESH_CONVERSATION'});
 console.log('PASS: draft reset and zero-width markers, bounded pre-send preparation, no extra Send, fresh-conversation guard');
}
main().catch(e=>{console.error(e);process.exitCode=1;});
