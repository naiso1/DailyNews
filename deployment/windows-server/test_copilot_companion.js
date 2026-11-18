'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const ui=require('../../dailynews_copilot_companion.js');
test('follow-up includes only an explicitly completed answer within server limit',()=>{
 assert.equal(ui.composeQuestion(' 質問 '),'質問');
 assert.throws(()=>ui.composeQuestion('x',{status:'needs_review',question:'prior',answer:'unknown'}),/NO_PRIOR_ANSWER/);
 const result=ui.composeQuestion('比較して',{status:'done',question:'前の質問',answer:'参考回答'});
 assert.match(result,/前の回答（参考）：参考回答/);assert.match(result,/追加の質問：比較して/);
 assert.throws(()=>ui.composeQuestion('x'.repeat(1001)),/INVALID_REQUEST/);
 assert.throws(()=>ui.composeQuestion('x'.repeat(800),{status:'done',question:'q',answer:'a'.repeat(400)}),/FOLLOWUP_TOO_LONG/);
});
test('lost response blocks repeating identical scope/article/question',()=>{
 const input={scope:'article',itemId:'jp1',question:'q'};
 assert.equal(ui.canRepeat([{uncertain:true,input}],input),false);
 assert.equal(ui.canRepeat([{uncertain:true,input}],{...input,itemId:'jp2'}),true);
 assert.equal(ui.canRepeat([{uncertain:false,input}],input),true);
});
test('private state uses member identity and rejects unsafe/provider-impostor URLs',()=>{
 assert.notEqual(ui.identity({id:1,email:'a@example.com'}),ui.identity({id:2,email:'b@example.com'}));
 assert.equal(ui.httpUrl('javascript:alert(1)'),null);
 assert.equal(ui.httpUrl('https://copilot.microsoft.com.evil.test/',true),null);
 assert.equal(ui.httpUrl('http://copilot.microsoft.com/',true),null);
 assert.equal(ui.httpUrl('https://copilot.cloud.microsoft/chat/',true),'https://copilot.cloud.microsoft/chat/');
});
