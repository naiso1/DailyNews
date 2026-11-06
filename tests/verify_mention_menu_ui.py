"""Scroll all mention candidates in the real UI; API fixtures never send comments."""
import argparse
import functools
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import threading
from urllib.parse import unquote, urlparse
from playwright.sync_api import sync_playwright
from verify_ranking_comments_ui import Handler, IMAGE, ROOT

DAY='2026-11-05'
USERS=[{'displayName':f'候補{index:02d} テスト'} for index in range(70)]
NEWS=[dict(id='jp-mention-test',country='jp',date=DAY,issueDate=DAY,title='メンション候補のスクロール確認',
           desc='コメントの下書きを保持して、先頭と末尾の候補を選択できるか確認します。',tags=[],img=IMAGE,
           source='Fixture',url='https://example.invalid/article',isNew=True)]
INSIGHTS=[dict(date=DAY,analysis={'jp':'検証用の考察'},ideas={'jp':[dict(id=999999,title='企画アイデアの確認',desc='コメント欄も共通の候補を使用します。',img=IMAGE)]})]


def verify(browser,base,edition,width,out):
    context=browser.new_context(viewport={'width':width,'height':900},service_workers='block')
    writes=[]
    def intercept(route):
        req=route.request;parsed=urlparse(req.url);name=unquote(parsed.path).rsplit('/',1)[-1]
        if parsed.hostname!=urlparse(base).hostname:route.abort();return
        if '/api/' in parsed.path:
            if req.method!='GET':writes.append(req.url)
            api=parsed.path.split('/api/',1)[1]
            if api=='users/mentions':payload={'users':USERS}
            elif api=='interactions':payload={'interactions':{}}
            elif api.startswith('interactions/'):
                payload={'likes':0,'comments':0,'reads':0,'commentItems':[]}
            else:payload={'activity':[],'notifications':[],'unreadCount':0,'users':[],'seen':[],'favorites':[]}
            route.fulfill(json=payload)
        elif name=='news_data.js':route.fulfill(body='window.LOADED_NEWS_DATA='+json.dumps(NEWS)+';',content_type='application/javascript')
        elif name=='insights_data.js':route.fulfill(body='window.DAILY_INSIGHTS='+json.dumps(INSIGHTS)+';',content_type='application/javascript')
        elif name=='publication_status.js':route.fulfill(body='',content_type='application/javascript')
        elif name=='dailynews_account.js':route.fulfill(body="window.dailyNewsAccount={user:{id:'fixture'},ready:true};",content_type='application/javascript')
        else:
            assert req.method=='GET'
            route.continue_()
    context.route('**/*',intercept)
    page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(base.rstrip('/')+('/exterior/' if edition=='exterior' else '/')+'内装製品デイリーニュース.html?from='+DAY+'&to='+DAY+'&new=0',wait_until='domcontentloaded')
    page.wait_for_selector('#card-jp-mention-test')
    # Open the real release history after publication at both required widths.
    if not page.locator('#releaseHistoryOverlay.open').count():page.locator('#releaseHistoryButton').click()
    overlay=page.locator('#releaseHistoryOverlay.open');overlay.wait_for()
    assert page.evaluate('window.DAILYNEWS_RELEASE_HISTORY[0].date')=='2026-11-06'
    assert 'メンション候補をスクロールできるよう修正' in overlay.inner_text()
    if out:
        out.mkdir(parents=True,exist_ok=True)
        page.screenshot(path=str(out/f'history-{edition}-{width}.png'))
    overlay.locator('.release-history-confirm').click()
    for item in ('card-jp-mention-test','idea-card-999999'):
        card=page.locator('#'+item)
        card.locator('.btn-comment').click()
        editor=card.locator('.comment-input');editor.fill('下書きを保持 ')
        card.locator('.comment-mention-trigger').click()
        menu=card.locator('.comment-mention-menu.open')
        page.wait_for_function('(id)=>document.querySelectorAll(`#${id} .comment-mention-option`).length===70',arg=item)
        assert menu.evaluate('(el)=>el.scrollHeight>el.clientHeight && el.clientHeight<=300')
        bounds=menu.bounding_box();card_bounds=card.bounding_box()
        assert bounds['y']>=max(0,card_bounds['y'])-1,(bounds,card_bounds)
        await_scroll=lambda condition:page.wait_for_function('(args)=>{const el=document.querySelector(`#${args[0]} .comment-mention-menu`);return '+condition+'}',arg=[item])
        menu.hover();page.mouse.wheel(0,10000)
        await_scroll('el.scrollTop+el.clientHeight>=el.scrollHeight-2')
        last=menu.locator('.comment-mention-option').last
        last_bounds=last.bounding_box()
        assert last_bounds['y']>=bounds['y'] and last_bounds['y']+last_bounds['height']<=bounds['y']+bounds['height']+1
        if out:page.screenshot(path=str(out/f'menu-{edition}-{width}-{item}.png'))
        last.click()
        assert editor.input_value()=='下書きを保持 @候補69 テスト '
        card.locator('.comment-mention-trigger').click()
        menu.hover();page.mouse.wheel(0,-10000)
        await_scroll('el.scrollTop===0')
        menu.locator('.comment-mention-option').first.click()
        assert editor.input_value()=='下書きを保持 @候補69 テスト @候補00 テスト '
        editor.fill('下書き @候補35')
        page.wait_for_function('(id)=>document.querySelectorAll(`#${id} .comment-mention-option`).length===1',arg=item)
        menu.locator('.comment-mention-option').click()
        assert editor.input_value()=='下書き @候補35 テスト '
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        editor.fill('');card.locator('.btn-comment').click()
    assert not errors,errors
    assert not any(url.endswith('/comments') for url in writes),'No comments may be submitted by the test'
    print(f'PASS {edition} {width}px: 70 candidates, wheel to both ends, selection, filtering, draft preserved, history')
    context.close()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--base');parser.add_argument('--artifacts',type=Path);args=parser.parse_args()
    server=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(ROOT)))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='msedge',headless=True,args=['--no-proxy-server'])
            for edition in ('interior','exterior'):
                for width in (1440,390):verify(browser,args.base or f'http://127.0.0.1:{server.server_port}',edition,width,args.artifacts)
            browser.close()
    finally:server.shutdown()


if __name__=='__main__':main()
