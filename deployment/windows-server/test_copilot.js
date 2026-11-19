'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const {spawn}=require('node:child_process'),http=require('node:http');
const {createService,dpapi}=require('./copilot-service');
const {buildQuestion}=require('./copilot-context');
const root=fs.mkdtempSync(path.join(os.tmpdir(),'dailynews-copilot-')),hash=s=>crypto.createHash('sha256').update(s).digest('hex');
const alice={email:'alice@example.com'},bob={email:'bob@example.com'};let sends=0;
const mock=async()=>{let sent=false,inputText='';const locator=(kind)=>({
 waitFor:async()=>{},boundingBox:async()=>null,isVisible:async()=>kind!=='expand'&&kind!=='collapse'&&kind!=='stop',
 click:async(options)=>{if(kind==='send'&&!options?.trial){sends++;sent=true;}},fill:async(text)=>{inputText=text;},
 innerText:async()=>kind==='manager'?alice.email:kind==='input'?inputText:kind==='reply'&&sent?'記事の要約からは仕様を確認できません。元記事で操作方法を確認するとよいでしょう。':'',
 count:async()=>sent?1:0,last(){return this;},
});const page={url:()=>sent?'https://copilot.cloud.microsoft/chat/conversation/test-123':'https://copilot.cloud.microsoft/chat/',goto:async()=>{},setDefaultTimeout(){},waitForTimeout:async()=>{},keyboard:{press:async()=>{},insertText:async text=>{inputText=text;}},locator:s=>locator(s.includes('markdown')?'reply':'input'),getByRole:(role,{name})=>locator(role==='dialog'?'manager':name instanceof RegExp?'profile':({'送信':'send','サイド バーの展開':'expand','サイド バーを折りたたむ':'collapse','生成を停止する':'stop','応答のコピー':'copy'})[name])};return {browser:{close:async()=>{}},context:{storageState:async()=>({cookies:[],origins:[]})},page};};
async function main(){
 const member=path.join(root,'private/accounts',hash(alice.email));fs.mkdirSync(member,{recursive:true});
 fs.writeFileSync(path.join(member,'account.json'),JSON.stringify({email:alice.email,revision:'abcdef01',connected:true}));fs.writeFileSync(path.join(member,'abcdef01.bin'),await dpapi(Buffer.from('{"cookies":[],"origins":[]}'),true));
 const catalog={range:{start:'2026-11-17',end:'2026-11-17'},rows:[{id:'jp1',date:'2026-11-17',title:'内装照明',desc:'イルミの要約',url:'https://example.com/article',tags:['イルミ']}]};
 const svc=createService({root:path.join(root,'private'),edition:'interior',article:id=>id==='jp1'?{title:'test',desc:'summary',url:'https://example.com/article'}:null,comment:(id,c)=>id==='jp1'&&c===7?{comment_text:'仕様は？'}:null,question:q=>buildQuestion(q,catalog),launchOverride:mock});
 assert.equal(svc.accountStatus(bob).connected,false);assert.throws(()=>svc.submit(bob,'jp1',7),{safeCode:'ACCOUNT_NOT_CONNECTED'});
 const first=svc.submit(alice,'jp1',7),duplicate=svc.submit(alice,'jp1',7);assert.equal(duplicate.id,first.id);
 assert.throws(()=>svc.getJob(bob,first.id),{safeCode:'NOT_FOUND'});assert.throws(()=>svc.submit(alice,'https://bad',7),{safeCode:'INVALID_REQUEST'});
 let j;for(let n=0;n<45;n++){await new Promise(r=>setTimeout(r,300));j=svc.getJob(alice,first.id);if(j.status==='done')break;}
 assert.equal(j.status,'done');assert.equal(sends,1);assert.ok(j.answer.length<=200);assert.equal(svc.submit(alice,'jp1',7).sendAttemptCount,1);
 const question={scope:'new',question:'今日のニュースで私に関係するニュースをピックアップして'};
 const query=svc.submitQuestion(alice,question);assert.equal(svc.submitQuestion(alice,question).id,query.id);
 assert.throws(()=>svc.getJob(bob,query.id),{safeCode:'NOT_FOUND'});
 for(let n=0;n<45;n++){await new Promise(r=>setTimeout(r,300));j=svc.getJob(alice,query.id);if(j.status==='done')break;}
 assert.equal(j.status,'done');assert.equal(sends,2);assert.equal(j.sources[0].id,'jp1');assert.equal(j.context.used,1);
 assert.equal(svc.submitQuestion(alice,question).sendAttemptCount,1);
 // Simulate an unknown result persisted before a restart. Ordinary submits do
 // not resend it; an explicit retry archives it and deduplicates its token.
 const file=path.join(member,'jobs',query.id+'.json'),unknown=JSON.parse(fs.readFileSync(file));
 Object.assign(unknown,{status:'needs_review',code:'RESULT_UNCONFIRMED'});delete unknown.answer;
 fs.writeFileSync(file,JSON.stringify(unknown));assert.equal(svc.submitQuestion(alice,question).status,'needs_review');
 assert.throws(()=>svc.retry(bob,query.id,unknown.createdAt),{safeCode:'NOT_FOUND'});
 const retry=svc.retry(alice,query.id,unknown.createdAt);
 assert.equal(svc.retry(alice,query.id,unknown.createdAt).createdAt,retry.createdAt);
 assert.equal(fs.readdirSync(path.join(member,'attempt-history')).length,1);
 for(let n=0;n<45;n++){await new Promise(r=>setTimeout(r,300));j=svc.getJob(alice,query.id);if(j.status==='done')break;}
 assert.equal(j.status,'done');assert.equal(sends,3);assert.equal(svc.retry(alice,query.id,unknown.createdAt).status,'done');
 const generalInput={scope:'general',question:'なぜ車に乗ると酔うの？'},generalJob=svc.submitQuestion(alice,generalInput);
 assert.equal(svc.submitQuestion(alice,generalInput).id,generalJob.id);
 assert.throws(()=>svc.getJob(bob,generalJob.id),{safeCode:'NOT_FOUND'});
 for(let n=0;n<45;n++){await new Promise(r=>setTimeout(r,300));j=svc.getJob(alice,generalJob.id);if(j.status==='done')break;}
 assert.equal(j.status,'done');assert.equal(sends,4);assert.equal(j.scope,'general');assert.equal(j.context.used,0);assert.deepEqual(j.sources,[]);
 assert.equal(svc.submitQuestion(alice,generalInput).sendAttemptCount,1);
 await svc.disconnect(alice);assert.equal(svc.accountStatus(alice).connected,false);assert.equal(fs.existsSync(path.join(member,'abcdef01.bin')),false);await svc.close();
 const app=path.join(root,'app'),release=path.join(root,'releases/abcdef1');fs.mkdirSync(app);fs.mkdirSync(release,{recursive:true});
 for(const name of ['server.js','copilot-client.js','copilot-comment-answers.js','copilot-context.js','shared-identity.js'])fs.copyFileSync(path.join(__dirname,name),path.join(app,name));
 fs.writeFileSync(path.join(root,'active-release.txt'),'abcdef1');fs.writeFileSync(path.join(release,'news_data.js'),'window.LOADED_NEWS_DATA=[{id:"jp1",date:"2026-11-17",title:"内装照明",desc:"イルミの要約",url:"https://example.com"}];');fs.writeFileSync(path.join(release,'index.html'),'<title>test</title>');
 fs.mkdirSync(path.join(root,'data'),{recursive:true});fs.writeFileSync(path.join(root,'data/copilot-worker.json'),JSON.stringify({token:'a'.repeat(64),port:19084}));
 const port=19700+Math.floor(Math.random()*300),base='http://127.0.0.1:'+port;
 const child=spawn(process.execPath,[path.join(app,'server.js')],{env:{...process.env,DAILYNEWS_ROOT:root,DAILYNEWS_HOST:'127.0.0.1',DAILYNEWS_PORT:String(port),DAILYNEWS_ADMIN_EMAILS:''},stdio:['ignore','ignore','pipe']});let errors='';child.stderr.on('data',b=>errors+=b);
 let polling=true;
 async function worker(){while(polling){try{
   const headers={Authorization:'Bearer '+'a'.repeat(64),'Content-Type':'application/json','X-Forwarded-Proto':'https'};
   const r=await fetch(base+'/api/copilot-worker/poll',{method:'POST',headers,body:'{}'}),d=(await r.json()).job;if(!d)continue;
   assert.equal(d.user.email,alice.email);
   if(d.operation==='submit')assert.equal(d.context.comment.text,'仕様は？');
   if(d.operation==='submitQuestion'){
    if(d.context.question.scope==='general'){assert.deepEqual(d.context.question.sources,[]);assert.equal(d.context.question.context.used,0);assert.match(d.context.question.prompt,/記事との関連付けは不要/);}
    else {assert.equal(d.context.question.sources[0].id,'jp1');assert.equal(d.context.question.context.used,1);assert.match(d.context.question.prompt,/イルミの要約/);}
   }
   await fetch(base+'/api/copilot-worker/result',{method:'POST',headers,body:JSON.stringify(d.operation==='accountStatus'?{id:d.id,result:{connected:false,email:alice.email}}:{id:d.id,code:'ACCOUNT_NOT_CONNECTED'})});
  }catch(e){if(polling)throw e;}}
 }
 try {
  for(let n=0;n<40;n++){try{if((await fetch(base+'/health')).ok)break;}catch{}await new Promise(r=>setTimeout(r,150));}
  void worker();
  let r=await fetch(base+'/api/copilot/account');assert.equal(r.status,401);
  r=await fetch(base+'/api/copilot-worker/poll',{method:'POST',headers:{'Content-Type':'application/json','X-Forwarded-Proto':'https'},body:'{}'});assert.equal(r.status,403);
  r=await fetch(base+'/api/auth/register',{method:'POST',headers:{'Content-Type':'application/json',Origin:base},body:JSON.stringify({email:alice.email,displayName:'Alice',password:'test-local-password-123',clientId:'abcdefghijklmnop1234'})});assert.equal(r.status,201,errors);const cookie=r.headers.get('set-cookie').split(';')[0];
  const headers={Cookie:cookie,'Content-Type':'application/json',Origin:base};
  r=await fetch(base+'/api/interactions/jp1/comments',{method:'POST',headers,body:JSON.stringify({text:'仕様は？',clientId:'abcdefghijklmnop1234'})});assert.equal(r.status,201);const detail=await r.json(),commentId=detail.commentItems[0].id;
  assert.equal(detail.createdCommentId,commentId);
  r=await fetch(base+'/api/copilot/questions',{method:'POST',headers,body:JSON.stringify({scope:'new',question:'今日のニュースで私に関係するニュースをピックアップして'})});assert.equal(r.status,409);assert.equal((await r.json()).error.code,'ACCOUNT_NOT_CONNECTED');
  r=await fetch(base+'/api/copilot/questions',{method:'POST',headers,body:JSON.stringify(generalInput)});assert.equal(r.status,409);assert.equal((await r.json()).error.code,'ACCOUNT_NOT_CONNECTED');
  for(const body of [{scope:'new',question:'test',userId:1},{scope:'all',question:'test',sources:[{id:'jp9'}]},{scope:'all',question:'x'.repeat(1001)}]){
   r=await fetch(base+'/api/copilot/questions',{method:'POST',headers,body:JSON.stringify(body)});assert.equal(r.status,400);}
  r=await fetch(base+'/api/copilot/questions',{method:'POST',headers:{...headers,Origin:'https://evil.example'},body:'{}'});assert.equal(r.status,403);
  r=await fetch(base+'/api/copilot/connection',{method:'POST',headers,body:'{}'});assert.equal(r.status,426);
  r=await fetch(base+'/api/copilot/jobs',{method:'POST',headers:{...headers,Origin:'https://evil.example'},body:'{}'});assert.equal(r.status,403);
  r=await fetch(base+'/api/copilot/jobs',{method:'POST',headers,body:JSON.stringify({itemId:'jp1',commentId,userId:1})});assert.equal(r.status,400);
  r=await fetch(base+'/api/copilot/jobs',{method:'POST',headers,body:JSON.stringify({itemId:'jp1',commentId})});assert.equal(r.status,409);assert.equal((await r.json()).error.code,'ACCOUNT_NOT_CONNECTED');
  r=await fetch(base+'/api/copilot/account',{headers});assert.equal((await r.json()).connected,false);
 }finally{polling=false;child.kill();}
 console.log('PASS: article comments and cross-news questions, account isolation, one send, stored answers, server-only sources, disconnect, authentication, HTTPS and CSRF');
}
main().catch(e=>{console.error(e);process.exitCode=1;});
