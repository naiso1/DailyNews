'use strict';
// Real isolated HTTP/SQLite routes; fake Microsoft worker. Never send a real prompt.
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const {spawn}=require('node:child_process');
const {createService}=require('./copilot-service');
async function verifyProviderIdentity(){
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'dailynews-copilot-identity-'));
 const alice={email:'alice@example.com'},bob={email:'bob@example.com'};
 const mock=async()=>{
  const loc=kind=>({waitFor:async()=>{},isVisible:async()=>kind==='input',click:async()=>{},innerText:async()=>alice.email});
  return {browser:{close:async()=>{}},context:{route:async()=>{},on:()=>{},storageState:async()=>({cookies:[],origins:[]})},page:{goto:async()=>{},url:()=> 'https://copilot.cloud.microsoft/chat/',setDefaultTimeout:()=>{},waitForTimeout:async()=>{},locator:()=>loc('input'),getByRole:(role)=>loc(role),keyboard:{press:async()=>{}}}};
 };
 const svc=createService({root,edition:'interior',article:()=>null,comment:()=>null,launchOverride:mock});
 try{
  const a=await svc.begin(alice);await assert.rejects(svc.frame(bob,a.id),{safeCode:'NOT_FOUND'});
  assert.equal((await svc.frame(alice,a.id)).status,'connected');
  const b=await svc.begin(bob);assert.equal((await svc.frame(bob,b.id)).code,'ACCOUNT_MISMATCH');assert.equal(svc.accountStatus(bob).connected,false);
  assert.equal(svc.accountStatus(alice).connected,true);await svc.disconnect(alice);assert.equal(svc.accountStatus(alice).connected,false);
 }finally{await svc.close();}
}
async function verifyEdition(edition){
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'dailynews-http-signin-')),app=path.join(root,'app'),release=path.join(root,'releases/abcdef2');
 fs.mkdirSync(app);fs.mkdirSync(release,{recursive:true});fs.mkdirSync(path.join(root,'data'));
 for(const n of ['server.js','shared-identity.js','copilot-client.js'])fs.copyFileSync(path.join(__dirname,n),path.join(app,n));
 fs.writeFileSync(path.join(root,'active-release.txt'),'abcdef2');fs.writeFileSync(path.join(release,'index.html'),'<title>test</title>');
 fs.writeFileSync(path.join(root,'data/copilot-worker.json'),JSON.stringify({token:'a'.repeat(64)}));
 fs.writeFileSync(path.join(root,'data/copilot-connection.json'),JSON.stringify({allowIntranetHttpSignIn:true}));
 const port=20100+Math.floor(Math.random()*1000),origin='http://127.0.0.1:'+port,base=origin+(edition==='exterior'?'/exterior':''),api=base+'/api';
 // Deliberately broad site allowlist proves the sign-in exception is independently bounded.
 const child=spawn(process.execPath,[path.join(app,'server.js')],{env:{...process.env,DAILYNEWS_ROOT:root,DAILYNEWS_HOST:'127.0.0.1',DAILYNEWS_PORT:String(port),DAILYNEWS_EDITION:edition,DAILYNEWS_ALLOWED_CLIENTS:'127.0.0.1,::1,0.0.0.0/0'},stdio:['ignore','ignore','pipe']});
 let serverErrors='';child.stderr.on('data',b=>serverErrors+=b);
 let polling=true,workerPromise;const workerController=new AbortController(),connections=new Map(),actions=[],workerHeaders={Authorization:'Bearer '+'a'.repeat(64),'Content-Type':'application/json','X-Forwarded-Proto':'https'};
 async function mockWorker(){while(polling){try{
  const response=await fetch(api+'/copilot-worker/poll',{method:'POST',headers:workerHeaders,body:'{}',signal:workerController.signal});const {job}=await response.json();if(!job)continue;
  let result,code;
  if(job.operation==='accountStatus')result={connected:false,email:job.user.email};
  else if(job.operation==='begin'){const id=crypto.randomUUID();connections.set(id,job.user.email);result={id,status:'signing_in'};}
  else if(['frame','action','cancel'].includes(job.operation)){
   if(connections.get(job.args[0])!==job.user.email)code='NOT_FOUND';
   else if(job.operation==='frame')result={status:'signing_in',host:'login.microsoftonline.com',width:1000,height:760,image:'mock-image'};
   else if(job.operation==='action'){actions.push(job.args[1]);result={ok:true};}
   else{connections.delete(job.args[0]);result={status:'cancelled'};}
  }else code='INVALID_REQUEST';
  await fetch(api+'/copilot-worker/result',{method:'POST',headers:workerHeaders,body:JSON.stringify(code?{id:job.id,code}:{id:job.id,result}),signal:workerController.signal});
 }catch(e){if(polling)throw e;}}}
 const headers=cookie=>({'Content-Type':'application/json',Origin:origin,...(cookie?{Cookie:cookie}:{})});
 try{
  let started=false;for(let n=0;n<80;n++){try{if((await fetch(base+'/health')).ok){started=true;break;}}catch{}await new Promise(r=>setTimeout(r,100));}assert.ok(started,serverErrors);
  assert.match(await (await fetch(base+'/dailynews_config.js')).text(),/"copilotIntranetHttpSignIn":true/);
  workerPromise=mockWorker();await new Promise(r=>setTimeout(r,100));
  let r=await fetch(api+'/copilot/connection',{method:'POST',headers:headers(),body:'{}'});assert.equal(r.status,401);
  async function register(email){const r=await fetch(api+'/auth/register',{method:'POST',headers:headers(),body:JSON.stringify({email,displayName:'Test',password:'local-fixture-only-123',clientId:crypto.randomUUID()})});assert.equal(r.status,201);return r.headers.get('set-cookie').split(';')[0];}
  const alice=await register('alice@example.com'),bob=await register('bob@example.com');
  r=await fetch(api+'/copilot/connection',{method:'POST',headers:{...headers(alice),Origin:'https://other.invalid'},body:'{}'});assert.equal(r.status,403);
  for(const addr of ['198.51.100.12','172.29.1.2, 198.51.100.12']){
   r=await fetch(api+'/copilot/connection',{method:'POST',headers:{...headers(alice),'X-Forwarded-For':addr},body:'{}'});assert.equal(r.status,426);
  }
  r=await fetch(api+'/copilot/connection',{method:'POST',headers:{...headers(alice),'X-Forwarded-For':'172.29.1.2'},body:'{}'});assert.equal(r.status,200);const id=(await r.json()).id;
  r=await fetch(api+'/copilot/connection/'+id+'/frame',{headers:headers(alice)});assert.equal(r.status,200);assert.equal((await r.json()).host,'login.microsoftonline.com');assert.equal(r.headers.get('cache-control'),'no-store');
  r=await fetch(api+'/copilot/connection/'+id+'/frame',{headers:headers(bob)});assert.equal(r.status,404);
  r=await fetch(api+'/copilot/connection/'+id+'/action',{method:'POST',headers:headers(bob),body:JSON.stringify({type:'key',key:'Tab'})});assert.equal(r.status,404);
  r=await fetch(api+'/copilot/connection/'+id+'/action',{method:'POST',headers:headers(alice),body:JSON.stringify({type:'text',text:'dummy-not-a-credential'})});assert.equal(r.status,200);assert.equal(actions.length,1);
  r=await fetch(api+'/copilot/connection/'+id,{method:'DELETE',headers:headers(bob)});assert.equal(r.status,404);
  r=await fetch(api+'/copilot/connection/'+id,{method:'DELETE',headers:headers(alice)});assert.equal(r.status,200);
  for(const route of ['poll','result']){
   r=await fetch(api+'/copilot-worker/'+route,{method:'POST',headers:{Authorization:workerHeaders.Authorization,'Content-Type':'application/json'},body:'{}'});assert.equal(r.status,403);
  }
  const log=fs.existsSync(path.join(root,'logs/server.log'))?fs.readFileSync(path.join(root,'logs/server.log'),'utf8'):'';assert.ok(!log.includes('dummy-not-a-credential'));
  console.log('PASS '+edition+': HTTP opt-in, intranet bounds, spoofed forwarding-chain rejection, login/CSRF/owner checks, no credential logging; worker HTTPS unchanged.');
 }finally{polling=false;workerController.abort();await workerPromise;child.kill();}
}
(async()=>{await verifyProviderIdentity();await verifyEdition('interior');await verifyEdition('exterior');})().catch(e=>{console.error(e);process.exitCode=1;});
