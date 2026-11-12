"""Shared real UI with fixture APIs/CDNs; no production writes or image storage."""
import json
import mimetypes
from pathlib import Path
from urllib.parse import unquote, urlparse, parse_qs
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts/image-url-sizing-20261112'
DAY = '2026-11-11'
HEARST = 'https://hips.hearstapps.com/hmg-prod/images/'
URLS = [HEARST+'first.jpg',
        'https://static0.topspeedimages.com/wordpress/wp-content/uploads/test.jpg?w=1600&h=900&fit=crop',
        'https://static0.carbuzzimages.com/wordpress/wp-content/uploads/test.jpg',
        'https://prcdn.freetls.fastly.net/release_image/1/2/test.jpg?width=2400&height=1260&fit=bounds',
        'https://unknown.example/photo.jpg', HEARST+'retry.jpg', HEARST+'missing.jpg',
        HEARST+'signed.jpg?Signature=fixture']
NEWS = [dict(id=f'jp{i}', country='jp', date=DAY, digestDate=DAY, title=f'画像表示の検証 {i}',
             desc='記事画像の表示確認', tags=[], img=url, source='Fixture',
             interiorScore=95, url='https://example.invalid/article') for i, url in enumerate(URLS, 1)]
IDEAS = [dict(date=DAY, analysis={'jp': '元画像の参照を確認 [jp1]'}, ideas={'jp': [
    dict(id=999999, title='検証用アイデア', desc='参照画像 [jp1] [jp6]', sourceNewsIds=['jp1', 'jp6'])]})]


