const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const read=p=>fs.readFileSync(path.join(__dirname,'..',p),'utf8').replace(/\r\n/g,'\n');
const html=read('内装製品デイリーニュース.html'),client=read('dailynews_client.js'),companion=read('dailynews_copilot_companion.js');
function extract(source,name,indent='        '){const start=source.indexOf(indent+'function '+name+'(');assert(start>=0,name);const marker='\n'+indent+'}';return source.slice(start,source.indexOf(marker,start)+marker.length);}
test('citations and list use identical normal cards with distinct DOM IDs and the same article IDs',()=>{
 const ctx=vm.createContext({document:{createElement:()=>({dataset:{}})},window:{interactionsData:{jp2298:{likes:2,comments:1,reads:12}}},
  isFavorite:()=>false,favoritesOnly:false,selectedFavoriteKeys:new Set(),isNewContent:()=>true,
  getNewsImageUrl:n=>n.img,getDisplayImageUrl:s=>s,renderRelatedNewsSources:()=>'',COUNTRY_FLAGS:{jp:'🇯🇵'},COUNTRY_NAMES:{jp:'日本'}});
 for(const name of ['escapeHtml','renderArticleTools','renderReactionButtons','renderCommentSection','renderNewsActions','createNewsCard'])vm.runInContext(extract(html,name),ctx);
 const item={id:'jp2298',country:'jp',title:'日産ルークス',desc:'快適パック',tags:['音響'],date:'2026-11-19',source:'MotorFan',img:'https://example.test/a.png',url:'https://example.test/a',interiorScore:60};
 const list=ctx.createNewsCard(item),preview=ctx.createNewsCard(item,{preview:true});
 assert.notEqual(preview.id,list.id);assert.equal(preview.dataset.newsId,list.dataset.newsId);assert.equal(preview.innerHTML,list.innerHTML);
 for(const text of ['country-badge','relevance-badge','card-tags','favorite-btn',"toggleLike('jp2298'","toggleComments('jp2298'",'article-copilot-btn','article-settings-btn','comment-section'])assert(preview.innerHTML.includes(text),text);
 assert(!preview.innerHTML.includes('ご意見'));assert(!preview.innerHTML.includes('requestArticleRemoval'));
 assert.equal(ctx.renderArticleTools("jp1');alert(1)//"),'');
 ctx.favoritesOnly=true;assert(!ctx.createNewsCard(item,{preview:true}).innerHTML.includes('favorite-select-wrap'));
});
test('opening a citation and selecting its Copilot button preserves the conversation and draft without sending',()=>{
 const nodes=()=>({children:[],append(...children){this.children.push(...children)},replaceChildren(){this.children=[]},querySelectorAll(){return this.children.filter(c=>c.isCard)},querySelector(){return this.children.find(c=>c.isCard)||null}});
 const article=nodes(),option={},input={value:'途中の質問',focus(){this.focused=true}},saved=[];
 const item={id:'jp2298',title:'ルークス'},classes=new Set();let disposed=0;
 const ctx=vm.createContext({article,select:{querySelector:()=>option},input,document:{activeElement:{focus(){}}},member:'owner',
  previewItem:null,openingSource:null,scope:'new',reading:false,records:[{answer:'保存済みの回答'}],draft:input.value,
  host:{classList:{add:c=>classes.add(c),remove:c=>classes.delete(c)}},
  window:{resolveDailyNewsItem:id=>id===item.id?item:null,createDailyNewsCard:()=>({...nodes(),isCard:true,_disposeNewsImageCarousel:()=>disposed++})},
  button:(text,fn)=>({text,onclick:fn}),el:()=>nodes(),renderStatus(){},save:()=>saved.push(true),open(){},
  fetch(){throw Error('No question should be submitted');}});
 // Evaluate the real preview/selection implementation, not a parallel test implementation.
 const start=companion.indexOf('  function disposeArticle('),end=companion.indexOf('  function sourceLink(',start);
 vm.runInContext(companion.slice(start,end),ctx);
 ctx.showArticle(item,ctx.document.activeElement);assert(article.children.some(c=>c.isCard));
 ctx.askArticle(item.id);assert.equal(ctx.scope,'article');assert.equal(ctx.previewItem.id,item.id);assert.equal(ctx.reading,false);assert(input.focused);
 assert.equal(ctx.draft,'途中の質問');assert.equal(ctx.records[0].answer,'保存済みの回答');
 ctx.hideArticle();assert.equal(disposed,1);assert.equal(ctx.scope,'new');assert.equal(ctx.records.length,1);assert.equal(input.value,'途中の質問');
 ctx.showArticle({id:'jp999'},null);assert.equal(ctx.previewItem,null);assert.equal(option.disabled,true);
});
test('both copies of an open article receive counts and public answers while comment inputs stay intact',()=>{
 const makeCard=id=>{const count={},comments={},list={innerHTML:''},classes={toggle(){}},btn={querySelector:()=>count,classList:classes};
  return {dataset:{newsId:id},count,comments,list,input:{value:'入力途中'},querySelector:s=>s.includes('toggleLike')?btn:s==='.btn-comment'?{querySelector:()=>comments}:list};};
 const cards=[makeCard('jp1'),makeCard('jp1'),makeCard('eu2')];
 const data={likes:4,commentCount:1,comments:[{id:5,text:'@Copilot 質問',canDelete:false,copilotAnswer:{status:'published',answer:'共有された回答'}}]};
 const ctx=vm.createContext({liveElements:{jp1:{lastData:data}},document:{querySelectorAll:()=>cards},window:{interactionsData:{jp1:{}}},updateLikeTooltip(){},mergeInteractionData(){},updateRankings(){},escapeHtml:String,formatCommentText:String});
 vm.runInContext(extract(client,'renderItem',''),ctx);ctx.renderItem('jp1');
 for(const card of cards.slice(0,2)){assert.equal(card.count.textContent,4);assert.equal(card.comments.textContent,1);assert.match(card.list.innerHTML,/共有された回答/);assert.equal(card.input.value,'入力途中');}
 assert.equal(cards[2].list.innerHTML,'');
});
test('settings only open existing edit/removal dialogs, without changing data',()=>{
 const menu={children:[],style:{},attributes:{},offsetWidth:200,offsetHeight:100,append(b){this.children.push(b)},replaceChildren(){this.children=[]},
  setAttribute(k,v){this.attributes[k]=v},addEventListener(){},matches(){return !!this.open},showPopover(){this.open=true},hidePopover(){this.open=false},get firstElementChild(){return this.children[0]}};
 let exists=false;const actions=[];
 const ctx=vm.createContext({innerWidth:390,innerHeight:700,document:{getElementById:()=>exists?menu:null,body:{append(){exists=true}},createElement:tag=>tag==='div'?menu:{focus(){}}},window:{requestImageUrlChange:id=>actions.push(['image',id]),requestArticleRemoval:id=>actions.push(['remove',id])}});
 vm.runInContext(extract(html,'toggleArticleSettings'),ctx);
 const trigger={setAttribute(){},getBoundingClientRect:()=>({left:350,bottom:690})};ctx.toggleArticleSettings('jp2298',trigger);
 assert.deepEqual(actions,[]);assert.equal(menu.style.left,'182px');assert.equal(menu.style.top,'592px');
 menu.children[0].onclick();assert.deepEqual(actions,[['image','jp2298']]);assert.equal(menu.open,false);
 ctx.toggleArticleSettings('jp2298',trigger);menu.children[1].onclick();assert.deepEqual(actions[1],['remove','jp2298']);
});
test('all inline scripts remain valid JavaScript',()=>{
 for(const match of html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g))new vm.Script(match[1]);
});
