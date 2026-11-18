"use strict";
(() => {
  const base=window.DAILYNEWS_CONFIG?.apiBase || '/api',states=new Map();let userKey='',scanPending=false,initialized=false;
  const messages={ACCOUNT_NOT_CONNECTED:'本人のCopilotを接続してください。',AUTH_REQUIRED:'Microsoftへの再接続が必要です。',ACCOUNT_MISMATCH:'DailyNewsと異なるMicrosoftアカウントです。ご本人の会社アカウントで接続してください。',BUSY:'別の接続・質問を処理しています。少し待ってから操作してください。',https_required:'安全な接続画面をHTTPSで開いてください。',RESULT_UNCONFIRMED:'送信済みですが回答を確認できませんでした。重複送信を防ぐため停止しています。',INTERRUPTED:'処理が中断されました。送信済みの場合は自動再送しません。',CONNECTION_FAILED:'Copilotへの接続を確認できませんでした。',ACCOUNT_CHANGED:'接続が変更されました。接続状態を確認してください。'};
  const who=()=>window.dailyNewsAccount?.user;
  const inlineConnection=()=>location.protocol==='https:' || window.DAILYNEWS_CONFIG?.copilotIntranetHttpSignIn===true;
  messages.WORKER_OFFLINE='Copilot連携用のPCに接続できません。PCの起動・サインイン後にお試しください。';
  messages.SEND_NOT_READY='Copilotの入力画面を準備できませんでした。質問は未送信です。時間をおいてお試しください。';
  messages.STALE_QUESTION='対象のニュースが更新されています。対象と質問を選び直して送信してください。';
  Object.assign(messages,{NO_NEWS:'対象のニュースがまだありません。',NO_RELEVANT_NEWS:'質問に合う記事が見つかりませんでした。言葉を変えてお試しください。',INVALID_REQUEST:'質問は1〜1000文字で入力してください。',NOT_FOUND:'対象の記事・質問が見つかりません。',ACCOUNT_NOT_CONNECTED:'本人のCopilotを接続してください。「接続設定」から操作できます。'});
  const supportsArticle=id=>/^(jp|us|eu|cn|in|paper)\d+$/.test(id||'');
  const mentionPattern=/(?:^|\s)@copilot(?=$|[\s、,:：?？])/i;
  const savedKey=()=>`dailynews-copilot-question:${window.DAILYNEWS_CONFIG?.id||'interior'}:${who()?.id}`;
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
      button.textContent=busy?'Copilotが回答中…':state.kind==='question'?'質問する':j?.status==='done'?'Copilotの回答':'Copilotへ質問';
      reply.hidden=!(state.error||j);
      if(reply.hidden)continue;
      reply.append(element('strong','Copilot · 自分だけに表示'));
      if(j?.question)reply.append(element('small','質問：'+j.question));
      const answer=element('p');
      const text=state.error||(j.status==='done'?j.answer:j.status==='needs_review'?'送信済みです。結果を確認できないため自動再送を停止しました。':j.status==='error'?errorText({code:j.code}):j.status==='queued'?'順番を待っています…':'本人のCopilotで回答を取得しています…');
      for(const part of String(text||'').split(/(\[(?:jp|us|eu|cn|in|paper)\d+\])/g)){
        const source=j?.sources?.find(s=>'['+s.id+']'===part);
        if(source?.url && /^https?:\/\//i.test(source.url)){const a=element('a',part);a.href=source.url;a.target='_blank';a.rel='noopener noreferrer';a.title=source.title;answer.append(a);}else answer.append(document.createTextNode(part));
      }
      reply.append(answer);
      if(j?.context){const c=j.context,label=c.scope==='new'?'本日のNEW':c.scope==='all'?'掲載ニュース全体':'この記事';
        reply.append(element('small',`${label} ${c.total}件から${c.used}件の掲載要約を参照（${c.dateFrom||'日付不明'}〜${c.dateTo||'日付不明'}）`));
        if(j.sources?.length){const details=element('details'),summary=element('summary',`参照候補の記事 ${j.sources.length}件`),list=element('ul');details.append(summary,list);
          for(const s of j.sources){const li=element('li'),a=element(s.url?'a':'span',`[${s.id}] ${s.title}`);if(s.url){a.href=s.url;a.target='_blank';a.rel='noopener noreferrer';}li.append(a);list.append(li);}reply.append(details);}}
      if(j?.conversationUrl){const link=element('a','Copilotで会話を開く');link.href=j.conversationUrl;link.target='_blank';link.rel='noopener noreferrer';reply.append(link);}
      if(j?.status==='needs_review'){
        const retry=element('button','確認して再試行','copilot-retry');retry.type='button';retry.disabled=!!state.loading;
        retry.onclick=()=>{
          const d=dialog('Copilotへの再試行');
          d.append(element('p','前の質問はCopilotに送信済みの可能性があります。再試行すると、Copilot側に同じ質問がもう一つ残る場合があります。前回の記録を保存し、1回だけ再送します。'));
          const send=element('button','1回だけ再送する');send.type='button';d.append(send);
          const id=j.id,createdAt=j.createdAt,member=userKey;
          send.onclick=async()=>{if(state.loading)return;send.disabled=true;d.close();state.loading=true;state.error='';render(state);
            try{const r=await api('/jobs/'+id+'/retry','POST',{createdAt});if(userKey!==member)return;state.job=r.job;void poll(state,member);}
            catch(e){if(userKey===member)state.error=errorText(e);}finally{if(userKey===member){state.loading=false;render(state);}}};
        };reply.append(retry);
      }
      if(j?.status==='done')reply.append(element('small','AIの回答です。記事で確認できる事実と仮説を分けてご確認ください。回答日時：'+new Date(j.completedAt||j.createdAt).toLocaleString('ja-JP',{timeZone:'Asia/Tokyo'})));
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
    const d=element('dialog',undefined,'copilot-dialog'),header=element('header'),h=element('h2',title),close=element('button','閉じる');d.setAttribute('aria-label',title);close.type='button';close.onclick=()=>d.close();header.append(h,close);d.append(header);document.body.append(d);d.showModal();d.addEventListener('close',()=>d.remove(),{once:true});return d;
  }
  async function settings() {
    const d=dialog('本人のCopilotを接続'),p=element('p','接続状態を確認しています…');d.append(p);
    try {const a=await api('/account');p.textContent=a.connected?`${a.email} のCopilotに接続済みです。回答はこのアカウントだけに表示します。`:'初回は本人のMicrosoftサインインが必要です。接続画面のMicrosoft表示を操作します。パスワードは保存せず、本人確認済みのセッションだけを暗号化して保存します。';
      const controls=element('div',undefined,'copilot-connect-tools');d.append(controls);
      if(a.connected){const off=element('button','Copilotの接続を解除');off.onclick=async()=>{off.disabled=true;await api('/account','DELETE');d.close();};controls.append(off);}
      const connect=element('button',a.connected?'接続し直す':'Microsoftに接続');controls.append(connect);
      const secure=new URL(location.href);secure.protocol='https:';secure.port='';secure.hash='copilot-connect';
      connect.onclick=()=>{d.close();if(inlineConnection())void connectScreen();else window.open(secure.href,'dailynews-copilot-connect','noopener');};
      if(location.protocol!=='https:' && inlineConnection()){
        d.append(element('p','社内HTTP接続が有効です。この画面で本人のMicrosoftサインインを進められます。証明書の登録やツールのインストールは不要です。','copilot-connect-note'));
        d.append(element('p','社内PCとDailyNewsサーバー間の入力・画面通信は暗号化されません。パスワードは保存せず、接続情報は本人ごとに暗号化して保存します。','copilot-connect-note'));
      }else if(location.protocol!=='https:'){
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
    if(location.protocol==='http:')d.append(element('p','社内HTTP接続：入力と画面は社内PC―サーバー間で暗号化されません。本人の会社アカウントで操作してください。','copilot-connect-note'));
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
      if(!alive||userKey!==key){const cancelled=id;id=null;await api('/connection/'+cancelled,'DELETE');return;}
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
    try {const a=await api('/account');if(userKey!==key)return;if(!a.connected){state.error=messages.ACCOUNT_NOT_CONNECTED;await settings();return;}
      const r=await api('/jobs','POST',{itemId:state.itemId,commentId:state.commentId});if(userKey!==key)return;state.job=r.job;void poll(state,key);
    }catch(e){if(userKey===key)state.error=errorText(e);}finally{if(userKey===key){state.loading=false;render(state);}}
  }
  function scan() {
    scanPending=false;if(!who())return;
    ensureEntry();
    document.querySelectorAll('.card[id^="card-"] .comment-input-area').forEach(area=>{
      if(!supportsArticle(area.closest('.card').id.slice(5))||area.dataset.copilotHint)return;
      area.dataset.copilotHint='true';const input=area.querySelector('.comment-input');if(!input)return;
      const hint=element('small','@Copilot の質問はコメントとして公開されます。回答は本人だけに表示します。','copilot-mention-hint');hint.hidden=!mentionPattern.test(input.value);area.after(hint);
      input.addEventListener('input',()=>{hint.hidden=!mentionPattern.test(input.value);});
    });
    for(const comment of document.querySelectorAll('.comment-item[data-comment-id]')){
      if(comment.querySelector('.copilot-controls'))continue;
      const card=comment.closest('.card[id^="card-"]'),itemId=card?.id.slice(5),commentId=Number(comment.dataset.commentId);
      if(!/^(jp|us|eu|cn|in|paper)\d+$/.test(itemId||'')||!commentId)continue;
      const key=itemId+'-'+commentId;let state=states.get(key);const fresh=!state;
      if(!state){state={key,itemId,commentId,job:null};states.set(key,state);}
      const box=element('div',undefined,'copilot-controls');box.dataset.copilotKey=key;
      const button=element('button','Copilotへ質問','copilot-question');button.type='button';button.onclick=()=>void ask(state);
      const account=element('button','接続設定','copilot-settings');account.type='button';account.onclick=()=>void settings();
      const reply=element('div',undefined,'copilot-reply');reply.setAttribute('aria-live','polite');reply.hidden=true;box.append(button,account,reply);comment.append(box);render(state);
      if(fresh){const member=userKey;void api('/current?itemId='+itemId+'&commentId='+commentId).then(r=>{if(userKey!==member||state.loading||state.job)return;state.job=r.job;render(state);void poll(state,member);}).catch(()=>{});}
    }
  }
  function ensureEntry(){
    if(document.getElementById('copilotNewsButton'))return;
    const parent=document.querySelector('.header-top-actions')||document.querySelector('header#top');if(!parent)return;
    const b=element('button','Copilot · ニュースに質問','copilot-news-entry');b.id='copilotNewsButton';b.type='button';b.onclick=()=>void newsDialog();parent.append(b);
  }
  async function newsDialog(){
    if(!who()){window.dailyNewsAccount?.openAuth?.('login','Copilotへの質問にはログインが必要です。');return;}
    const d=dialog('Copilot · ニュースに質問');d.classList.add('copilot-news-dialog');
    d.append(element('p','本人のCopilotに質問し、短い回答をここに表示します。この質問は公開コメントには投稿されません。'));
    let state=states.get('news-question');if(!state){state={key:'news-question',kind:'question',job:null};states.set(state.key,state);}
    const form=element('form'),scopeLabel=element('label','対象'),scope=element('select');scope.id='copilotNewsScope';scopeLabel.htmlFor=scope.id;
    for(const [value,label] of [['new','本日のNEW'],['all','掲載ニュース全体']]){const o=element('option',label);o.value=value;scope.append(o);}
    scope.value=state.scope||'new';scope.onchange=()=>{state.scope=scope.value;};
    const label=element('label','質問'),input=element('textarea');input.id='copilotNewsQuestion';label.htmlFor=input.id;input.rows=3;input.maxLength=1000;input.required=true;input.value=state.draft||'';
    input.placeholder='例：内装イルミに関するトレンドを教えて';input.oninput=()=>{state.draft=input.value;};
    const examples=element('div',undefined,'copilot-examples');
    for(const [text,target] of [['今日のニュースで私に関係するニュースをピックアップして','new'],[`${window.DAILYNEWS_CONFIG?.id==='exterior'?'外装':'内装'}イルミに関するトレンドを教えて`,'all']]){
      const b=element('button',text);b.type='button';b.onclick=()=>{scope.value=target;state.scope=target;input.value=text;state.draft=text;input.focus();};examples.append(b);}
    const box=element('div',undefined,'copilot-query-controls');box.dataset.copilotKey=state.key;
    const send=element('button','質問する','copilot-question');send.type='submit';
    const settingsButton=element('button','接続設定','copilot-settings');settingsButton.type='button';settingsButton.onclick=()=>void settings();
    const reply=element('div',undefined,'copilot-reply');reply.setAttribute('aria-live','polite');reply.hidden=true;box.append(send,settingsButton,reply);
    form.append(scopeLabel,scope,label,input,examples,element('small','NEWは画面のNEW表示と同じ対象です。全体への質問では関連する記事を最大30件選び、参照範囲を回答と一緒に表示します。'),box);d.append(form);render(state);
    form.onsubmit=async e=>{e.preventDefault();if(state.loading||state.job&&!['done','error','needs_review'].includes(state.job.status))return;
      const member=userKey,question=input.value.trim();if(!question)return;
      state.loading=true;state.error='';render(state);
      try{const account=await api('/account');if(userKey!==member)return;
        if(!account.connected){state.error=messages.ACCOUNT_NOT_CONNECTED;await settings();return;}
        const r=await api('/questions','POST',{scope:scope.value,question});if(userKey!==member)return;state.job=r.job;
        try{sessionStorage.setItem(savedKey(),state.job.id);}catch{}void poll(state,member);
      }catch(error){if(userKey===member)state.error=errorText(error);}finally{if(userKey===member){state.loading=false;render(state);}}
    };
    if(!state.job&&!state.loading){let id;try{id=sessionStorage.getItem(savedKey());}catch{}
      if(/^[a-f0-9]{64}$/.test(id||'')){const member=userKey;try{const r=await api('/jobs/'+id);if(userKey===member&&!state.loading&&!state.job){state.job=r.job;render(state);void poll(state,member);}}catch{}}}
  }
  window.dailyNewsCopilot={supportsArticle,askComment:async(itemId,commentId)=>{
    if(!supportsArticle(itemId)||!who())return;
    scan();const key=itemId+'-'+commentId;let state=states.get(key);
    if(!state){state={key,itemId,commentId,job:null};states.set(key,state);}
    if(state.loading)return;await ask(state);
  }};
  function changed(){userKey=who()?.email||'';states.clear();document.querySelectorAll('.copilot-controls').forEach(el=>el.remove());document.querySelectorAll('.copilot-dialog').forEach(el=>el.close());scan();}
  function ready(){if(initialized)return;initialized=true;changed();new MutationObserver(()=>{if(!scanPending){scanPending=true;requestAnimationFrame(scan);}}).observe(document.body,{childList:true,subtree:true});
    if(location.hash==='#copilot-connect'&&who()&&inlineConnection()){history.replaceState(null,'',location.pathname+location.search);void connectScreen();}}
  window.addEventListener('dailynews:account-changed',changed);window.addEventListener('dailynews:account-ready',ready,{once:true});
  if(window.dailyNewsAccount?.ready)ready();
})();
