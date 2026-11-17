"""Real shared page and scripts; fixture accounts/provider/comments, no live writes."""
import argparse
import functools
import json
from http.server import ThreadingHTTPServer
from pathlib import Path
import threading
from urllib.parse import unquote, urlparse
from playwright.sync_api import sync_playwright
from verify_ranking_comments_ui import Handler, IMAGE, ROOT

DAY = '2026-11-17'
NEWS = [dict(id='jp1', country='jp', date=DAY, title='光の演出を広げるアンビエント照明',
             desc='ドアとインパネの照明を連動させる内装技術の検討。', tags=['イルミ'], img=IMAGE,
             source='表示確認用の記事', url='https://example.invalid/jp1')]

def verify(browser, base, edition, width, out):
    ctx = browser.new_context(viewport={'width': width, 'height': 1000}, service_workers='block')
    interactions = {'likes':0, 'comments':0, 'reads':0, 'commentItems':[]}
    writes=[]; questions=[]; errors=[]; fail_comment=False; jobs={}; connected=True
    def intercept(route):
        nonlocal interactions
        req=route.request; parsed=urlparse(req.url); path=unquote(parsed.path).removeprefix('/exterior'); name=path.rsplit('/',1)[-1]
        if parsed.hostname!=urlparse(base).hostname: route.abort(); return
        if '/api/' in path:
            api=path.split('/api/',1)[1]; data={}
            if req.method!='GET': writes.append((api,req.post_data_json))
            if api=='copilot/account': data={'connected':connected,'email':'fixture@example.invalid'}
            elif api=='copilot/current': data={'job':None}
            elif api in ('copilot/jobs','copilot/questions'):
                body=req.post_data_json; questions.append(body); job_id=str(len(questions)).zfill(64)
                j={'id':job_id,'status':'done','answer':'光の統合制御と体験価値の両立に注目です。内装イルミへの適用は検証が必要です。[jp1]', 'createdAt':'2026-11-18T00:00:00Z','completedAt':'2026-11-18T00:00:01Z'}
                if api.endswith('questions'):
                    j.update(question=body['question'],scope=body['scope'],context={'scope':body['scope'],'total':47,'used':1,'dateFrom':DAY,'dateTo':DAY},sources=[{'id':'jp1','title':NEWS[0]['title'],'url':NEWS[0]['url']}])
                jobs[job_id]=j; data={'job':j}
            elif api.startswith('copilot/jobs/'): data={'job':jobs[api.rsplit('/',1)[-1]]}
            elif api=='interactions': data={'interactions':{'jp1':interactions}}
            elif api.startswith('interactions/jp1'):
                if req.method=='POST' and api.endswith('/comments'):
                    if fail_comment: route.fulfill(status=503,json={'error':{'message':'fixture failure'}}); return
                    ident=interactions['comments']+1
                    interactions={**interactions,'comments':ident,'commentItems':[*interactions['commentItems'],{'id':ident,'user':'検証ユーザー','userId':1,'text':req.post_data_json['text'],'likes':0}]}
                    data={**interactions,'createdCommentId':ident}
                else: data=interactions
            elif api=='users/mentions': data={'users':[{'displayName':'三輪 朋弘'}]}
            else: data={'activity':[],'notifications':[],'unreadCount':0,'users':[],'seen':[],'favorites':[]}
            route.fulfill(json=data); return
        if name=='news_data.js': body='window.LOADED_NEWS_DATA='+json.dumps(NEWS)+';'
        elif name=='insights_data.js': body='window.DAILY_INSIGHTS=[];'
        elif name=='publication_status.js': body='window.EXTERIOR_PUBLICATION_STATUS='+json.dumps({'issue_date':DAY,'target_dates':[DAY],'selected_news_ids':['jp1'],'status':'published'})+';'
        elif name=='dailynews_account.js': body="window.dailyNewsAccount={user:{id:1,email:'fixture@example.invalid'},ready:true,openAuth:()=>{}};"
        else: route.continue_(); return
        route.fulfill(body=body,content_type='application/javascript')
    ctx.route('**/*',intercept)
    page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.on('dialog',lambda d:d.accept())
    page.goto(base+('/exterior' if edition=='exterior' else '')+'/内装製品デイリーニュース.html?from='+DAY+'&to='+DAY+'&new=0',wait_until='domcontentloaded')
    page.locator('#card-jp1').wait_for()
    if page.locator('#releaseHistoryOverlay.open').count(): page.locator('.release-history-close').click()
    page.locator('#copilotNewsButton').click(); dialog=page.locator('.copilot-news-dialog')
    dialog.locator('.copilot-examples button').first.click()
    dialog.get_by_role('button',name='質問する',exact=True).click()
    dialog.locator('.copilot-reply').wait_for(state='visible')
    assert questions[-1]=={'scope':'new','question':'今日のニュースで私に関係するニュースをピックアップして'}
    assert '47件から1件' in dialog.inner_text(); assert dialog.locator('.copilot-reply p a').get_attribute('href')==NEWS[0]['url']
    dialog.locator('.copilot-examples button').last.click(); dialog.get_by_role('button',name='質問する',exact=True).click()
    page.wait_for_function("document.querySelector('.copilot-reply small').textContent.includes('トレンド')")
    assert questions[-1]['scope']=='all'; assert not any('/comments' in w[0] for w in writes)
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    out.mkdir(parents=True,exist_ok=True);dialog.screenshot(path=str(out/f'news-question-{edition}-{width}.png'))
    dialog.locator('header button').click(); page.locator('#copilotNewsButton').click()
    assert 'トレンド' in page.locator('.copilot-news-dialog .copilot-reply').inner_text()
    page.locator('.copilot-news-dialog header button').click()
    card=page.locator('#card-jp1');card.locator('.btn-comment').click();input=card.locator('.comment-input')
    card.locator('.comment-mention-trigger').click();menu=card.locator('.comment-mention-menu.open')
    assert menu.locator('.comment-mention-option').first.inner_text()=='@Copilotに質問'
    menu.locator('.comment-mention-option').first.click();assert input.input_value()=='@Copilot '
    input.fill('@Copilot この技術を内装イルミに使える？')
    assert card.locator('.copilot-mention-hint').is_visible()
    before=len(questions)
    input.evaluate("el=>el.dispatchEvent(new KeyboardEvent('keypress',{key:'Enter',isComposing:true,bubbles:true}))")
    assert len(questions)==before
    card.screenshot(path=str(out/f'mention-input-{edition}-{width}.png'))
    card.locator('.comment-submit').evaluate('(el)=>{el.click();el.click();}')
    page.wait_for_function("document.querySelector('#card-jp1 .comment-item .copilot-reply')?.textContent.includes('光の統合')")
    assert interactions['comments']==1; assert len(questions)==before+1;assert questions[-1]=={'itemId':'jp1','commentId':1}
    assert input.input_value()==''
    card.screenshot(path=str(out/f'mention-answer-{edition}-{width}.png'))
    # A failed comment preserves its draft and never sends a provider question.
    fail_comment=True;input.fill('@Copilot 失敗時の確認');before=len(questions)
    input.evaluate("el=>el.scrollIntoView({block:'center'})")
    card.locator('.comment-submit').click();page.wait_for_timeout(300)
    assert len(questions)==before;assert input.input_value()=='@Copilot 失敗時の確認'
    fail_comment=False;input.fill('通常のコメント');input.evaluate("el=>el.scrollIntoView({block:'center'})");card.locator('.comment-submit').click();page.wait_for_timeout(300)
    assert len(questions)==before and interactions['comments']==2
    # Changing the account must remove private answers, including the global dialog.
    page.locator('#copilotNewsButton').click()
    page.evaluate("window.dailyNewsAccount.user={id:2,email:'other@example.invalid'};window.dispatchEvent(new Event('dailynews:account-changed'))")
    page.locator('.copilot-dialog').wait_for(state='detached')
    page.locator('#copilotNewsButton').click();assert page.locator('.copilot-news-dialog .copilot-reply').is_hidden()
    page.locator('.copilot-news-dialog header button').click()
    page.locator('#releaseHistoryButton').click();history=page.locator('#releaseHistoryOverlay')
    assert '2026-11-18' in history.inner_text() and '@Copilotで質問・ニュース全体を相談' in history.inner_text()
    history.screenshot(path=str(out/f'history-{edition}-{width}.png'))
    assert not errors,errors
    print(f'PASS {edition} {width}px: NEW/all, cited links, public mention once, failed post no question, IME, private-account reset, history')
    ctx.close()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--base');parser.add_argument('--artifacts',type=Path,default=ROOT/'artifacts/copilot-questions-20261118');args=parser.parse_args()
    server=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(ROOT)))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='msedge',headless=True,args=['--no-proxy-server'])
            for edition in ('interior','exterior'):
                for width in (1440,390):verify(browser,args.base or f'http://127.0.0.1:{server.server_port}',edition,width,args.artifacts)
            browser.close()
    finally: server.shutdown()
if __name__=='__main__': main()