def verify(browser, edition, width):
    context = browser.new_context(viewport={'width': width, 'height': 1000},
                                  service_workers='block', reduced_motion='reduce')
    seen, errors, writes = [], [], []
    def route(r):
        parsed = urlparse(r.request.url)
        if parsed.hostname != 'dailynews.test':
            seen.append(r.request.url)
            if 'missing.jpg' in parsed.path or ('retry.jpg' in parsed.path and 'resize' in parse_qs(parsed.query)):
                r.fulfill(status=404); return
            if parsed.hostname not in ['hips.hearstapps.com', 'static0.topspeedimages.com',
                                       'static0.carbuzzimages.com', 'prcdn.freetls.fastly.net', 'unknown.example']:
                r.abort(); return
            r.fulfill(body='<svg xmlns="http://www.w3.org/2000/svg" width="980" height="653"><rect width="980" height="653" fill="#276b85"/></svg>', content_type='image/svg+xml'); return
        path = unquote(parsed.path).removeprefix('/exterior').lstrip('/')
        if path.startswith('api/'):
            if r.request.method != 'GET': writes.append((r.request.method, path))
            detail = dict(likes=2, comments=0, reads=1, liked=False, imageUrlsOverride=[URLS[0], HEARST+'second.jpg'])
            if path == 'api/interactions': r.fulfill(json={'interactions': {'jp1': detail}})
            elif path.startswith('api/interactions/'): r.fulfill(json=detail if path.split('/')[2]=='jp1' else {'likes': 0, 'comments': []})
            else: r.fulfill(json={'total': 0, 'daily': {}, 'activity': [], 'users': [], 'notifications': [], 'unreadCount': 0, 'seenKeys': []})
            return
        scripts = {'news_data.js': 'window.LOADED_NEWS_DATA='+json.dumps(NEWS)+';',
                   'insights_data.js': 'window.DAILY_INSIGHTS='+json.dumps(IDEAS)+';',
                   'dailynews_account.js': "window.dailyNewsAccount={user:{id:'fixture'}};", 'release_history.js': ''}
        if path in scripts: r.fulfill(body=scripts[path], content_type='application/javascript'); return
        if path == 'publication_status.json':
            r.fulfill(json={'edition_id':'exterior', 'status':'published', 'processed_through':DAY, 'target_dates':[DAY], 'selected_count':len(NEWS)}); return
        file = ROOT/(path or '内装製品デイリーニュース.html')
        if not file.resolve().is_relative_to(ROOT) or not file.is_file(): r.fulfill(status=404); return
        r.fulfill(body=file.read_bytes(), content_type=mimetypes.guess_type(file.name)[0] or 'application/octet-stream')
    context.route('**/*', route)
    page = context.new_page()
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto('http://dailynews.test/'+('exterior/' if edition=='exterior' else '')+f'?from={DAY}&to={DAY}&new=0', wait_until='domcontentloaded')
    page.wait_for_function("window.firebaseInteractionsReady && document.querySelectorAll('#card-jp1 .news-image-dot').length===2")
    for i, original in enumerate(URLS, 1):
        card = page.locator(f'#card-jp{i}'); card.scroll_into_view_if_needed()
        image = card.locator('.thumb > img')
        page.wait_for_function('(id)=>document.querySelector(id).complete && document.querySelector(id).naturalWidth>0', arg=f'#card-jp{i} .thumb > img')
        assert image.get_attribute('data-original-src') == original
        current = image.get_attribute('src')
        if i in [1,2,3,4]:
            assert urlparse(current).hostname == urlparse(original).hostname
            params = parse_qs(urlparse(current).query)
            assert params.get('resize', params.get('w', params.get('width'))) in [['980:*'], ['980']]
        elif i in [5,6,8]: assert current == original, (i, current)
        else: assert 'thumb_default' in current or current.startswith('data:'), current
    # Bounded fallback, then normal placeholder; another slide starts afresh.
    assert any('retry.jpg?' in u for u in seen) and HEARST+'retry.jpg' in seen
    assert page.locator('#card-jp6 .thumb img').get_attribute('data-original-retried') == '1'
    assert page.locator('#card-jp7 .thumb img').get_attribute('data-failed') == '1'
    card = page.locator('#card-jp1'); image = card.locator('.thumb > img')
    card.locator('.news-image-dot').nth(1).click()
    assert image.get_attribute('data-original-src') == HEARST+'second.jpg'
    assert parse_qs(urlparse(image.get_attribute('src')).query)['resize'] == ['980:*']
    card.locator('.btn-comment').click(); card.locator('.comment-input').fill('入力途中を保持')
    card.locator('.news-image-dot').nth(0).click()
    assert card.locator('.comment-input').input_value() == '入力途中を保持'
    assert card.locator('.comment-section.open').count() == 1
    # Reference/ranking images use the same publisher variant and retain originals.
    for selector in ['#rankingList img', '.idea-source-card img', '.analysis-float-source img']:
        targets=page.locator(selector).all()
        assert targets, selector
        for target in targets:
            assert target.get_attribute('data-original-src')
            assert urlparse(target.get_attribute('src')).hostname == 'hips.hearstapps.com'
    card.locator('.image-edit-btn').click()
    assert page.locator('#imageEditorUrl').input_value().splitlines() == [URLS[0], HEARST+'second.jpg']
    assert 'resize=' in page.locator('#imageEditorPreview img').get_attribute('src')
    page.locator('.image-editor-close').click()
    page.evaluate("openNewsImageGallery('jp1')")
    assert 'resize=' in page.locator('dialog figure img').get_attribute('src')
    page.locator('dialog [data-next]').click()
    assert page.locator('dialog figure img').get_attribute('data-original-src') == HEARST+'second.jpg'
    page.locator('dialog [data-close]').click()
    assert page.evaluate('window.LOADED_NEWS_DATA.map(n=>n.img)') == URLS, 'never rewrite stored data'
    assert not any('/items/' in p or '/admin/' in p for _,p in writes), writes
    assert not errors, errors
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    card.screenshot(path=str(OUT/f'fixture-{edition}-{width}.png'))
    context.close()
    return {'edition':edition, 'width':width, 'status':'PASS', 'originalUrlsPreserved':True}


if __name__ == '__main__':
    OUT.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='msedge', headless=True)
        results=[verify(browser,e,w) for e in ['interior','exterior'] for w in [1440,390]]
        browser.close()
    (OUT/'browser-tests.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(results,ensure_ascii=False))
