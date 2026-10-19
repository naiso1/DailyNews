"use strict";
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const http=require('node:http'),zlib=require('node:zlib');
const {spawn}=require('node:child_process'),{once}=require('node:events');
async function test(edition){
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'dailynews-static-'));
 const release=path.join(root,'releases','a'.repeat(40));fs.mkdirSync(release,{recursive:true});
 const original=Buffer.from('window.NEWS_DATA = '+JSON.stringify(Array(100).fill({title:'日本語ニュースと画像',url:'https://example.com/article'}))+';');
 fs.writeFileSync(path.join(release,'news_data.js'),original);
 fs.writeFileSync(path.join(release,'index.html'),'<h1>News</h1>');
 fs.writeFileSync(path.join(root,'active-release.txt'),'a'.repeat(40));
 const child=spawn(process.execPath,[path.join(__dirname,'../deployment/windows-server/server.js')],{env:{...process.env,DAILYNEWS_ROOT:root,DAILYNEWS_EDITION:edition,DAILYNEWS_HOST:'127.0.0.1',DAILYNEWS_PORT:'0',DAILYNEWS_ALLOWED_CLIENTS:'127.0.0.1,::1',DAILYNEWS_IDENTITY_DB:'',DAILYNEWS_EXTERIOR_DB:''},stdio:['ignore','pipe','pipe']});
 let errors='';child.stderr.on('data',x=>errors+=x);
 try{
  const base=await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error(errors)),10000);child.stdout.on('data',x=>{const m=String(x).match(/listening on (http:\/\/\S+)/);if(m){clearTimeout(timer);resolve(m[1]);}});child.on('exit',()=>{clearTimeout(timer);reject(Error(errors));});});
  const prefix=edition==='exterior'?'/exterior':'';
  const registration=await fetch(base+prefix+'/api/auth/register',{method:'POST',headers:{Origin:base,'Content-Type':'application/json'},body:JSON.stringify({email:'test@example.invalid',displayName:'Test',password:'test-only-password'})});
  assert.equal(registration.status,201);
  const cookie=registration.headers.get('set-cookie').split(';')[0];
  function request(headers={},method='GET',url='/news_data.js'){
   return new Promise((resolve,reject)=>{const r=http.request(base+prefix+url,{method,headers:{Cookie:cookie,...headers}},response=>{const chunks=[];response.on('data',c=>chunks.push(c));response.on('end',()=>resolve({status:response.statusCode,headers:response.headers,body:Buffer.concat(chunks)}));});r.on('error',reject);r.end();});
  }
  const compressed=await request({'Accept-Encoding':'gzip'});
  assert.equal(compressed.status,200);assert.equal(compressed.headers['content-encoding'],'gzip');
  assert.deepEqual(zlib.gunzipSync(compressed.body),original);
  assert.ok(compressed.body.length<original.length/2);
  assert.equal(compressed.headers.vary,'Accept-Encoding');assert.equal(compressed.headers['cache-control'],'private, no-cache');
  const etag=compressed.headers.etag;
  const repeated=await request({'Accept-Encoding':'gzip','If-None-Match':etag});
  assert.equal(repeated.status,304);assert.equal(repeated.body.length,0);
  const deniedGzip=await request({'Accept-Encoding':'gzip;q=0, *;q=1'});
  assert.equal(deniedGzip.headers['content-encoding'],undefined);assert.deepEqual(deniedGzip.body,original);
  const head=await request({'Accept-Encoding':'gzip'},'HEAD');
  assert.equal(head.body.length,0);assert.equal(head.headers['content-length'],compressed.headers['content-length']);
  const concurrent=await Promise.all(Array.from({length:6},()=>request({'Accept-Encoding':'gzip'})));
  concurrent.forEach(r=>assert.deepEqual(r.body,compressed.body));
  if(edition==='interior'){
   const unauthorized=await request({Cookie:'','If-None-Match':etag});assert.equal(unauthorized.status,401);
   for(const url of ['/%6eews_data.js','/NEWS_DATA.js','/page_images%5c..%5cnews_data.js']){
    assert.equal((await request({Cookie:'','If-None-Match':etag},'GET',url)).status,401);
   }
  }
  const api=await request({},'GET','/api/auth/me');assert.equal(api.headers['cache-control'],'no-store');assert.equal(api.headers.etag,undefined);
  const next=path.join(root,'releases','b'.repeat(40));fs.mkdirSync(next,{recursive:true});
  const updated=Buffer.from(original.toString().replace('日本語','更新後'));
  fs.writeFileSync(path.join(next,'news_data.js'),updated);fs.writeFileSync(path.join(root,'active-release.txt'),'b'.repeat(40));
  const changed=await request({'Accept-Encoding':'gzip','If-None-Match':etag});
  assert.equal(changed.status,200);assert.notEqual(changed.headers.etag,etag);assert.deepEqual(zlib.gunzipSync(changed.body),updated);
  console.log(edition+': gzip, 304, HEAD, q=0, concurrent reads, auth/API isolation, release freshness PASS');
 }finally{
  if(child.exitCode===null){const stopped=once(child,'exit');child.kill();await stopped;}
  const safeRoot=path.resolve(root),tempRoot=path.resolve(os.tmpdir())+path.sep;
  assert.ok(safeRoot.startsWith(tempRoot)&&path.basename(safeRoot).startsWith('dailynews-static-'));
  fs.rmSync(safeRoot,{recursive:true,force:true});
 }
}
(async()=>{await test('interior');await test('exterior');})().catch(e=>{console.error(e);process.exitCode=1;});
