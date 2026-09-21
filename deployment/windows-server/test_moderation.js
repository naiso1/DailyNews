"use strict";
// Isolated temporary databases and localhost servers only; no production access.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawn } = require("node:child_process");
const { once } = require("node:events");
const { DatabaseSync } = require("node:sqlite");
const vm = require("node:vm");

// Real legacy wording only: classify the surviving snapshot, never invent events.
const source = fs.readFileSync(path.join(__dirname,"server.js"),"utf8");
const classifierStart = source.indexOf("function classifyLegacyRemoval(");
const classifierEnd = source.indexOf("\n}",classifierStart)+2;
const classifierContext = vm.createContext({});
vm.runInContext(source.slice(classifierStart,classifierEnd),classifierContext);
for (const reason of ["内装と関係ない","バイクの記事",
  "シートのみのニュースで豊田合成の商圏でなく、その他の快適性につながる参考にもならないため。",
  "シートのみの記事であり、豊田合成として参考にならない。","バイクは商権外",
  "自動車内装と関係ない","自動車内装に全く関係ない"]) {
  assert.equal(classifierContext.classifyLegacyRemoval(reason),"out_of_scope",reason);
}
assert.equal(classifierContext.classifyLegacyRemoval("もう一度確認したい"),"other");

async function fixture(edition, legacy = false) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "dailynews-moderation-"));
  const app = path.join(root,"app"); fs.mkdirSync(app);
  fs.mkdirSync(path.join(root,"data"));
  fs.mkdirSync(path.join(root,"releases","abcdef1"),{recursive:true});
  fs.writeFileSync(path.join(root,"active-release.txt"),"abcdef1");
  fs.copyFileSync(path.join(__dirname,"server.js"),path.join(app,"server.js"));
  const dbPath = path.join(root,"data","dailynews.sqlite");
  if (legacy) {
    const db = new DatabaseSync(dbPath);
    db.exec(`CREATE TABLE hidden_items(item_id TEXT PRIMARY KEY,reason TEXT NOT NULL,created_by INTEGER,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
      INSERT INTO hidden_items VALUES('jpold','同じ記事が重複',NULL,'2026-09-01 01:00:00','2026-09-02 02:00:00');
      INSERT INTO hidden_items VALUES('123','画像が違う',NULL,'2026-09-03 01:00:00','2026-09-03 01:00:00');`);
    db.close();
  }
  const port = 21000 + Math.floor(Math.random()*20000);
  const base = `http://127.0.0.1:${port}${edition === "exterior" ? "/exterior" : ""}`;
  let child; let stderr="";
  async function start() {
    child=spawn(process.execPath,[path.join(app,"server.js")],{cwd:app,env:{...process.env,
      DAILYNEWS_HOST:"127.0.0.1",DAILYNEWS_PORT:String(port),DAILYNEWS_EDITION:edition,
      DAILYNEWS_ADMIN_EMAILS:"admin@example.com",DAILYNEWS_IDENTITY_DB:"",DAILYNEWS_EXTERIOR_DB:""},stdio:["ignore","pipe","pipe"]});
    child.stderr.on("data",v=>{stderr+=v;});
    for(let i=0;i<80;i++) { try { if((await fetch(`${base}/api/status`)).ok)return; }catch{} await new Promise(r=>setTimeout(r,50)); }
    throw new Error(stderr);
  }
  async function stop() { if(child && child.exitCode===null) { const ended=once(child,"exit");child.kill();await ended; } }
  async function req(url,{cookie="",status=200,...options}={}) {
    const response=await fetch(`${base}${url}`,{...options,headers:{Origin:new URL(base).origin,"Content-Type":"application/json",Cookie:cookie},body:options.body?JSON.stringify(options.body):undefined});
    const data=await response.json();assert.equal(response.status,status,`${JSON.stringify(data)}\n${stderr}`);
    return {data,cookie:response.headers.get("set-cookie")?.split(";")[0]};
  }
  await start();
  return {req,dbPath,restart:async()=>{await stop();await start();},close:async()=>{await stop();fs.rmSync(root,{recursive:true,force:true});}};
}

