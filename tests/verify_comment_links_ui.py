"""Render comments in the real UI with isolated API/data fixtures; no live writes."""
import argparse, functools, json, threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse
from playwright.sync_api import sync_playwright
from verify_ranking_comments_ui import Handler, IMAGE, ROOT

DAY='2026-10-19'
LONG='https://example.invalid/reference?name='+'long-value-'*30+'&mode=detail#section'
TEXT='参考動画：https://example.invalid/watch?v=example123&t=15。\n資料（https://example.invalid/material_(sample)）。\n'+LONG+'\n<img src=x onerror="window.commentInjected=true"> javascript:alert(1)'
NEWS=[dict(id='jp-link-test',country='jp',date=DAY,issueDate=DAY,title='コメントのリンク表示を確認',desc='URLのリンク・折り返し・入力欄の確認',tags=[],img=IMAGE,source='Fixture',url='https://example.invalid/article',isNew=True)]
INSIGHTS=[dict(date=DAY,analysis={'jp':'確認用の考察'},ideas={'jp':[dict(id=999999,title='企画アイデアのコメント',desc='同じリンク表示を使用',img=IMAGE)]})]

def verify(browser,base,edition,width,out,existing):
    context=browser.new_context(viewport={'width':width,'height':1000},service_workers='block')
    comments=[{'id':1,'user':'確認用','text':TEXT,'date':DAY,'likes':0,'canDelete':False},
              {'id':2,'user':'返信の確認','text':'https://example.invalid/reply?x=1&y=2','parentId':1,'date':DAY,'likes':0,'canDelete':False}]
    comments += [{'id':100+i,'user':'既存コメントの確認','text':r['comment_text'],'date':DAY,'likes':0,'canDelete':False} for i,r in enumerate(existing)]
    detail={'likes':0,'comments':len(comments),'reads':0,'commentItems':comments}
    writes=[]
    def intercept(route):
        req=route.request;parsed=urlparse(req.url);name=unquote(parsed.path).rsplit('/',1)[-1]
        if parsed.hostname=='example.invalid':route.fulfill(body='<title>Link destination fixture</title>');return
        if parsed.hostname!=urlparse(base).hostname:route.abort();return
        if '/api/' in parsed.path:
            if req.method!='GET':writes.append(req.url)
            api=parsed.path.split('/api/',1)[1]
            if api=='interactions':payload={'interactions':{'jp-link-test':detail,'999999':detail}}
            elif api.startswith('interactions/'):payload=detail
            else:payload={'activity':[],'notifications':[],'unreadCount':0,'users':[],'seenKeys':[],'favorites':[]}
            route.fulfill(json=payload)
        elif name=='news_data.js':route.fulfill(body='window.LOADED_NEWS_DATA='+json.dumps(NEWS)+';',content_type='application/javascript')
        elif name=='insights_data.js':route.fulfill(body='window.DAILY_INSIGHTS='+json.dumps(INSIGHTS)+';',content_type='application/javascript')
        elif name=='publication_status.js':route.fulfill(body='',content_type='application/javascript')
        elif name=='dailynews_account.js':route.fulfill(body="window.dailyNewsAccount={user:{id:'fixture'}};",content_type='application/javascript')
        else:
            assert req.method=='GET'
            route.continue_()
    context.route('**/*',intercept)
    page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    prefix=base.rstrip('/')+('/exterior/' if edition=='exterior' else '/')
    page.goto(prefix+'内装製品デイリーニュース.html?from='+DAY+'&to='+DAY+'&new=0',wait_until='domcontentloaded')
    page.wait_for_selector('#card-jp-link-test')
    if page.locator('#releaseHistoryOverlay.open').count():page.locator('#releaseHistoryOverlay .release-history-confirm').click()
    for item in ('card-jp-link-test','idea-card-999999'):
        card=page.locator('#'+item);card.locator('.btn-comment').click()
        page.wait_for_function('(id)=>document.querySelectorAll(`#${id} .comment-url`).length>=4',arg=item)
        primary=card.locator('[data-comment-id="1"] .comment-text')
        links=primary.locator('a')
        assert links.count()==3
        assert links.nth(0).get_attribute('href')=='https://example.invalid/watch?v=example123&t=15'
        assert links.nth(1).get_attribute('href')=='https://example.invalid/material_(sample)'
        assert links.nth(2).get_attribute('href')==LONG
        assert primary.inner_text()==TEXT.replace('\n',' '),repr(primary.inner_text())
        assert primary.locator('img,script,[onerror]').count()==0
        assert not page.evaluate('Boolean(window.commentInjected)')
        for link in links.all():
            assert link.get_attribute('target')=='_blank'
            assert set(link.get_attribute('rel').split())=={'noopener','noreferrer'}
        assert card.locator('.reply-comment .comment-url').count()==1
        editor=card.locator('.comment-input');editor.fill('入力中のコメントは保持する')
        original_url=page.url
        with context.expect_page() as opened:links.nth(0).click()
        popup=opened.value;popup.wait_for_url('https://example.invalid/watch?v=example123&t=15',wait_until='domcontentloaded')
        assert popup.url=='https://example.invalid/watch?v=example123&t=15'
        popup.close()
        assert page.url==original_url and editor.input_value()=='入力中のコメントは保持する'
        assert card.locator('.comment-section.open').count()==1
        assert primary.evaluate('(el)=>el.scrollWidth<=el.clientWidth')
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        if out:
            out.mkdir(parents=True,exist_ok=True);card.screenshot(path=str(out/f'{edition}-{width}-{item}.png'))
        editor.fill('');card.locator('.btn-comment').click()
    assert not errors,errors
    assert not any(url.endswith('/comments') for url in writes),'A real comment must never be submitted by this test'
    if existing:
        assert any('www.youtube.com' in a.get_attribute('href') for a in page.locator('.comment-url').all())
    print(f'PASS {edition} {width}px: existing comments/replies, escaped HTML, new tab, draft retained, long URLs wrap.')
    context.close()

def main():
    p=argparse.ArgumentParser();p.add_argument('--base');p.add_argument('--artifacts',type=Path);p.add_argument('--existing-comments',type=Path);args=p.parse_args()
    existing=json.loads(args.existing_comments.read_text(encoding='utf8')) if args.existing_comments else []
    server=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(ROOT)))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='msedge',headless=True)
            for edition in ('interior','exterior'):
                for width in (1440,390):verify(browser,args.base or f'http://127.0.0.1:{server.server_port}',edition,width,args.artifacts,existing)
            browser.close()
    finally:server.shutdown()

if __name__=='__main__':main()
