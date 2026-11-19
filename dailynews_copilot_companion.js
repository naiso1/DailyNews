"use strict";
// Personal-account UI. Provider identity, article selection and deduplication stay server-side.
(() => {
  const validId = id => /^(jp|us|eu|cn|in|paper)\d+$/.test(id || '');
  const validJob = id => /^[a-f0-9]{64}$/.test(id || '');
  const terminal = job => ['done','error','needs_review'].includes(job?.status);
  function httpUrl(value, conversation = false) {
    try { const u=new URL(value);return ['http:','https:'].includes(u.protocol)&&(!conversation||(u.protocol==='https:'&&['copilot.cloud.microsoft','copilot.microsoft.com'].includes(u.hostname)))?u.href:null; } catch { return null; }
  }
  function composeQuestion(text, prior) {
    const question=String(text||'').trim();
    if(!question||question.length>1000)throw new Error('INVALID_REQUEST');
    if(!prior)return question;
    if(prior.status!=='done'||!prior.question||!prior.answer)throw new Error('NO_PRIOR_ANSWER');
    const result=`前の質問：${prior.question.slice(0,220)}\n前の回答（参考）：${prior.answer.slice(0,400)}\n追加の質問：${question}`;
    if(result.length>1000)throw new Error('FOLLOWUP_TOO_LONG');
    return result;
  }
  function identity(user) {return user?.id&&user?.email?`${user.id}:${String(user.email).toLowerCase()}`:'';}
  function canRepeat(records,input) {return !records.some(r=>r.uncertain&&r.input?.scope===input.scope&&r.input?.itemId===input.itemId&&r.input?.question===input.question);}
  if(typeof module==='object'&&module.exports){module.exports={validId,validJob,terminal,httpUrl,composeQuestion,identity,canRepeat};return;}
  if(new URLSearchParams(location.search).get('copilot')==='classic'||window.dailyNewsCopilotCompanion)return;
  const config=window.DAILYNEWS_CONFIG||{},base=config.apiBase||'/api',path=config.basePath||'';
  const image=path+'/page_images/copilot_companion_20261118.png';
  const errors={ACCOUNT_NOT_CONNECTED:'本人のCopilotが未接続です。「接続設定」を開いてください。',AUTH_REQUIRED:'Microsoftへの再接続が必要です。「接続設定」を開いてください。',ACCOUNT_MISMATCH:'DailyNewsとMicrosoftのアカウントが一致しません。本人の会社アカウントで接続してください。',ACCOUNT_CHANGED:'ログイン中のアカウントが変わりました。ページを再読み込みしてください。',WORKER_OFFLINE:'Copilot連携用のPCに接続できません。少し待って接続状態を確認してください。',BUSY:'別の質問・接続処理が実行中です。少し待ってからお試しください。',NETWORK_ERROR:'通信を確認できませんでした。質問の自動再送は行いません。',SERVER_UNAVAILABLE:'サーバーの応答を確認できませんでした。質問の自動再送は行いません。',NO_NEWS:'対象のニュースがまだありません。',NO_RELEVANT_NEWS:'この条件に合う記事がありません。対象か質問を変えてお試しください。',INVALID_REQUEST:'質問を1〜1000文字で入力してください。',FOLLOWUP_TOO_LONG:'前の回答と合わせて長くなっています。追加の質問を短くするか、「前の回答を参照」を解除してください。',NO_PRIOR_ANSWER:'前の回答を読み込んでからお試しください。',SEND_NOT_READY:'Copilotの入力画面を準備できませんでした。質問は未送信です。',NOT_FOUND:'対象の記事・質問が見つかりません。',RESULT_UNCONFIRMED:'送信済みの可能性があるため、自動再送を停止しています。',INTERRUPTED:'処理が中断されました。送信済みの場合は自動再送しません。'};
  let member='',epoch=0,records=[],draft='',scope='new',replyTo=null,previewItem=null,openingSource=null;
  let sending=false,restoring=false,opened=false,reading=false,account=null,notice='',scroll=0,saveTimer=null,pollTimer=null,checking=null;
  const who=()=>window.dailyNewsAccount?.user;
  const key=()=>`dailynews-copilot-companion:${config.id||'interior'}:${member}`;
  const same=stamp=>stamp===epoch&&member&&member===identity(who());
  const errText=e=>errors[e?.code||e?.message]||'接続を確認できませんでした。「接続状態を確認」から確認してください。';
  const el=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
  const button=(text,fn,cls)=>{const b=el('button',text,cls);b.type='button';b.onclick=fn;return b;};
  const avatar=()=>{const img=el('img');img.src=image;img.alt='';return img;};
  const sessionRead=()=>{try{return JSON.parse(sessionStorage.getItem(key())||'{}');}catch{return {};}};
  function save(){if(!member)return;try{sessionStorage.setItem(key(),JSON.stringify({draft,scope,open:opened,scroll,records:records.slice(-20).map(r=>({id:r.job?.id||r.id,input:r.input,display:r.display,uncertain:r.uncertain,error:r.error})),replyTo}));}catch{}}
  // Answers are never stored in browser storage: restore only owner-checked job IDs.
  async function request(route,method='GET',body) {
    let response,data;try{response=await fetch(base+route,{method,credentials:'same-origin',cache:'no-store',headers:{'Content-Type':'application/json'},...(body!==undefined?{body:JSON.stringify(body)}:{})});}catch{throw {code:'NETWORK_ERROR'};}
    try{data=await response.json();}catch{throw {code:'SERVER_UNAVAILABLE'};}
    if(!response.ok)throw {code:data.error?.code||data.error||data.code||(response.status===401?'ACCOUNT_CHANGED':'SERVER_UNAVAILABLE')};return data;
  }
  async function verifyMember(stamp){const auth=await request('/auth/me');if(!same(stamp)||identity(auth.user)!==member){if(stamp===epoch){clearPrivate();notice=errors.ACCOUNT_CHANGED;renderStatus();}throw {code:'ACCOUNT_CHANGED'};}}
  async function checkAccount(){
    if(checking)return checking;
    const stamp=epoch;checking=(async()=>{try{await verifyMember(stamp);const a=await request('/copilot/account');if(!same(stamp))return;
      if(a.connected&&String(a.email||'').toLowerCase()!==String(who()?.email||'').toLowerCase())throw {code:'ACCOUNT_MISMATCH'};
      account=a;notice=a.connected?'':errors.ACCOUNT_NOT_CONNECTED;
    }catch(e){if(same(stamp)){account=null;notice=errText(e);if(e.code==='ACCOUNT_CHANGED')clearPrivate();}}finally{checking=null;renderStatus();}})();return checking;
  }
  const host=el('div',undefined,'dncp-host');host.id='dailynewsCompanion';document.body.append(host);document.body.classList.add('dncp-enabled');
  const launcher=el('div',undefined,'dncp-launcher');
  const bubble=button('Copilotに相談',()=>open(),'dncp-bubble');bubble.append(el('small','ニュースのこと、聞いてみませんか'));
  const pet=button('',()=>open(),'dncp-pet');pet.setAttribute('aria-label','Copilotを開く');pet.append(avatar());launcher.append(bubble,pet);
  const panel=el('aside',undefined,'dncp-panel');panel.setAttribute('aria-label','Copilotとの会話');panel.hidden=true;
  const header=el('header',undefined,'dncp-header'),heading=el('div');heading.append(el('h2','Copilot'),el('small','本人のアカウント · 自分だけの会話'));
  const minimize=button('−',()=>close(),'dncp-minimize');minimize.setAttribute('aria-label','会話を最小化');header.append(avatar(),heading,minimize);
  const connection=el('div','接続状態を確認します','dncp-connection');
  const transcript=el('div',undefined,'dncp-transcript');transcript.tabIndex=0;transcript.setAttribute('aria-label','質問と回答');
  const status=el('p',undefined,'dncp-status');status.setAttribute('role','status');
  const composer=el('form',undefined,'dncp-composer'),contextRow=el('div',undefined,'dncp-context'),scopeLabel=el('label','対象'),select=el('select');select.id='dncpScope';scopeLabel.htmlFor=select.id;
  for(const [value,label] of [['new','本日のNEW'],['all','掲載ニュース全体から検索'],['article','開いている記事']]){const o=el('option',label);o.value=value;if(value==='article')o.disabled=true;select.append(o);}
  select.onchange=()=>{scope=select.value;save();};
  const detailToggle=button('詳細',()=>{details.hidden=!details.hidden;detailToggle.setAttribute('aria-expanded',String(!details.hidden));},'dncp-text-button');detailToggle.setAttribute('aria-expanded','false');contextRow.append(scopeLabel,select,detailToggle);
  const details=el('div',undefined,'dncp-details');details.hidden=true;
  details.append(el('p','NEWは対象ニュースの要約をまとめて参照します（最大80件）。全体は関連する最大30件。参照した範囲は回答と一緒に表示します。質問・回答は公開コメントに投稿されません。'));
  details.append(button('接続設定',()=>window.dailyNewsCopilot?.openSettings?.(),'dncp-text-button'),button('接続状態を確認',()=>void refresh(),'dncp-text-button'));
  const normal=el('a','従来の質問画面を使う');const normalUrl=new URL(location.href);normalUrl.searchParams.set('copilot','classic');normal.href=normalUrl.href;details.append(normal);
  const followup=el('div',undefined,'dncp-followup-context');followup.hidden=true;
  const field=el('div',undefined,'dncp-field'),input=el('textarea');input.rows=2;input.maxLength=1000;input.placeholder='気になることを聞いてみる…';input.setAttribute('aria-label','Copilotへの質問');
  input.oninput=()=>{draft=input.value;save();renderStatus();};
  input.onkeydown=e=>{if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)&&!e.isComposing){e.preventDefault();void submit();}};
  const send=el('button','送信','dncp-send');send.type='submit';send.setAttribute('aria-label','質問する');field.append(input,send);
  const hint=el('small','Ctrl＋Enterで送信 · 回答は自分だけに表示','dncp-hint');composer.append(contextRow,details,followup,status,field,hint);composer.onsubmit=e=>{e.preventDefault();void submit();};panel.append(header,connection,transcript,composer);
  const article=el('section',undefined,'dncp-article');article.hidden=true;article.setAttribute('aria-label','参照記事');
  host.append(launcher,panel,article);
  transcript.onscroll=()=>{scroll=transcript.scrollTop;clearTimeout(saveTimer);saveTimer=setTimeout(save,150);};
  function renderStatus(){
    connection.textContent=!member?'DailyNewsへのログインが必要です':account?.connected?`${who()?.displayName||who()?.name||'本人'}のCopilotに接続済み · 自分だけに表示`:'接続を確認してください';
    status.textContent=notice;status.hidden=!notice;
    send.disabled=!member||sending||restoring||records.some(r=>r.job&&!terminal(r.job))||!draft.trim();
    send.textContent=sending||records.some(r=>r.job&&!terminal(r.job))?'回答中…':'送信';
    select.disabled=sending;followup.replaceChildren();followup.hidden=!replyTo;
    if(replyTo){followup.append(el('span','前の回答を参照して質問'),button('解除',()=>{replyTo=null;renderStatus();save();},'dncp-text-button'));}
  }
  function setDraft(text,target){draft=text;input.value=text;if(target){scope=target;select.value=target;}save();renderStatus();input.focus();}
  function open(){if(!member){window.dailyNewsAccount?.openAuth?.('login','本人のCopilotへの質問にはログインが必要です。');return;}
    opened=true;reading=false;panel.hidden=false;launcher.hidden=true;host.classList.remove('dncp-reading');document.body.classList.add('dncp-open');transcript.scrollTop=scroll;save();void checkAccount();}
  function close(){scroll=transcript.scrollTop;opened=false;panel.hidden=true;launcher.hidden=false;document.body.classList.remove('dncp-open');hideArticle();save();}
  function hideArticle(){article.hidden=true;reading=false;host.classList.remove('dncp-reading');previewItem=null;select.querySelector('[value="article"]').disabled=true;if(scope==='article'){scope='new';select.value=scope;}openingSource?.focus({preventScroll:true});}
  function showArticle(source,sourceButton){
    const item=window.resolveDailyNewsItem?.(source.id);article.replaceChildren();openingSource=sourceButton;
    const bar=el('div',undefined,'dncp-article-bar');bar.append(button('← ニュース一覧に戻る',hideArticle,'dncp-text-button'),el('small','DailyNews 掲載記事'));article.append(bar);
    if(!item){article.append(el('p','この記事は現在の掲載一覧にありません。非表示・更新された可能性があります。回答は会話欄に残っています。'));}
    else{
      previewItem=item;select.querySelector('[value="article"]').disabled=false;
      const body=el('div',undefined,'dncp-article-body'),url=httpUrl(window.getNewsImageUrl?.(item)||item.img);
      if(url){const img=el('img');img.src=url;img.alt='';img.onerror=()=>img.remove();img.onload=()=>{if(img.naturalWidth<=2)img.remove();};body.append(img);}
      const copy=el('div',undefined,'dncp-article-copy'),title=el('h2',item.title);title.tabIndex=-1;
      copy.append(el('small',`${item.source||''} · ${item.date||''}`),title,el('h3','掲載要約'),el('p',item.desc||'要約は登録されていません。'));
      const actions=el('div',undefined,'dncp-article-actions');actions.append(button('この記事について相談',()=>{scope='article';select.value=scope;reading=false;host.classList.remove('dncp-reading');input.focus();save();},'dncp-primary'));
      const sourceUrl=httpUrl(item.url);if(sourceUrl){const a=el('a','元サイトを別タブで開く ↗');a.href=sourceUrl;a.target='_blank';a.rel='noopener noreferrer';actions.append(a);}copy.append(actions);body.append(copy);article.append(body);
    }
    const back=button('会話に戻る',()=>{reading=false;host.classList.remove('dncp-reading');},'dncp-mobile-return dncp-primary');article.append(back);article.hidden=false;article.scrollTop=0;reading=true;host.classList.add('dncp-reading');
  }
  function sourceLink(source,label){const b=button(label||source.title||source.id,()=>showArticle(source,b),'dncp-source');b.title=source.title||source.id;b.setAttribute('aria-label','記事を開く：'+(source.title||source.id));return b;}
  function renderRecord(r){
    const fragment=document.createDocumentFragment(),question=el('div',undefined,'dncp-question');question.append(el('small','あなた'),el('p',r.display||r.job?.question||r.input?.question||'質問'));fragment.append(question);
    const answer=el('div',undefined,'dncp-answer');answer.append(el('strong','Copilot'));
    if(r.error){answer.append(el('p',r.error));if(r.uncertain)answer.append(el('small','同じ質問の自動再送は行いません。Copilotの会話をご確認ください。'));}
    const j=r.job;
    if(j){
      const p=el('p',undefined,'dncp-answer-text');
      const value=j.status==='done'?j.answer:j.status==='needs_review'?'送信結果を確認できませんでした。重複を防ぐため自動再送を停止しています。':j.status==='error'?errText({code:j.code}):j.status==='queued'?'順番を待っています…':'本人のCopilotで回答を取得しています…';
      for(const part of String(value||'').split(/(\[(?:jp|us|eu|cn|in|paper)\d+\])/g)){
        const s=j.sources?.find(s=>validId(s.id)&&`[${s.id}]`===part);
        if(s)p.append(sourceLink(s,(s.title||s.id).slice(0,28)+((s.title||'').length>28?'…':'')));else p.append(document.createTextNode(part));
      }answer.append(p);
      if(j.context){const c=j.context;answer.append(el('small',`${c.scope==='new'?'本日のNEW':c.scope==='all'?'掲載ニュース全体':'この記事'} ${c.total}件から${c.used}件の掲載要約を参照（${c.dateFrom||'日付不明'}〜${c.dateTo||'日付不明'}）`));}
      if(j.sources?.length){const candidates=el('details'),summary=el('summary',`参照候補 ${j.sources.length}件`),links=el('div',undefined,'dncp-source-list');for(const s of j.sources)if(validId(s.id))links.append(sourceLink(s));candidates.append(summary,links);answer.append(candidates);}
      const conversation=httpUrl(j.conversationUrl,true);if(conversation){const a=el('a','Copilotで会話を開く ↗');a.href=conversation;a.target='_blank';a.rel='noopener noreferrer';answer.append(a);}
      if(j.status==='done'){answer.append(el('small','AIの回答です。事実と仮説を分けてご確認ください。'),button('この回答を踏まえて質問',()=>{replyTo=j.id;setDraft('もう少し具体的に教えて');},'dncp-followup'))}
      if(!terminal(j)||r.error)answer.append(button('回答の状態を確認',()=>void refresh(),'dncp-text-button'));
      if(j.status==='needs_review')answer.append(el('small','送信済みの可能性があります。「Copilotで会話を開く」から確認してください。自動再送はしません。'));
    }fragment.append(answer);return fragment;
  }
  function render(scrollToEnd=false){const old=transcript.scrollTop;transcript.replaceChildren();
    if(!records.length){const welcome=el('div',undefined,'dncp-welcome');welcome.append(el('small','YOUR NEWS COMPANION'),el('h3','気になるニュースから、少し先の話を。'),el('p','本人のCopilotに質問します。記事を開いても、この会話は残ります。'));
      const examples=el('div',undefined,'dncp-examples');for(const [text,target] of [['今日のニュースで私に関係するニュースをピックアップして','new'],['今日のニュースの考察を教えて','new'],[`${config.id==='exterior'?'外装':'内装'}イルミに関するトレンドを教えて`,'all']])examples.append(button(text,()=>setDraft(text,target)));welcome.append(examples);transcript.append(welcome);
    }else for(const r of records)transcript.append(renderRecord(r));
    transcript.scrollTop=scrollToEnd?transcript.scrollHeight:old;scroll=transcript.scrollTop;renderStatus();save();}
  async function readJob(r,stamp){await verifyMember(stamp);const result=await request('/copilot/jobs/'+r.id);await verifyMember(stamp);if(!same(stamp))return;r.job=result.job;r.error='';}
  function schedulePoll(){clearTimeout(pollTimer);if(records.some(r=>r.job&&!terminal(r.job)))pollTimer=setTimeout(()=>void poll(),2500);}
  async function poll(){const stamp=epoch;try{for(const r of records.filter(r=>r.job&&!terminal(r.job))){await readJob(r,stamp);if(!same(stamp))return;}render();}catch(e){if(same(stamp)){notice=errText(e);renderStatus();}}finally{if(same(stamp)&&!notice)schedulePoll();}}
  async function refresh(){const stamp=epoch;notice='';await checkAccount();if(!same(stamp))return;try{for(const r of records.filter(r=>validJob(r.id))){await readJob(r,stamp);if(!same(stamp))return;}render();schedulePoll();}catch(e){if(same(stamp)){notice=errText(e);renderStatus();}}}
  async function submit(){
    if(sending||restoring||records.some(r=>r.job&&!terminal(r.job))||!draft.trim())return;
    const stamp=epoch;let payload;notice='';
    try{payload={scope,question:composeQuestion(draft,replyTo?records.find(r=>r.job?.id===replyTo)?.job:null),...(scope==='article'?{itemId:previewItem?.id}:{})};if(scope==='article'&&!validId(payload.itemId))throw {code:'NOT_FOUND'};
      if(!canRepeat(records,payload))throw {code:'RESULT_UNCONFIRMED'};
    }catch(e){notice=errText(e);renderStatus();return;}
    sending=true;renderStatus();let record=null;
    try{await verifyMember(stamp);await checkAccount();if(!same(stamp))return;if(!account?.connected)throw {code:'ACCOUNT_NOT_CONNECTED'};
      record={input:payload,display:draft,uncertain:true};records.push(record);save(); // Persist intent before the only POST; a lost response must not cause resubmission.
      const result=await request('/copilot/questions','POST',payload);
      await verifyMember(stamp);if(!same(stamp))return;
      record.job=result.job;record.id=result.job.id;record.uncertain=false;draft='';input.value='';replyTo=null;render(true);schedulePoll();
    }catch(e){if(same(stamp)){if(record){record.error=errText(e);if(!['NETWORK_ERROR','SERVER_UNAVAILABLE','ACCOUNT_CHANGED'].includes(e.code))record.uncertain=false;}else notice=errText(e);render(true);}}
    finally{if(same(stamp)){sending=false;renderStatus();save();}}
  }
  function clearPrivate(){epoch++;clearTimeout(pollTimer);clearTimeout(saveTimer);if(member){try{sessionStorage.removeItem(key());}catch{}}member='';records=[];draft='';input.value='';replyTo=null;account=null;sending=false;restoring=false;checking=null;close();render();}
  async function changed(){const next=identity(who());if(next===member)return;if(member)clearPrivate();member=next;epoch++;const stamp=epoch;if(!member){renderStatus();return;}
    const saved=sessionRead();draft=typeof saved.draft==='string'?saved.draft.slice(0,1000):'';scope=['new','all'].includes(saved.scope)?saved.scope:'new';input.value=draft;select.value=scope;scroll=Number(saved.scroll)||0;opened=!!saved.open;
    records=Array.isArray(saved.records)?saved.records.filter(r=>validJob(r.id)||r.uncertain).slice(-20):[];restoring=true;const savedScroll=scroll;render();if(opened)open();
    try{await verifyMember(stamp);for(const r of records.filter(r=>validJob(r.id))){await readJob(r,stamp);if(!same(stamp))return;}}
    catch(e){if(same(stamp))notice=errText(e);}finally{if(same(stamp)){restoring=false;replyTo=records.some(r=>r.job?.id===saved.replyTo&&r.job.status==='done')?saved.replyTo:null;render();transcript.scrollTop=savedScroll;scroll=savedScroll;save();schedulePoll();}}
  }
  window.dailyNewsCopilotCompanion={open};
  window.addEventListener('dailynews:account-changed',()=>void changed());window.addEventListener('dailynews:account-ready',()=>void changed(),{once:true});
  window.addEventListener('focus',()=>{if(opened&&member)void checkAccount();});
  if(window.dailyNewsAccount?.ready)void changed();
  renderStatus();
})();