async function main() {
  const f=await fixture("interior",true);
  try {
    const admin=(await f.req("/api/auth/register",{status:201,method:"POST",body:{email:"admin@example.com",displayName:"Admin",password:"test-password-123"}})).cookie;
    const user=(await f.req("/api/auth/register",{status:201,method:"POST",body:{email:"user@example.com",displayName:"User",password:"test-password-123"}})).cookie;
    let moderation=(await f.req("/api/admin/moderation",{cookie:admin})).data;
    assert.equal(moderation.history.total,2);
    assert.deepEqual(moderation.history.items.map(v=>v.action),["legacy_snapshot","legacy_snapshot"]);
    const old=moderation.history.items.find(v=>v.itemId==="jpold");
    assert.equal(old.eventAt,"2026-09-02 02:00:00");assert.equal(old.legacyCreatedAt,"2026-09-01 01:00:00");assert.equal(old.reasonCode,"duplicate");
    await f.restart();assert.equal((await f.req("/api/admin/moderation",{cookie:admin})).data.history.total,2);
    await f.req("/api/admin/moderation",{cookie:user,status:403});
    const hide={reasonCode:"out_of_scope",reason:"対象外の記事です",itemKind:"news",edition:"interior",sourceUrl:"https://example.com/story?id=7"};
    await f.req("/api/interactions/jp1/hidden",{cookie:user,method:"PUT",body:hide});
    await f.req("/api/interactions/jp1/hidden",{cookie:user,method:"PUT",body:hide});
    await f.req("/api/interactions/jp1/hidden",{cookie:user,method:"PUT",body:{...hide,reasonCode:"duplicate",reason:"他の記事と重複"}});
    await f.req("/api/interactions/jp2/hidden",{cookie:user,method:"PUT",status:400,body:{...hide,sourceUrl:"https://user:password@example.com/story"}});
    await f.req("/api/interactions/jp2/hidden",{cookie:user,method:"PUT",status:400,body:{...hide,edition:"exterior"}});
    await f.req("/api/admin/hidden-items/jp1",{cookie:user,method:"DELETE",status:403});
    await f.req("/api/admin/hidden-items/jp1",{cookie:admin,method:"DELETE"});
    moderation=(await f.req("/api/admin/moderation?pageSize=2&historyPage=1",{cookie:admin})).data;
    assert.equal(moderation.history.total,5);assert.equal(moderation.history.items.length,2);assert.equal(moderation.summary.hiddenCount,2);
    assert.deepEqual(moderation.history.items.map(v=>v.action),["restore","reason_changed"]);
    assert.equal(moderation.history.items[0].sourceUrl,hide.sourceUrl);
    assert.equal(moderation.weekly.reduce((n,v)=>n+v.hide,0),1);
    const feedback=(await f.req("/api/feedback",{cookie:user,method:"POST",status:201,body:{category:"article",message:"要約をご確認ください",itemId:"jp1",itemKind:"news",edition:"interior"}})).data;
    await f.req(`/api/admin/feedback/${feedback.id}`,{cookie:user,method:"PUT",status:403,body:{status:"resolved",adminNote:"不正"}});
    await f.req(`/api/admin/feedback/${feedback.id}`,{cookie:admin,method:"PUT",body:{status:"in_review",adminNote:"原文と照合中です"}});
    let own=(await f.req("/api/me/activity",{cookie:user})).data.feedback[0];
    assert.equal(own.status,"in_review");assert.equal(own.adminNote,"原文と照合中です");assert.equal(own.edition,"interior");assert.equal(own.itemKind,"news");
    assert.equal((await f.req("/api/admin/feedback?status=new",{cookie:admin})).data.total,0);
    assert.equal((await f.req("/api/admin/feedback?status=in_review&pageSize=999",{cookie:admin})).data.pageSize,50);
    await f.req(`/api/admin/feedback/${feedback.id}`,{cookie:admin,method:"PUT",status:400,body:{status:"read"}});
    let policies=(await f.req("/api/admin/selection-policies",{cookie:admin})).data;
    assert.equal(policies.policies.length,5);assert.ok(policies.policies.every(v=>v.enabled&&v.reviewStatus==="approved"&&v.source==="initial_user_request"));
    await f.req("/api/admin/selection-policies/exclude_off_topic",{cookie:user,method:"PUT",status:403,body:{enabled:false,reviewStatus:"pending"}});
    await f.req("/api/admin/selection-policies/exclude_off_topic",{cookie:admin,method:"PUT",status:400,body:{enabled:true,reviewStatus:"pending"}});
    await f.req("/api/admin/selection-policies/exclude_off_topic",{cookie:admin,method:"PUT",body:{enabled:false,reviewStatus:"pending",adminNote:"条件を再確認"}});
    const db=new DatabaseSync(f.dbPath,{readOnly:true});
    assert.equal(db.prepare("SELECT COUNT(*) AS n FROM feedback_events").get().n,1);
    assert.equal(db.prepare("SELECT COUNT(*) AS n FROM selection_policy_events WHERE actor_user_id IS NULL").get().n,5);
    assert.equal(db.prepare("SELECT reason FROM moderation_events WHERE action='hide'").get().reason,hide.reason);db.close();
  } finally {await f.close();}
  const exterior=await fixture("exterior");
  try {
    const admin=(await exterior.req("/api/auth/register",{status:201,method:"POST",body:{email:"admin@example.com",displayName:"Admin",password:"test-password-123"}})).cookie;
    const policies=(await exterior.req("/api/admin/selection-policies",{cookie:admin})).data;
    assert.equal(policies.policies.length,2);assert.ok(policies.policies.every(v=>!v.enabled&&v.reviewStatus==="pending"));
    await exterior.req("/api/admin/selection-policies/interior_lighting_only",{cookie:admin,method:"PUT",status:400,body:{enabled:true,reviewStatus:"approved"}});
  } finally {await exterior.close();}
  console.log("Feedback / moderation migration, history, permissions, paging and edition policy tests passed.");
}
main().catch(error=>{console.error(error);process.exitCode=1;});
