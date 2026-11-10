'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {createRequire}=require('node:module');
const file=path.resolve(__dirname,'../deployment/workstation/copilot/worker.js');
const temporary=path.resolve(__dirname,'../runtime/copilot-worker-tests');fs.mkdirSync(temporary,{recursive:true});
let ticks=0;
const box={module:{exports:{}},require:createRequire(file),process,Buffer,performance:{now:()=>ticks+=1000},
  setTimeout:fn=>setTimeout(fn,0),clearTimeout};
vm.runInNewContext(fs.readFileSync(file,'utf8'),box,{filename:file});
const {generate,validateRequest}=box.module.exports;
function fixture(options={}){
  const dir=fs.mkdtempSync(path.join(temporary,'job-'));
  const request={key:'a'.repeat(64),prompt:'正方形の部品画像',outputDir:dir,timeoutMs:30000};
  const state={sent:0,download:0,filled:0};
  const page={
    url:()=> 'https://copilot.cloud.microsoft/chat/',
    locator(selector){
      if(selector.includes('editor-target'))return{isVisible:async()=>true,fill:async()=>state.filled++};
      if(selector.includes('生成を停止する'))return{isVisible:async()=>!!options.timeout};
      if(selector.includes('ダウンロード'))return{count:async()=>options.notFresh||state.sent&&!options.timeout?1:0,isVisible:async()=>true,click:async()=>state.download++};
      if(selector.includes('送信'))return{waitFor:async()=>{},click:async()=>{assert.equal(JSON.parse(fs.readFileSync(path.join(dir,'phase.json'))).event,'sending');state.sent++;if(options.clickLost)throw new Error('lost after click');}};
      throw new Error('Unexpected selector');
    },
    evaluate:async()=>state.sent&&!options.timeout?1:0,
    waitForEvent:async()=>({suggestedFilename:()=> 'image.png',saveAs:async target=>fs.writeFileSync(target,Buffer.alloc(1500))}),
  };
  return{dir,request,state,page};
}
(async()=>{
  assert.throws(()=>validateRequest({}),/INVALID_REQUEST/);
  const successful=fixture();await generate(successful.page,successful.request);
  assert.equal(successful.state.sent,1);assert.equal(successful.state.download,1);
  const receipt=JSON.parse(fs.readFileSync(path.join(successful.dir,'result.json')));
  assert.equal(receipt.provider,'copilot');assert.equal(receipt.imageModel,'');
  await assert.rejects(generate(successful.page,successful.request),/NEEDS_REVIEW/);
  assert.equal(successful.state.sent,1);
  const lost=fixture({clickLost:true});await assert.rejects(generate(lost.page,lost.request),/lost after click/);
  await assert.rejects(generate(lost.page,lost.request),/NEEDS_REVIEW/);assert.equal(lost.state.sent,1);
  const old=fixture({notFresh:true});await assert.rejects(generate(old.page,old.request),/NOT_A_FRESH_CONVERSATION/);assert.equal(old.state.sent,0);
  const timeout=fixture({timeout:true});await assert.rejects(generate(timeout.page,timeout.request),/GENERATION_TIMEOUT/);
  await assert.rejects(generate(timeout.page,timeout.request),/NEEDS_REVIEW/);assert.equal(timeout.state.sent,1);
  // No credential material or browser state is involved in these fixtures.
  console.log('PASS: validation, save receipt, pre-click journal, no resend after lost click/timeout, fresh-chat guard');
})().catch(e=>{console.error(e);process.exitCode=1;});
