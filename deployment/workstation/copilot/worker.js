'use strict';
// Dedicated Edge contexts; never attach to the user's everyday browser.
const fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto');
const {spawn} = require('node:child_process');
const {createRequire} = require('node:module');
const RUNTIME = path.join(process.env.LOCALAPPDATA || '', 'DailyNewsRuntime', 'copilot');
const AUTH = path.join(RUNTIME, 'auth.bin');
const ENGINE = path.join(process.env.LOCALAPPDATA || '', 'DailyNewsRuntime/exabase/engine/playwright_engine.js');
const ENGINE_SHA = '481517dd4230ab85afd490e5b3db491b0f599cd46f4e1e550aacaf8571353d76';
const URL = 'https://copilot.cloud.microsoft/chat/';
const INPUT = '#m365-chat-editor-target-element';
const DOWNLOAD = 'button[aria-label="ダウンロード"]';
const fail = code => Object.assign(new Error(code), {safeCode:code});
const emit = v => process.stdout.write(JSON.stringify(v)+'\n');
const sleep = ms => new Promise(r=>setTimeout(r,ms));
function atomic(file, value) {
  fs.writeFileSync(file+'.tmp', JSON.stringify(value));fs.renameSync(file+'.tmp',file);
}
function validateRequest(r) {
  if (!/^[a-f0-9]{64}$/.test(r.key||'') || typeof r.prompt!=='string' || !r.prompt.trim()
      || r.prompt.length>12000 || !path.isAbsolute(r.outputDir||'')
      || (r.timeoutMs!==undefined && (!Number.isFinite(r.timeoutMs)||r.timeoutMs<30000||r.timeoutMs>600000))) throw fail('INVALID_REQUEST');
}
function runtime() {
  if(process.platform!=='win32'||!process.env.LOCALAPPDATA)throw fail('RUNTIME_MISSING');
  if(!fs.existsSync(ENGINE))throw fail('RUNTIME_MISSING');
  if(crypto.createHash('sha256').update(fs.readFileSync(ENGINE)).digest('hex')!==ENGINE_SHA)throw fail('ENGINE_CHANGED');
  const {chromium}=createRequire(ENGINE)('playwright-core');
  const edge=[process.env['ProgramFiles(x86)'],process.env.ProgramFiles,process.env.LOCALAPPDATA].filter(Boolean)
    .map(p=>path.join(p,'Microsoft/Edge/Application/msedge.exe')).find(p=>fs.existsSync(p));
  if(!edge)throw fail('EDGE_MISSING');
  fs.mkdirSync(RUNTIME,{recursive:true});
  return {chromium,edge};
}
function lock() {
  const file=path.join(RUNTIME,'worker.lock');
  try {const fd=fs.openSync(file,'wx');fs.writeFileSync(fd,String(process.pid));fs.closeSync(fd);}
  catch(e) {
    if(e.code!=='EEXIST')throw e;
    const owner=Number(fs.readFileSync(file,'utf8'));
    if(!Number.isSafeInteger(owner)||owner<=0)throw fail('BUSY');
    try {process.kill(owner,0);throw fail('BUSY');}catch(check){if(check.code!=='ESRCH')throw fail('BUSY');}
    fs.unlinkSync(file);return lock();
  }
  return ()=>{try{fs.unlinkSync(file);}catch{}};
}
function dpapi(buffer,protect) {
  const method=protect?'Protect':'Unprotect';
  const script=`Add-Type -AssemblyName System.Security; $b=[Convert]::FromBase64String([Console]::In.ReadToEnd().Trim()); $r=[Security.Cryptography.ProtectedData]::${method}($b,$null,[Security.Cryptography.DataProtectionScope]::CurrentUser); [Console]::Out.Write([Convert]::ToBase64String($r))`;
  return new Promise((resolve,reject)=>{
    const p=spawn('powershell.exe',['-NoProfile','-NonInteractive','-Command',script],{windowsHide:true,stdio:['pipe','pipe','pipe']});
    const chunks=[];let size=0;
    const timer=setTimeout(()=>{p.kill();reject(fail('AUTH_REQUIRED'));},30000);
    p.stdout.on('data',b=>{size+=b.length;if(size>12*1024*1024)p.kill();else chunks.push(b);});p.stderr.resume();
    p.on('error',()=>{clearTimeout(timer);reject(fail('AUTH_REQUIRED'));});
    p.on('close',code=>{clearTimeout(timer);code===0?resolve(Buffer.from(Buffer.concat(chunks).toString().trim(),'base64')):reject(fail('AUTH_REQUIRED'));});
    p.stdin.end(buffer.toString('base64'));
  });
}
async function loadSession(){
  try{return JSON.parse((await dpapi(fs.readFileSync(AUTH),false)).toString('utf8'));}catch{throw fail('AUTH_REQUIRED');}
}
async function saveSession(context){
  const encrypted=await dpapi(Buffer.from(JSON.stringify(await context.storageState({indexedDB:true}))),true);
  fs.writeFileSync(AUTH+'.tmp',encrypted);fs.renameSync(AUTH+'.tmp',AUTH);
}
async function authenticated(page){
  return /^https:\/\/(copilot|m365)\.cloud\.microsoft\//.test(page.url()) && await page.locator(INPUT).isVisible().catch(()=>false);
}
async function ready(page){
  const deadline=performance.now()+20000;
  while(performance.now()<deadline){if(await authenticated(page))return;await sleep(500);}
  throw fail('AUTH_REQUIRED');
}
async function generate(page, request){
  validateRequest(request);
  const dir=request.outputDir;fs.mkdirSync(dir,{recursive:true});
  const phase=path.join(dir,'phase.json');
  if(fs.existsSync(phase)){
    const previous=JSON.parse(fs.readFileSync(phase,'utf8'));
    if(['sending','submitted','done'].includes(previous.event))throw fail('NEEDS_REVIEW');
  }
  await sleep(1500);
  const download=page.locator(DOWNLOAD);
  if(await download.count())throw fail('NOT_A_FRESH_CONVERSATION');
  await page.locator(INPUT).fill(request.prompt,{timeout:10000});
  const send=page.locator('button[aria-label="送信"]');
  await send.waitFor({state:'visible',timeout:10000});
  const mark=event=>{const v={event,key:request.key};atomic(phase,v);emit(v);};
  mark('sending');const started=performance.now();
  await send.click({timeout:10000});mark('submitted');
  const deadline=performance.now()+(request.timeoutMs||180000);let stable=null,done=false;
  while(performance.now()<deadline){
    if(!await authenticated(page))throw fail('AUTH_REQUIRED');
    const stopping=await page.locator('button[aria-label="生成を停止する"]').isVisible().catch(()=>false);
    const available=await download.count()===1 && await download.isVisible();
    const large=await page.evaluate(()=>[...(document.querySelector('main,[role="main"]')||document.body).querySelectorAll('img')]
      .filter(i=>i.complete&&i.naturalWidth>=256&&i.naturalHeight>=256).length);
    if(available&&large&&!stopping){if(stable===null)stable=performance.now();if(performance.now()-stable>=2500){done=true;break;}}
    else stable=null;
    await sleep(1000);
  }
  if(!done)throw fail('GENERATION_TIMEOUT');
  const pending=page.waitForEvent('download',{timeout:30000});
  // Attach a rejection handler immediately even when clicking fails.
  pending.catch(()=>{});
  await download.click({timeout:10000});const item=await pending;
  const extension=path.extname(item.suggestedFilename()).toLowerCase();
  if(!['.png','.jpg','.jpeg','.webp'].includes(extension))throw fail('INVALID_IMAGE');
  const file=path.join(dir,'generated-reference'+extension);
  await item.saveAs(file+'.tmp');
  const bytes=fs.statSync(file+'.tmp').size;
  if(bytes<1000||bytes>25*1024*1024)throw fail('INVALID_IMAGE');
  fs.renameSync(file+'.tmp',file);
  const result={status:'DONE',key:request.key,provider:'copilot',imageModel:'',modelVisibility:'not_exposed',file,
    generationToSavedSeconds:+((performance.now()-started)/1000).toFixed(3)};
  atomic(path.join(dir,'result.json'),result);mark('done');emit(result);
}
async function readRequest(){
  const chunks=[];let size=0;for await(const b of process.stdin){size+=b.length;if(size>65536)throw fail('INVALID_REQUEST');chunks.push(b);}
  try{return JSON.parse(Buffer.concat(chunks).toString('utf8'));}catch{throw fail('INVALID_REQUEST');}
}
async function main(){
  const mode=process.argv[2];
  if(!['--generate','--check-session','--login'].includes(mode))throw fail('INVALID_REQUEST');
  const request=mode==='--generate'?await readRequest():null;if(request)validateRequest(request);
  const {chromium,edge}=runtime(),release=lock();let browser,context,page,timer,timedOut=false;
  try{
    let state;try{state=await loadSession();}catch(e){if(mode!=='--login')throw e;}
    browser=await chromium.launch({executablePath:edge,headless:mode!=='--login'});
    timer=setTimeout(()=>{timedOut=true;browser.close().catch(()=>{});},mode==='--login'?600000:(request?.timeoutMs||20000)+80000);
    context=await browser.newContext({...(state?{storageState:state}:{}),viewport:{width:1440,height:1000},acceptDownloads:true});
    page=await context.newPage();await page.goto(URL,{waitUntil:'domcontentloaded',timeout:60000});
    if(mode==='--login'){
      emit({status:'LOGIN_REQUIRED'});while(!await authenticated(page)){if(timedOut)throw fail('AUTH_REQUIRED');await sleep(500);}
    }else await ready(page);
    if(request)await generate(page,request);
    try{if(!timedOut&&await authenticated(page))await saveSession(context);}catch{emit({event:'warning',code:'SESSION_REFRESH_FAILED'});}
    if(!request)emit({status:'AUTHENTICATED'});
  }catch(e){if(timedOut)throw fail('GENERATION_TIMEOUT');throw e;}
  finally{clearTimeout(timer);if(browser)await browser.close().catch(()=>{});release();}
}
if(require.main===module)main().catch(e=>{emit({status:'ERROR',code:e.safeCode||'COPILOT_UNAVAILABLE'});process.exitCode=1;});
module.exports={validateRequest,generate};
