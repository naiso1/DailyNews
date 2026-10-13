"use strict";
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawn}=require('node:child_process'),{once}=require('node:events'),{DatabaseSync}=require('node:sqlite');
async function test(edition){
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'dailynews-images-'));
 const child=spawn(process.execPath,[path.join(__dirname,'../deployment/windows-server/server.js')],{env:{...process.env,DAILYNEWS_ROOT:root,DAILYNEWS_EDITION:edition,DAILYNEWS_HOST:'127.0.0.1',DAILYNEWS_PORT:'0',DAILYNEWS_ALLOWED_CLIENTS:'127.0.0.1,::1',DAILYNEWS_ADMIN_EMAILS:'admin@example.com',DAILYNEWS_IDENTITY_DB:'',DAILYNEWS_EXTERIOR_DB:''},stdio:['ignore','pipe','pipe']});
 let errors='';child.stderr.on('data',x=>errors+=x);
 try{
  const base=await new Promise((resolve,reject)=>{const timeout=setTimeout(()=>reject(Error(errors)),10000);child.stdout.on('data',x=>{const m=String(x).match(/listening on (http:\/\/\S+)/);if(m){clearTimeout(timeout);resolve(m[1]);}});child.on('exit',()=>{clearTimeout(timeout);reject(Error(errors));});});
  let cookie='';const prefix=edition==='exterior'?'/exterior':'';
  async function request(url,method='GET',body,status=200){const r=await fetch(base+prefix+'/api'+url,{method,headers:{Origin:base,Cookie:cookie,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});const text=await r.text();assert.equal(r.status,status,text);if(r.headers.get('set-cookie'))cookie=r.headers.get('set-cookie').split(';')[0];return JSON.parse(text);}
  await request('/admin/weekly-reports','GET',null,401);
  await request('/auth/register','POST',{email:'admin@example.com',displayName:'Admin',password:'test-password-123'},201);
  const urls=['https://example.com/1.jpg','https://example.com/2.jpg'];
  let r=await request('/admin/items/jp1/image','PUT',{imageUrls:urls});assert.deepEqual(r.imageUrlsOverride,urls);assert.equal(r.imageUrlOverride,urls[0]);
  r=await request('/admin/items/jp1/image','PUT',{imageUrls:[urls[1],urls[0],urls[1]]});assert.deepEqual(r.imageUrlsOverride,[urls[1],urls[0]]);
  for(const imageUrls of [[],['javascript:alert(1)'],Array(6).fill(urls[0]),['https://user:pass@example.com/a'],null]) await request('/admin/items/jp1/image','PUT',{imageUrls},400);
  r=await request('/admin/items/jp1/image','PUT',{imageUrl:urls[0]});assert.deepEqual(r.imageUrlsOverride,[urls[0]]);
  const db=new DatabaseSync(path.join(root,'data/dailynews.sqlite'));
  db.prepare('UPDATE item_image_overrides SET image_urls=NULL').run();
  r=await request('/interactions/jp1?clientId=test-browser-123456');assert.deepEqual(r.imageUrlsOverride,[urls[0]]);
  await request('/interactions/jp1/read','POST',{clientId:'test-browser-123456'});
  await request('/interactions/jp1/read','POST',{clientId:'test-browser-999999'});
  assert.equal(db.prepare('SELECT COUNT(*) n FROM user_article_reads').get().n,1,'Same user/article/day dedupes across browsers');
  r=await request('/admin/items/jp1/image','DELETE');assert.deepEqual(r.imageUrlsOverride,[]);
  fs.writeFileSync(path.join(root,'data/weekly-reports.json'),JSON.stringify({reports:[{week:'2026-10-05'}]}));
  assert.equal((await request('/admin/weekly-reports')).reports[0].week,'2026-10-05');
  await request('/auth/logout','POST',{});
  await request('/auth/register','POST',{email:'reader@example.com',displayName:'Reader',password:'test-password-123'},201);
  await request('/admin/items/jp1/image','PUT',{imageUrls:urls},403);
  await request('/admin/weekly-reports','GET',null,403);
  await request('/auth/logout','POST',{});
  await request('/interactions/jp1/read','POST',{clientId:'test-browser-000000'});
  assert.equal(db.prepare('SELECT COUNT(*) n FROM user_article_reads').get().n,1,'Guests are not assigned to authenticated users');
  db.close();
 }finally{if(child.exitCode===null){const stopped=once(child,'exit');child.kill();await stopped;}fs.rmSync(root,{recursive:true,force:true});}
}
(async()=>{await test('interior');await test('exterior');console.log('Images, legacy compatibility, admin authorization and user reads: PASS');})().catch(error=>{console.error(error);process.exitCode=1;});
