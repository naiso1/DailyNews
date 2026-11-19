'use strict';
// Real isolated API and SQLite with a fake worker. No production writes or provider calls.
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const {spawn}=require('node:child_process');
async function verify(edition){
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'dailynews-public-answer-')),app=path.join(root,'app'),release=path.join(root,'releases/abcdef3');
 fs.mkdirSync(app);fs.mkdirSync(release,{recursive:true});fs.mkdirSync(path.join(root,'data'));
 for(const n of ['server.js','shared-identity.js','copilot-client.js','copilot-comment-answers.js','copilot-context.js'])fs.copyFileSync(path.join(__dirname,n),path.join(app,n));
 fs.writeFileSync(path.join(root,'active-release.txt'),'abcdef3');fs.writeFileSync(path.join(release,'index.html'),'<title>test</title>');
 fs.writeFileSync(path.join(release,'news_data.js'),'window.LOADED_NEWS_DATA=[{id:"jp1",date:"2026-11-19",title:"記事",desc:"記事の掲載要約",url:"https://example.test/article"}];');
 fs.writeFileSync(path.join(release,'publication_status.json'),JSON.stringify({issue_date:'2026-11-19',selected_news_ids:['jp1']}));
 fs.writeFileSync(path.join(root,'data/copilot-worker.json'),JSON.stringify({token:'a'.repeat(64)}));
 const port=22000+Math.floor(Math.random()*2000),origin='http://127.0.0.1:'+port,api=origin+(edition==='exterior'?'/exterior':'')+'/api';
 const child=spawn(process.execPath,[path.join(app,'server.js')],{env:{...process.env,DAILYNEWS_ROOT:root,DAILYNEWS_HOST:'127.0.0.1',DAILYNEWS_PORT:String(port),DAILYNEWS_EDITION:edition},stdio:['ignore','ignore','pipe']});
 let errors='',running=true,workerTask,submits=0;child.stderr.on('data',b=>errors+=b);
 const controller=new AbortController(),jobs=new Map(),workerHeaders={Authorization:'Bearer '+'a'.repeat(64),'Content-Type':'application/json','X-Forwarded-Proto':'https'};
 const jobFor=(email,commentId)=>{const id=crypto.createHash('sha256').update(email+'|'+commentId).digest('hex');let j=jobs.get(id);if(!j){j={id,itemId:'jp1',commentId,status:'done',answer:'<script>unsafe</script> 掲載要約から確認できます。',completedAt:'2026-11-19T04:00:00.000Z',conversationUrl:'https://copilot.cloud.microsoft/chat/private'};jobs.set(id,j);}return j;};
 async function worker(){while(running){try{
  const r=await fetch(api+'/copilot-worker/poll',{method:'POST',headers:workerHeaders,body:'{}',signal:controller.signal});const {job:d}=await r.json();if(!d)continue;
  let result,code;
  if(d.operation==='submit'){submits++;result={...jobFor(d.user.email,d.args[1]),status:'queued',answer:undefined};}
  else if(d.operation==='current')result=jobFor(d.user.email,d.args[1]);
  else if(d.operation==='getJob'){result=jobs.get(d.args[0]);if(!result||jobFor(d.user.email,result.commentId).id!==result.id){result=null;code='NOT_FOUND';}}
  else code='INVALID_REQUEST';
  await fetch(api+'/copilot-worker/result',{method:'POST',headers:workerHeaders,body:JSON.stringify({id:d.id,result,code}),signal:controller.signal});
 }catch(e){if(running)throw e;}}}
 try{
  for(let n=0;n<60;n++){try{if((await fetch(origin+'/health')).ok)break;}catch{}await new Promise(r=>setTimeout(r,150));}
  async function register(name){const r=await fetch(api+'/auth/register',{method:'POST',headers:{Origin:origin,'Content-Type':'application/json'},body:JSON.stringify({email:name+'@example.test',displayName:name,password:'local-test-password-123',clientId:'abcdefghijklmnop1234'})});assert.equal(r.status,201,errors);return r.headers.get('set-cookie').split(';')[0];}
  const alice=await register('alice'),bob=await register('bob');
  const req=(route,cookie,method='GET',body,extra={})=>fetch(api+route,{method,headers:{Cookie:cookie,Origin:origin,'Content-Type':'application/json',...extra},...(body!==undefined?{body:JSON.stringify(body)}:{})});
  workerTask=worker();await new Promise(r=>setTimeout(r,100));
  let r=await req('/interactions/jp1/comments',alice,'POST',{text:'@Copilot 仕様は？',copilotAnswerVisibility:'public'});assert.equal(r.status,201);let detail=await r.json();const id=detail.createdCommentId;
  assert.equal(detail.commentItems[0].copilotAnswer.status,'waiting');
  r=await req('/copilot/jobs',alice,'POST',{itemId:'jp1',commentId:id});assert.equal(r.status,200);const j=(await r.json()).job;assert.equal(j.publicCommentAnswer.status,'pending');
  // No browser polls the job; server polling must persist it for a different reader.
  for(let n=0;n<100;n++){r=await req('/interactions/jp1',bob);detail=await r.json();if(detail.commentItems[0].copilotAnswer.status==='published')break;await new Promise(r=>setTimeout(r,300));}
  assert.equal(detail.commentItems[0].copilotAnswer.answer,jobs.get(j.id).answer);assert.equal(detail.comments,1);assert.equal(submits,1);
  assert.deepEqual(Object.keys(detail.commentItems[0].copilotAnswer).sort(),['answer','completedAt','status']);
  r=await req('/copilot/jobs/'+j.id+'/publish',bob,'POST',{});assert.equal(r.status,404);
  r=await req('/copilot/jobs/'+j.id+'/publish',alice,'POST',{answer:'forged'});assert.equal(r.status,400);
  r=await req('/copilot/jobs/'+j.id+'/publish',alice,'POST',{}, {Origin:'https://evil.test'});assert.equal(r.status,403);
  r=await req('/interactions/jp1/comments',alice,'POST',{text:'一般コメント',copilotAnswerVisibility:'public'});assert.equal(r.status,400);
  r=await req('/interactions/jp1/comments',alice,'POST',{text:'@Copilot 過去の質問'});const legacy=(await r.json()).createdCommentId;
  r=await req('/copilot/jobs',alice,'POST',{itemId:'jp1',commentId:legacy});const old=(await r.json()).job;
  await req('/copilot/jobs/'+old.id,alice);
  detail=await(await req('/interactions/jp1',bob)).json();assert.equal(detail.commentItems.find(c=>c.id===legacy).copilotAnswer,null);
  r=await req('/copilot/jobs/'+old.id+'/publish',alice,'POST',{});assert.equal(r.status,200);assert.equal((await r.json()).job.publicCommentAnswer.status,'published');
  await req('/copilot/jobs/'+old.id+'/publish',alice,'POST',{});assert.equal(submits,2);
  await req('/interactions/jp1/comments/'+id,alice,'DELETE');detail=await(await req('/interactions/jp1',bob)).json();assert.equal(detail.comments,1);assert.equal(detail.commentItems.some(c=>c.id===id),false);
  console.log('PASS '+edition+': public persistence without browser, private legacy, owner/CSRF/body checks, separate counts, explicit sharing and parent deletion');
 }finally{running=false;controller.abort();if(workerTask)await workerTask;child.kill();}
}
(async()=>{await verify('interior');await verify('exterior');})().catch(e=>{console.error(e);process.exitCode=1;});
