'use strict';
// Sessions stay under the signed-in workstation user's DPAPI. No auth input logs.
const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),https=require('node:https'),crypto=require('node:crypto');
const {createRequire}=require('node:module');
const runtime=path.join(process.env.LOCALAPPDATA,'DailyNewsRuntime/copilot-personal');
const settings=JSON.parse(fs.readFileSync(path.join(runtime,'worker.json'),'utf8'));
const {createService}=require(path.join(settings.repo,'deployment/windows-server/copilot-service.js'));
const engine=path.join(process.env.LOCALAPPDATA,'DailyNewsRuntime/exabase/engine/playwright_engine.js');
if(crypto.createHash('sha256').update(fs.readFileSync(engine)).digest('hex')!=='481517dd4230ab85afd490e5b3db491b0f599cd46f4e1e550aacaf8571353d76')throw Error('ENGINE_CHANGED');
const {chromium}=createRequire(engine)('playwright-core');let requestContext=null;
const services=Object.fromEntries(['interior','exterior'].map(edition=>[edition,createService({root:runtime,edition,
  sharedBrowserLock:path.join(runtime,'../copilot/worker.lock'),
  article:id=>requestContext?.article?.id===id?requestContext.article:null,
  comment:(id,c)=>requestContext?.comment?.itemId===id&&requestContext.comment.id===c?{comment_text:requestContext.comment.text}:null,
  launchOverride:async(state)=>{
    const browser=await chromium.launch({executablePath:path.join(process.env['ProgramFiles(x86)'],'Microsoft/Edge/Application/msedge.exe'),headless:true});
    try {const context=await browser.newContext({storageState:state,viewport:{width:1000,height:760},locale:'ja-JP',acceptDownloads:false}),page=await context.newPage();page.setDefaultTimeout(10000);return {browser,context,page};}
    catch(e){await browser.close();throw e;}
  }
})]));
const allowed=new Set(['accountStatus','begin','frame','action','disconnect','cancel','current','getJob','submit']);
async function execute(data){
 if(!allowed.has(data.operation)||!services[data.edition]||!Array.isArray(data.args)||!data.user||!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(data.user.email)||data.user.email.length>254)throw Object.assign(new Error(),{safeCode:'INVALID_REQUEST'});
 requestContext=data.context||null;const pending=services[data.edition][data.operation](data.user,...data.args);requestContext=null;return await pending;
}
const server=http.createServer(async(req,res)=>{
 const send=(status,value)=>{res.writeHead(status,{'Content-Type':'application/json','Cache-Control':'no-store'});res.end(JSON.stringify(value));};
 try {
  const token=String(req.headers.authorization||'').replace(/^Bearer /,'');
  if(req.method!=='POST'||req.url!=='/rpc'||token.length!==settings.token.length||!crypto.timingSafeEqual(Buffer.from(token),Buffer.from(settings.token)))return send(403,{code:'DENIED'});
  let body='';for await(const chunk of req){body+=chunk;if(Buffer.byteLength(body)>32000)throw Error('size');}
  const data=JSON.parse(body);body='';
  if(data.operation==='shutdown'){send(200,{ok:true});setTimeout(stop,50);return;}
  send(200,{result:await execute(data)});
 }catch(e){requestContext=null;send(409,{code:e.safeCode||'CONNECTION_FAILED'});}
});
let closing=false;
const connectionStatus={};
function recordConnection(edition,status,code=''){
 const previous=connectionStatus[edition];if(previous?.status===status&&previous.code===code&&Date.now()-Date.parse(previous.checkedAt)<120000)return;
 connectionStatus[edition]={status,code,checkedAt:new Date().toISOString()};fs.writeFileSync(path.join(runtime,'connection-status.json'),JSON.stringify(connectionStatus));
}
const ca=new crypto.X509Certificate(fs.readFileSync(path.join(settings.repo,'setup/IEWEB01-DailyNews.cer'))).toString();
const agent=new https.Agent({ca,keepAlive:true});
function exchange(edition,route,body){return new Promise((resolve,reject)=>{
 const encoded=JSON.stringify(body),req=https.request({host:'IEWEB01',port:443,path:(edition==='exterior'?'/exterior':'')+'/api/copilot-worker/'+route,method:'POST',agent,headers:{Authorization:'Bearer '+settings.token,'Content-Type':'application/json','Content-Length':Buffer.byteLength(encoded)}},res=>{
  let result='';res.on('data',b=>{result+=b;if(result.length>32000)req.destroy();});res.on('end',()=>{try{if(res.statusCode!==200)throw Error('HTTP_'+res.statusCode);resolve(JSON.parse(result));}catch(e){reject(e);}});
 });req.on('error',reject);req.setTimeout(30000,()=>req.destroy());req.end(encoded);
});}
async function loop(edition){while(!closing){try{
 const {job}=await exchange(edition,'poll',{});recordConnection(edition,'connected');if(!job)continue;
 let payload;try{payload={id:job.id,result:await execute(job)};}catch(e){payload={id:job.id,code:e.safeCode||'CONNECTION_FAILED'};}
 // Retry delivery of a result, never re-execute a browser action or question.
 for(let n=0;n<3&&!closing;n++){try{await exchange(edition,'result',payload);break;}catch{await new Promise(r=>setTimeout(r,1500));}}
 }catch(e){recordConnection(edition,'unavailable',String(e.code||e.message).slice(0,80));if(!closing)await new Promise(r=>setTimeout(r,15000));}}
}
server.listen(19085,'127.0.0.1',()=>{fs.writeFileSync(path.join(runtime,'worker.pid'),String(process.pid));void loop('interior');void loop('exterior');});
async function stop(){closing=true;agent.destroy();await Promise.allSettled(Object.values(services).map(s=>s.close()));server.close(()=>process.exit(0));setTimeout(()=>process.exit(0),2000).unref();}
process.on('SIGINT',stop);process.on('SIGTERM',stop);server.on('error',()=>process.exit(1));
