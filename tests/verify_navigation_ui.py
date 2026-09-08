"""Local browser regression test. Requires Playwright Chromium; no live account/API is used."""

import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
from urllib.parse import quote, urlparse

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def main():
    server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(QuietHandler, directory=str(ROOT)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    activity = [{'itemId': 'cn1585', 'user': 'Test reader', 'type': 'comment',
                 'text': 'Navigation test', 'createdAt': '2026-09-08T01:00:00Z'}]
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = browser.new_context(viewport={'width': 1400, 'height': 1000})
            context.route('https://**', lambda r: r.abort())
            for name in ['dailynews_client.js', 'dailynews_account.js']:
                stub = "window.accountOpenCount=0;window.dailyNewsAccount={user:{id:'test'},open:()=>window.accountOpenCount++};" if name == 'dailynews_account.js' else ''
                context.route('**/' + name + '*', lambda r, req, stub=stub: r.fulfill(body=stub, content_type='application/javascript'))

            def api(route):
                assert urlparse(route.request.url).hostname == '127.0.0.1'
                assert route.request.method == 'GET'
                data = {'activity': activity} if '/activity/recent' in route.request.url else {'notifications': [], 'unreadCount': 0}
                route.fulfill(json=data)

            context.route('**/api/**', api)
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.goto(f'http://127.0.0.1:{server.server_port}/' + quote('内装製品デイリーニュース.html') + '?countries=cn&sort=relevance-desc&from=2026-09-01&to=2026-09-07', wait_until='domcontentloaded')
            page.locator('.activity-card').wait_for()

            assert page.locator('.source-list-count').inner_text() == str(page.evaluate('window.DAILYNEWS_CONFIGURED_SOURCES.length'))
            page.locator('#sourceListButton').click()
            for source in ['Automotive Interiors World', 'Auto & Design', 'BMWBLOG', 'ル・ボラン']:
                page.locator('#sourceListSearch').fill(source)
                assert page.locator('.source-list-source').all_text_contents() == [source]
            page.locator('.source-list-close').click()

            def assert_restored(expected_account_count):
                page.wait_for_function("document.getElementById('rankingBack').classList.contains('hidden')")
                page.wait_for_timeout(450)
                assert page.locator('#searchInput').input_value() == ''
                assert page.locator('#dateFrom').input_value() == '2026-09-01'
                assert page.locator('#dateTo').input_value() == '2026-09-07'
                assert page.locator('#sortOrder').input_value() == 'relevance-desc'
                assert page.locator('#countryFilters .chip.active').get_attribute('data-country') == 'cn'
                assert page.evaluate('window.accountOpenCount') == expected_account_count

            for method in ['button', 'browser']:
                page.locator('.activity-card').click()
                page.wait_for_function("document.getElementById('searchInput').value === 'cn1585'")
                page.wait_for_timeout(400)
                card = page.locator('#card-cn1585')
                assert card.locator('.title').inner_text().endswith('車中泊仕様')
                desc = card.locator('.desc').inner_text()
                for term in ['9L冷蔵庫', '16.1インチ', '11通り', 'Explorer Edition']:
                    assert term in desc
                assert '#:~:text=' in card.locator('a.btn').get_attribute('href')
                if method == 'button':
                    page.locator('#rankingBackBtn').click()
                else:
                    page.go_back()
                assert_restored(0)

            # My-page entry points explicitly opt in; other entry points must not inherit this.
            page.evaluate("showNewsItem('cn1585', false, true)")
            page.wait_for_timeout(400)
            page.locator('#rankingBackBtn').click()
            assert_restored(1)
            page.locator('.activity-card').click()
            page.wait_for_timeout(400)
            page.locator('#rankingBackBtn').click()
            assert_restored(1)

            idea_id = page.evaluate("String(window.DAILY_INSIGHTS.flatMap(d=>Object.values(d.ideas || {}).flat()).find(i=>i.id).id)")
            activity[0]['itemId'] = 'idea-' + idea_id
            page.evaluate("window.dispatchEvent(new Event('dailynews:activity-updated'))")
            page.locator(f'[data-activity-item="idea-{idea_id}"]').wait_for()
            page.locator('.activity-card').click()
            page.wait_for_timeout(400)
            page.locator('#rankingBackBtn').click()
            assert_restored(1)
            assert not errors, errors
            print('PASS: source directory, activity news/idea returns, button/browser back, account-only return, restored filters, cn1585 content')
            browser.close()
    finally:
        server.shutdown()


if __name__ == '__main__':
    main()
