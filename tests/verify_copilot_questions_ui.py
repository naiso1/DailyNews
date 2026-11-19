"""Real shared page and scripts; fixture accounts/provider/comments, no live writes."""
import argparse
import functools
import json
from http.server import ThreadingHTTPServer
from pathlib import Path
import threading
from urllib.parse import parse_qs, unquote, urlparse
from playwright.sync_api import sync_playwright
from verify_ranking_comments_ui import Handler, IMAGE, ROOT

DAY = '2026-11-17'
NEWS = [dict(id='jp1', country='jp', date=DAY, title='光の演出を広げるアンビエント照明',
             desc='ドアとインパネの照明を連動させる内装技術の検討。', tags=['イルミ'], img=IMAGE,
             source='表示確認用の記事', url='https://example.invalid/jp1'),
        dict(id='jp2', country='jp', date='2026-10-01', title='過去の車室内照明の記事',
             desc='表示期間外の記事もDailyNews内で開けることを確認。', tags=['イルミ'], img=IMAGE,
             source='表示確認用の記事', url='https://example.invalid/broken')]

class PageHandler(Handler):
    def translate_path(self, path):
        if urlparse(path).path in ('/', '/exterior/'):
            path='/内装製品デイリーニュース.html'
        return super().translate_path(path)

def verify(browser, base, edition, width, out):
    height=780 if width<500 else 1000
    ctx = browser.new_context(viewport={'width': width, 'height': height}, service_workers='block')
    interactions = {'likes':0, 'comments':0, 'reads':0, 'commentItems':[]}
    writes=[]; questions=[]; errors=[]; fail_comment=False; jobs={}; connected=True;account_failure=''
    def intercept(route):
        nonlocal interactions,account_failure
        req=route.request; parsed=urlparse(req.url); path=unquote(parsed.path).removeprefix('/exterior'); name=path.rsplit('/',1)[-1]
        if parsed.hostname!=urlparse(base).hostname: route.abort(); return
        if '/api/' in path:
            api=path.split('/api/',1)[1]; data={}
            if req.method!='GET': writes.append((api,req.post_data_json))
            if api=='copilot/account':
                if account_failure=='once-html':
                    account_failure='';route.fulfill(status=502,body='<html>Gateway error</html>',content_type='text/html');return
                if account_failure=='html': route.fulfill(status=502,body='<html>Gateway error</html>',content_type='text/html');return
                if account_failure=='network': route.abort('connectionfailed');return
                data={'connected':connected,'email':'fixture@example.invalid'}
            elif api=='copilot/current': data={'job':None}
            elif api in ('copilot/jobs','copilot/questions'):
                body=req.post_data_json; questions.append(body); job_id=str(len(questions)).zfill(64)
                j={'id':job_id,'status':'done','answer':'光の統合制御と体験価値の両立に注目です。内装イルミへの適用は検証が必要です。[jp1]', 'createdAt':'2026-11-18T00:00:00Z','completedAt':'2026-11-18T00:00:01Z'}
                if api.endswith('questions'):
                    j.update(question=body['question'],scope=body['scope'],context={'scope':body['scope'],'total':47,'used':1,'dateFrom':DAY,'dateTo':DAY},sources=[{'id':'jp1','title':NEWS[0]['title'],'url':NEWS[0]['url']}])
                    if body['scope']=='all':
                        j['answer']+='過去の照明事例も参照できます。[jp2] 未確認のID [jp999]'
                        j['context'].update(used=2,dateFrom=NEWS[1]['date'])
                        # Link by article ID even if the old provider record has no external URL.
                        j['sources'].append({'id':'jp2','title':NEWS[1]['title']})
                if len(questions)==1: j.update(status='needs_review',sendAttemptCount=1)
                jobs[job_id]=j; data={'job':j}
            elif api.startswith('copilot/jobs/') and api.endswith('/retry'):
                job_id=api.split('/')[-2];j=jobs[job_id]
                assert req.post_data_json=={'createdAt':j['createdAt']}
                j.update(status='done');data={'job':j}
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
    # Keep covering the supported classic fallback after the companion becomes default.
    page.goto(base+('/exterior' if edition=='exterior' else '')+'/内装製品デイリーニュース.html?copilot=classic&from='+DAY+'&to='+DAY+'&new=0',wait_until='domcontentloaded')
    page.locator('#card-jp1').wait_for()
    assert page.locator('#card-jp2').count()==0
    if page.locator('#releaseHistoryOverlay.open').count(): page.locator('.release-history-close').click()
    page.locator('#copilotNewsButton').click(); dialog=page.locator('.copilot-news-dialog')
    dialog.locator('.copilot-examples button').first.click()
    dialog.get_by_role('button',name='質問する',exact=True).click()
    dialog.locator('.copilot-reply').wait_for(state='visible')
    assert questions[-1]=={'scope':'new','question':'今日のニュースで私に関係するニュースをピックアップして'}
    assert not any(w[0].endswith('/retry') for w in writes)
    dialog.get_by_role('button',name='確認して再試行',exact=True).click()
    confirm=page.get_by_role('dialog',name='Copilotへの再試行',exact=True)
    confirm.locator('header button').click();confirm.wait_for(state='detached')
    assert not any(w[0].endswith('/retry') for w in writes)
    dialog.get_by_role('button',name='確認して再試行',exact=True).click()
    confirm=page.get_by_role('dialog',name='Copilotへの再試行',exact=True)
    confirm.get_by_role('button',name='1回だけ再送する',exact=True).evaluate('(el)=>{el.click();el.click();}')
    page.wait_for_function("document.querySelector('.copilot-news-dialog .copilot-reply p')?.textContent.includes('光の統合')")
    assert len([w for w in writes if w[0].endswith('/retry')])==1
    assert '47件から1件' in dialog.inner_text()
    href=dialog.locator('.copilot-reply p a').get_attribute('href')
    assert urlparse(href).path==('/exterior/' if edition=='exterior' else '/')
    assert parse_qs(urlparse(href).query,keep_blank_values=True)=={'q':['jp1'],'from':[''],'to':[''],'new':['0']}
    dialog.locator('.copilot-examples button').last.click(); dialog.get_by_role('button',name='質問する',exact=True).click()
    page.wait_for_function("document.querySelector('.copilot-reply small').textContent.includes('トレンド')")
    assert questions[-1]['scope']=='all'; assert not any('/comments' in w[0] for w in writes)
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    rect=dialog.bounding_box()
    assert abs(rect['x']+rect['width']/2-width/2)<2,rect
    assert abs(rect['y']+rect['height']/2-height/2)<2,rect
    assert rect['y']>=0 and rect['height']<=height*.94+1,rect
    assert '全記事の本文は送りません' in dialog.inner_text()
    assert dialog.locator('.copilot-reply p a').count()==2
    if width<500:
        dialog.evaluate('(el)=>{el.scrollTop=el.scrollHeight;}')
        close_rect=dialog.locator('header button').bounding_box()
        assert close_rect['y']>=rect['y'] and close_rect['y']+close_rect['height']<=rect['y']+rect['height']
    out.mkdir(parents=True,exist_ok=True)
    page.screenshot(path=str(out/f'news-question-{edition}-{width}.png'))
    # Both citation and list use a reloadable link to this edition, never the source website.
    old_link=dialog.locator('.copilot-reply p a').last
    old_href=old_link.evaluate('(a)=>a.href')
    dialog.locator('.copilot-reply summary').click()
    assert dialog.locator('.copilot-reply li a').last.evaluate('(a)=>a.href')==old_href
    before=len(questions)
    old_link.click();dialog.wait_for(state='detached')
    page.locator('#card-jp2').wait_for()
    assert page.locator('#card-jp1').count()==0
    assert page.locator('#dateFrom').input_value()=='' and page.locator('#dateTo').input_value()==''
    assert len(questions)==before
    page.go_back();page.locator('#card-jp1').wait_for()
    assert page.locator('#card-jp2').count()==0
    # New-tab/reload fallback also removes date filters and respects the edition path.
    linked=ctx.new_page();linked.goto(old_href,wait_until='domcontentloaded')
    linked.locator('#card-jp2').wait_for();assert linked.locator('#card-jp1').count()==0
    assert linked.evaluate('window.DAILYNEWS_CONFIG.id')==edition
    linked.close();assert len(questions)==before
    page.locator('#copilotNewsButton').click();dialog=page.locator('.copilot-news-dialog')
    # Infrastructure failures must not look like article selection or sign-in errors.
    before=len(questions)
    for failure,message in [('html','DailyNewsサーバーの応答'),('network','DailyNewsとの通信')]:
        account_failure=failure
        dialog.get_by_role('button',name='質問する',exact=True).click()
        page.wait_for_function('(text)=>document.querySelector(".copilot-news-dialog .copilot-reply p")?.textContent.includes(text)',arg=message)
        assert len(questions)==before
    account_failure=''
    # One read-only reconnect may recover a transient 502; submit the question once.
    account_failure='once-html'
    dialog.get_by_role('button',name='質問する',exact=True).click()
    page.wait_for_function('()=>!document.querySelector(".copilot-news-dialog .copilot-question").disabled')
    assert account_failure=='' and len(questions)==before+1
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
    assert '2026-11-18' in history.inner_text() and 'Copilotの質問画面を中央に配置' in history.inner_text()
    history.screenshot(path=str(out/f'history-{edition}-{width}.png'))
    assert not errors,errors
    print(f'PASS {edition} {width}px: centered/scrollable dialog, internal archive links/back/reload, scope explanation, NEW/all, public mention once, private-account reset, history')
    ctx.close()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--base');parser.add_argument('--artifacts',type=Path,default=ROOT/'artifacts/copilot-questions-20261118');args=parser.parse_args()
    server=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(PageHandler,directory=str(ROOT)))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='msedge',headless=True,args=['--no-proxy-server'])
            for edition in ('interior','exterior'):
                for width in (1440,390):verify(browser,args.base or f'http://127.0.0.1:{server.server_port}',edition,width,args.artifacts)
            browser.close()
    finally: server.shutdown()
if __name__=='__main__': main()
