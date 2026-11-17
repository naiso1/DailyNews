'use strict';
// In-memory HTTPS job handoff. Microsoft sign-in input is never persisted here.
const fs=require('node:fs'),crypto=require('node:crypto');
function createClient({configFile,edition,article,comment,question}) {
  const pending=new Map();let wake=null,lastPoll=0,closed=false;
  function authorized(request){
    try{const config=JSON.parse(fs.readFileSync(configFile,'utf8')),token=String(request.headers.authorization||'').replace(/^Bearer /,'');return /^[a-f0-9]{64}$/.test(config.token)&&token.length===64&&crypto.timingSafeEqual(Buffer.from(token),Buffer.from(config.token));}catch{return false;}
  }
  async function invoke(operation,user,...args) {
    if(closed||Date.now()-lastPoll>120000)throw Object.assign(new Error(),{safeCode:'WORKER_OFFLINE'});
    if(pending.size>=32)throw Object.assign(new Error(),{safeCode:'BUSY'});
    return new Promise((resolve,reject)=>{
      let context;
      if(operation==='submitQuestion')context={question:question(args[0])};
      if(['submit','current'].includes(operation)){
        const [itemId,commentId]=args;
        if(typeof itemId!=='string'||!/^(jp|us|eu|cn|in|paper)\d+$/.test(itemId)||!Number.isSafeInteger(commentId)||commentId<1){reject(Object.assign(new Error(),{safeCode:'INVALID_REQUEST'}));return;}
        const a=article(itemId),c=comment(itemId,commentId);if(!a||!c){reject(Object.assign(new Error(),{safeCode:'NOT_FOUND'}));return;}
        context={article:{id:a.id,title:a.title,desc:a.desc,url:a.url},comment:{id:commentId,itemId,text:c.comment_text}};
      }
      const id=crypto.randomUUID(),timer=setTimeout(()=>{pending.delete(id);reject(Object.assign(new Error(),{safeCode:'WORKER_OFFLINE'}));},80000);
      pending.set(id,{data:{id,operation,edition,user:{email:user.email},args,context},resolve,reject,timer,delivered:false});wake?.();
    });
  }
  async function poll(){
    lastPoll=Date.now();let next=[...pending.values()].find(p=>!p.delivered);
    if(!next&&!closed){await new Promise(resolve=>{let timer;const done=()=>{clearTimeout(timer);if(wake===done)wake=null;resolve();};wake=done;timer=setTimeout(done,20000);});next=[...pending.values()].find(p=>!p.delivered);}
    lastPoll=Date.now();if(!next)return null;next.delivered=true;const data=next.data;next.data={id:data.id};return data;
  }
  function complete(data){const p=pending.get(data.id);if(!p)return;clearTimeout(p.timer);pending.delete(data.id);data.code?p.reject(Object.assign(new Error(),{safeCode:String(data.code).slice(0,80)})):p.resolve(data.result);}
  const client={authorized,poll,complete,close:async()=>{closed=true;wake?.();for(const p of pending.values()){clearTimeout(p.timer);p.reject(Object.assign(new Error(),{safeCode:'WORKER_OFFLINE'}));}pending.clear();}};
  for(const operation of ['accountStatus','begin','frame','action','disconnect','cancel','current','getJob','submit','submitQuestion'])client[operation]=(user,...args)=>invoke(operation,user,...args);
  return client;
}
module.exports={createClient};
