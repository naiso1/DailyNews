"""Isolated browser checks for member edits and in-card image navigation."""
import json, os, shutil, subprocess, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'runtime/image-carousel-ui'

def test_edition(browser, edition, port):
    root=OUTPUT/edition;release=root/'releases/abcdef3'
    release.mkdir(parents=True,exist_ok=True);(root/'active-release.txt').write_text('abcdef3')
    for name in ('dailynews_client.js','dailynews_account.js','dailynews_reports.js','dailynews_annotations.js','exchange_rates.js','release_history.js','dailynews_config.js','dailynews_activity.js','dailynews_sources.js','dailynews_exterior_tags.js','source_list_data.js'):
        shutil.copy2(ROOT/name,release/name)
    shutil.copy2(ROOT/'内装製品デイリーニュース.html',release/'index.html')
    base=f'http://127.0.0.1:{port}';site=base+('/exterior' if edition=='exterior' else '')
    urls=[site+f'/image-{n}.svg' for n in range(5)]
    for n,color in enumerate(('#2375af','#178274','#7957ad','#b65e36','#486475')):
        (release/f'image-{n}.svg').write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="800" height="450"><rect width="800" height="450" fill="{color}"/><text x="370" y="260" font-size="90" fill="white">{n+1}</text></svg>')
    items=[{'id':f'jp{n}','title':'自動車の製品画像を確認','desc':'カード内の画像切り替えを確認します。','summary':'コメント入力を保持する確認です。','country':'jp','date':'2026-10-13','img':urls[0],'images':images,'tags':['テスト'],'source':'UI fixture','url':'https://example.com/article','interiorScore':95,'exteriorScore':95} for n,images in [(1,urls[:2]),(2,urls[:1]),(3,[urls[0],site+'/missing.svg',urls[1]])]]
    (release/'news_data.js').write_text('window.LOADED_NEWS_DATA='+json.dumps(items,ensure_ascii=False)+';window.NEWS_DATA=window.LOADED_NEWS_DATA;',encoding='utf8')
    (release/'insights_data.js').write_text('window.DAILY_INSIGHTS=[];',encoding='utf8')
    env={**os.environ,'DAILYNEWS_ROOT':str(root),'DAILYNEWS_EDITION':edition,'DAILYNEWS_HOST':'127.0.0.1','DAILYNEWS_PORT':str(port),'DAILYNEWS_ALLOWED_CLIENTS':'127.0.0.1,::1','DAILYNEWS_ADMIN_EMAILS':'admin@example.com','DAILYNEWS_IDENTITY_DB':'','DAILYNEWS_EXTERIOR_DB':''}
    process=subprocess.Popen(['node',str(ROOT/'deployment/windows-server/server.js')],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        time.sleep(1)
        context=browser.new_context(viewport={'width':1440,'height':1050})
        response=context.request.post(site+'/api/auth/register',data={'email':'reader@example.com','displayName':'Reader','password':'fixture-password-123'},headers={'Origin':base})
        if response.status==409:context.request.post(site+'/api/auth/login',data={'email':'reader@example.com','password':'fixture-password-123'},headers={'Origin':base})
        # Make repeated test runs start from the article's original image list.
        assert context.request.delete(site+'/api/items/jp1/image',headers={'Origin':base}).status==200
        page=context.new_page()
        page.on('pageerror',lambda error:print(f'{edition} page error: {error}',flush=True))
        page.goto(site+'/?from=2026-10-13&to=2026-10-13');page.wait_for_selector('#card-jp1')
        page.wait_for_function('window.dailyNewsAccount?.user && !window.dailyNewsAccount.user.isAdmin')
        # Acknowledge the normal system notice before exercising article controls.
        page.locator('#releaseHistoryButton').evaluate('(button)=>button.click()')
        page.locator('#releaseHistoryOverlay.open .release-history-close').click()
        page.wait_for_timeout(500)
        card=page.locator('#card-jp1'); image=card.locator('.thumb > img'); dots=card.locator('.news-image-dot')
        assert dots.count()==2 and page.locator('#card-jp2 .news-image-dots').count()==0
        assert card.locator('.content').get_by_text('画像 2枚を見る',exact=True).count()==0
        height=card.locator('.thumb').bounding_box()['height']
        offset=card.locator('.title').evaluate('(el)=>el.offsetTop')
        card.locator('.image-edit-btn').click();page.locator('#imageEditorUrl').fill('\n'.join(urls))
        page.locator('.image-editor-save').click();page.wait_for_selector('#imageUrlEditorOverlay.open',state='hidden')
        page.wait_for_function("document.querySelectorAll('#card-jp1 .news-image-dot').length===5")
        assert context.request.get(site+'/api/interactions/jp1').json()['imageUrlsOverride']==urls
        assert abs(card.locator('.thumb').bounding_box()['height']-height)<1
        assert card.locator('.title').evaluate('(el)=>el.offsetTop')==offset
        selected=lambda:card.locator('.news-image-dot[aria-pressed="true"]').get_attribute('title')
        page.mouse.move(0,0);page.clock.install()
        page.clock.run_for(6100);assert selected()=='1 / 5枚','No hover must not advance'
        card.locator('.title').hover();page.clock.run_for(3100);assert selected()=='2 / 5枚'
        page.clock.run_for(3000);assert selected()=='3 / 5枚'
        page.mouse.move(0,0);page.clock.run_for(6100);assert selected()=='3 / 5枚','Leave must stop'
        dots.nth(4).click();assert selected()=='5 / 5枚'
        page.clock.run_for(3100);assert selected()=='1 / 5枚','Wrap to first image'
        dots.nth(1).focus();dots.nth(1).press('End');assert selected()=='5 / 5枚'
        dots.nth(4).press('ArrowRight');assert selected()=='1 / 5枚'
        card.locator('.btn-comment').click();field=card.locator('.comment-input');field.fill('入力中のコメントを保持')
        card.locator('.title').hover();page.clock.run_for(6100)
        assert selected()=='1 / 5枚' and field.input_value()=='入力中のコメントを保持'
        page.mouse.click(2,2);card.locator('.btn-comment').click()
        page.emulate_media(reduced_motion='reduce');card.locator('.title').hover();page.clock.run_for(6100)
        assert selected()=='1 / 5枚';page.emulate_media(reduced_motion='no-preference')
        page.evaluate("window.dispatchEvent(new Event('blur'))");page.clock.run_for(6100);assert selected()=='1 / 5枚'
        page.evaluate("window.dispatchEvent(new Event('focus'))");page.clock.run_for(3100);assert selected()=='2 / 5枚'
        page.mouse.move(0,0)
        dots.nth(3).click();page.mouse.move(0,0)
        page.evaluate("window.__oldCard=document.querySelector('#card-jp1');window.__oldSrc=window.__oldCard.querySelector('.thumb img').src;applyFilters()")
        assert selected()=='4 / 5枚','Keep chosen image across card refresh'
        page.clock.run_for(6100)
        assert page.evaluate("!window.__oldCard.isConnected && window.__oldCard.querySelector('.thumb img').src===window.__oldSrc")
        broken=page.locator('#card-jp3');broken.locator('.news-image-dot').nth(1).click()
        page.wait_for_function("document.querySelector('#card-jp3 .thumb img').dataset.failed==='1'")
        broken.locator('.news-image-dot').nth(2).click()
        page.wait_for_function("document.querySelector('#card-jp3 .thumb img').naturalWidth>0 && !document.querySelector('#card-jp3 .thumb img').dataset.failed")
        assert broken.locator('.thumb > img').get_attribute('src')==urls[1]
        for label,width,height in [('desktop',1440,1050),('mobile',390,844)]:
            page.set_viewport_size({'width':width,'height':height});card.scroll_into_view_if_needed();card.screenshot(path=str(OUTPUT/f'{edition}-{label}.png'))
            bounds=card.locator('.thumb').bounding_box();dot_bounds=card.locator('.news-image-dots').bounding_box()
            assert dot_bounds['y']>=bounds['y'] and dot_bounds['y']+dot_bounds['height']<=bounds['y']+bounds['height']
        # A touch pointer never starts automatic rotation; tapping dots still works.
        touch=browser.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True,storage_state=context.storage_state())
        tp=touch.new_page();tp.goto(site+'/?from=2026-10-13&to=2026-10-13');tp.wait_for_selector('#card-jp1 .news-image-dot')
        tp.locator('#releaseHistoryButton').evaluate('(button)=>button.click()')
        tp.locator('#releaseHistoryOverlay.open .release-history-close').click()
        tp.clock.install();tp.locator('#card-jp1 .news-image-dot').nth(2).tap();tp.clock.run_for(6100)
        assert tp.locator('#card-jp1 .news-image-dot[aria-pressed="true"]').get_attribute('title')=='3 / 5枚'
        touch.close();context.close()
        print(f'{edition}: member editor, in-image dots, stable layout, 3s hover, pause, keyboard/touch, refresh disposal and broken-image recovery PASS')
    finally:process.terminate();process.wait(timeout=10)

if __name__=='__main__':
    OUTPUT.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='msedge',headless=True)
        try:
            for edition,port in [('interior',18953),('exterior',18954)]:
                if len(sys.argv)==1 or edition in sys.argv[1:]:test_edition(browser,edition,port)
        finally:browser.close()
