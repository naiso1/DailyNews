"use strict";
(() => {
  const base=window.DAILYNEWS_CONFIG?.apiBase || '/api',states=new Map();let userKey='',scanPending=false,initialized=false;
  const messages={ACCOUNT_NOT_CONNECTED:'本人のCopilotを接続してください。',AUTH_REQUIRED:'Microsoftへの再接続が必要です。',ACCOUNT_MISMATCH:'DailyNewsと異なるMicrosoftアカウントです。ご本人の会社アカウントで接続してください。',BUSY:'別の接続・質問を処理しています。少し待ってから操作してください。',https_required:'安全な接続画面をHTTPSで開いてください。',RESULT_UNCONFIRMED:'送信済みですが回答を確認できませんでした。重複送信を防ぐため停止しています。',INTERRUPTED:'処理が中断されました。送信済みの場合は自動再送しません。',CONNECTION_FAILED:'Copilotへの接続を確認できませんでした。',ACCOUNT_CHANGED:'接続が変更されました。接続状態を確認してください。'};
  const who=()=>window.dailyNewsAccount?.user;
  messages.WORKER_OFFLINE='Copilot連携用のPCに接続できません。PCの起動・サインイン後にお試しください。';
  const errorText=e=>messages[e?.code]||'接続を確認して、もう一度操作してください。';
  async function api(route,method='GET',body) {
    const response=await fetch(base+'/copilot'+route,{method,credentials:'same-origin',cache:'no-store',headers:{'Content-Type':'application/json'},...(body!==undefined?{body:JSON.stringify(body)}:{})});
    const data=await response.json();if(!response.ok)throw Object.assign(new Error(data.error?.message||data.message||'接続エラー'),{code:data.error?.code||data.error||data.code});return data;
  }
  function element(tag,text,className) {const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(className)el.className=className;return el;}
  function render(state) {
    for(const box of document.querySelectorAll(`[data-copilot-key="${state.key}"]`)){
      const button=box.querySelector('.copilot-question'),reply=box.querySelector('.copilot-reply');reply.replaceChildren();
      const j=state.job,busy=state.loading||j&&!['done','error','needs_review'].includes(j.status);button.disabled=!!busy;
      button.textContent=busy?'Copilotが回答中…':j?.status==='done'?'Copilotの回答':'Copilotへ質問';
      reply.hidden=!(state.error||j);
      if(reply.hidden)continue;
      reply.append(element('strong','Copilot · 自分だけに表示'));
      reply.append(element('p',state.error||(j.status==='done'?j.answer:j.status==='needs_review'?'送信済みです。結果を確認できないため自動再送を停止しました。':j.status==='error'?errorText({code:j.code}):j.status==='queued'?'順番を待っています…':'本人のCopilotで回答を取得しています…')));
      if(j?.conversationUrl){const link=element('a','Copilotで会話を開く');link.href=j.conversationUrl;link.target='_blank';link.rel='noopener noreferrer';reply.append(link);}
      if(j?.status==='done')reply.append(element('small','AIの回答です。記事で確認できる事実と仮説を分けてご確認ください。'));
    }
  }
  async function poll(state,key) {
    if(state.polling)return;state.polling=true;
    try {while(userKey===key&&state.job&&!['done','error','needs_review'].includes(state.job.status)){
      await new Promise(resolve=>setTimeout(resolve,2200));if(userKey!==key)break;
      const result=await api('/jobs/'+state.job.id);if(userKey!==key)break;state.job=result.job;render(state);
    }}catch(e){if(userKey===key){state.error=errorText(e);render(state);}}finally{state.polling=false;}
  }
  function dialog(title) {
    const d=element('dialog',undefined,'copilot-dialog'),header=element('header'),h=element('h2',title),close=element('button','閉じる');close.type='button';close.onclick=()=>d.close();header.append(h,close);d.append(header);document.body.append(d);d.showModal();d.addEventListener('close',()=>d.remove(),{once:true});return d;
  }
  async function settings() {
    const d=dialog('本人のCopilotを接続'),p=element('p','接続状態を確認しています…');d.append(p);
    try {const a=await api('/account');p.textContent=a.connected?`${a.email} のCopilotに接続済みです。回答はこのアカウントだけに表示します。`:'初回は本人のMicrosoftサインインが必要です。接続画面のMicrosoft表示を操作します。パスワードは保存せず、本人確認済みのセッションだけを暗号化して保存します。';
      const controls=element('div',undefined,'copilot-connect-tools');d.append(controls);
      if(a.connected){const off=element('button','Copilotの接続を解除');off.onclick=async()=>{off.disabled=true;await api('/account','DELETE');d.close();};controls.append(off);}
      const connect=element('button',a.connected?'接続し直す':'Microsoftに接続');controls.append(connect);
      const secure=new URL(location.href);secure.protocol='https:';secure.port='';secure.hash='copilot-connect';
      connect.onclick=()=>{d.close();if(location.protocol==='https:')void connectScreen();else window.open(secure.href,'dailynews-copilot-connect','noopener');};
      if(location.protocol!=='https:'){
        const help=element('div',undefined,'copilot-certificate-help');
        help.append(element('p','「接続がプライベートではありません」と表示される場合は、Microsoftの認証より前の、PC側の証明書設定で止まっています。IEWEB01の自己署名証明書を確認し、このPCの現在のWindowsユーザーに登録する初回操作が必要です。'));
        const guide=element('a','証明書の確認・登録手順を開く');guide.href='/setup/copilot-connection.html';guide.target='_blank';guide.rel='noopener noreferrer';help.append(guide);
        help.append(element('p','登録後に「Microsoftに接続」を開き直してください。証明書の警告を無視して進めず、手順に沿って内容を確認してください。'));
        d.append(help);
      }
    }catch(e){p.textContent=errorText(e);}
  }
  async function connectScreen() {
    if(!who())return;
    const d=dialog('Microsoftサインイン — 自分のCopilot'),status=element('p','接続画面を準備しています…','copilot-connect-status');d.append(status);
    d.append(element('p','下のMicrosoft画面をクリックし、そのままキーボードで入力できます。貼り付け・Tab・Enterも使えます。本人の会社アカウントでサインインしてください。接続は10分で終了します。'));
    const host=element('p','','copilot-auth-host'),img=element('img');img.alt='本人のMicrosoftサインイン画面';img.tabIndex=0;img.hidden=true;d.append(host,img);
    const tools=element('div',undefined,'copilot-connect-tools');d.append(tools);
    let id,alive=true,serial=Promise.resolve();const key=userKey;
    const action=data=>{serial=serial.then(()=>alive&&userKey===key?api('/connection/'+id+'/action','POST',data):null).catch(e=>{status.textContent=errorText(e);});};
    img.onclick=e=>{img.focus();const r=img.getBoundingClientRect();action({type:'click',x:(e.clientX-r.left)/r.width*1000,y:(e.clientY-r.top)/r.height*760});};
    img.onkeydown=e=>{
      if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='v')return;
      e.preventDefault();if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='a')action({type:'key',key:'Control+A'});
      else if(e.key.length===1&&!e.ctrlKey&&!e.metaKey)action({type:'text',text:e.key});
      else if(['Tab','Enter','Backspace','Delete','ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Escape'].includes(e.key))action({type:'key',key:e.key==='Tab'&&e.shiftKey?'Shift+Tab':e.key});
    };
    img.onpaste=e=>{e.preventDefault();action({type:'text',text:e.clipboardData.getData('text').slice(0,512)});};
    for(const label of ['Tab','Enter','Backspace']){const b=element('button',label);b.onclick=()=>action({type:'key',key:label});tools.append(b);}
    d.addEventListener('close',()=>{alive=false;if(id)void api('/connection/'+id,'DELETE').catch(()=>{});},{once:true});
    try {id=(await api('/connection','POST',{})).id;
      while(alive&&userKey===key){await serial;const f=await api('/connection/'+id+'/frame');if(!alive)break;
        if(f.status==='connected'){id=null;img.hidden=true;status.textContent='本人のCopilotに接続できました。元のニュースページで「Copilotへ質問」を押してください。';host.textContent='接続完了';break;}
        if(f.status!=='signing_in'){status.textContent=f.status==='expired'?'接続の待ち時間が終了しました。':errorText({code:f.code});break;}
        img.src='data:image/jpeg;base64,'+f.image;img.hidden=false;host.textContent='接続先: '+f.host;status.textContent='Microsoft画面でサインインしてください。';await new Promise(r=>setTimeout(r,1500));
      }
    }catch(e){status.textContent=errorText(e);}
  }
  async function ask(state) {
    if(!who()){window.dailyNewsAccount?.open?.();return;}
    if(state.job?.status==='done'){const box=document.querySelector(`[data-copilot-key="${state.key}"] .copilot-reply`);if(box)box.hidden=!box.hidden;return;}
    const key=userKey;state.loading=true;state.error='';render(state);
    try {const a=await api('/account');if(userKey!==key)return;if(!a.connected){await settings();return;}
      const r=await api('/jobs','POST',{itemId:state.itemId,commentId:state.commentId});if(userKey!==key)return;state.job=r.job;void poll(state,key);
    }catch(e){if(userKey===key)state.error=errorText(e);}finally{if(userKey===key){state.loading=false;render(state);}}
  }
  function scan() {
    scanPending=false;if(!who())return;
    for(const comment of document.querySelectorAll('.comment-item[data-comment-id]')){
      if(comment.querySelector('.copilot-controls'))continue;
      const card=comment.closest('.card[id^="card-"]'),itemId=card?.id.slice(5),commentId=Number(comment.dataset.commentId);
      if(!/^(jp|us|eu|cn|in)\d+$/.test(itemId||'')||!commentId)continue;
      const key=itemId+'-'+commentId;let state=states.get(key);const fresh=!state;
      if(!state){state={key,itemId,commentId,job:null};states.set(key,state);}
      const box=element('div',undefined,'copilot-controls');box.dataset.copilotKey=key;
      const button=element('button','Copilotへ質問','copilot-question');button.type='button';button.onclick=()=>void ask(state);
      const account=element('button','接続設定','copilot-settings');account.type='button';account.onclick=()=>void settings();
      const reply=element('div',undefined,'copilot-reply');reply.setAttribute('aria-live','polite');reply.hidden=true;box.append(button,account,reply);comment.append(box);render(state);
      if(fresh){const member=userKey;void api('/current?itemId='+itemId+'&commentId='+commentId).then(r=>{if(userKey!==member)return;state.job=r.job;render(state);void poll(state,member);}).catch(()=>{});}
    }
  }
  function changed(){userKey=who()?.email||'';states.clear();document.querySelectorAll('.copilot-controls').forEach(el=>el.remove());document.querySelectorAll('.copilot-dialog').forEach(el=>el.close());scan();}
  function ready(){if(initialized)return;initialized=true;changed();new MutationObserver(()=>{if(!scanPending){scanPending=true;requestAnimationFrame(scan);}}).observe(document.body,{childList:true,subtree:true});
    if(location.hash==='#copilot-connect'&&who()&&location.protocol==='https:'){history.replaceState(null,'',location.pathname+location.search);void connectScreen();}}
  window.addEventListener('dailynews:account-changed',changed);window.addEventListener('dailynews:account-ready',ready,{once:true});
  if(window.dailyNewsAccount?.ready)ready();
})();
