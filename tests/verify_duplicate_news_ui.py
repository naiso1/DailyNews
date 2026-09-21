"""Browser regression with in-memory fixtures; no production content or API is modified."""

import argparse
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if urlparse(self.path).path.endswith('/favicon.ico'):
            self.send_response(204)
            self.end_headers()
            return
        super().do_GET()

    def translate_path(self, path):
        if path.startswith('/exterior/'):
            path = '/' + path[len('/exterior/'):]
        return super().translate_path(path)

    def log_message(self, *args):
        pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    news = [
        {'id': 'jp1', 'date': '2026-09-17', 'title': '代表記事：内装材の同一発表',
         'relatedUrls': ['https://syndicated.test/article', 'javascript:alert(1)', 'https://hidden.test/article']},
        {'id': 'jp2', 'date': '2026-09-20', 'title': '転載記事', 'duplicateOf': 'jp1',
         'url': 'https://syndicated.test/article'},
        {'id': 'jp3', 'date': '2026-09-20', 'duplicateOf': 'jp2'},
        {'id': 'eu1', 'country': 'eu', 'date': '2026-09-20', 'title': '最新号の別製品'},
        {'id': 'cn1', 'country': 'cn', 'title': '非表示の代表記事', 'url': 'https://hidden.test/article'},
        {'id': 'cn2', 'country': 'cn', 'date': '2026-09-20', 'duplicateOf': 'cn1'},
        {'id': 'in1', 'date': '2026-09-20', 'duplicateOf': 'missing'},
        {'id': 'us1', 'date': '2026-09-20', 'duplicateOf': 'us2'},
        {'id': 'us2', 'date': '2026-09-20', 'duplicateOf': 'us1'},
    ]
    news = [{'country': 'jp', 'date': '2026-09-17', 'title': '確認記事', 'desc': '記事の説明。',
             'source': '検証媒体', 'url': f'https://source.test/{n["id"]}', 'tags': ['内装'],
             'img': 'page_images/icon_world.png', 'exteriorScore': 90, **n} for n in news]
    current_ids = [n['id'] for n in news if n['date'] == '2026-09-20']
    publication = {'edition_id': 'exterior', 'status': 'published', 'processed_through': '2026-09-20',
                   'issue_date': '2026-09-20', 'lookback_start': '2026-09-14',
                   'target_dates': ['2026-09-20'], 'source_dates': ['2026-09-20'],
                   'selected_count': len(current_ids), 'supplemental_count': 0, 'selected_news_ids': current_ids}
    insights = [{'date': '2026-09-20', 'analysis': {'jp': '保存した発表を確認する。[jp2]'}, 'ideas': {}}]
    result = {'status': 'running', 'viewports': {}, 'blocked_mutations': [], 'page_errors': []}
    server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Handler, directory=str(ROOT)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    origin = f'http://127.0.0.1:{server.server_port}'
    entry = ROOT / '内装製品デイリーニュース.html'

    def route_request(route):
        request = route.request
        parsed = urlparse(request.url)
        if request.method not in {'GET', 'HEAD'}:
            result['blocked_mutations'].append({'method': request.method, 'path': parsed.path})
            route.abort()
        elif parsed.netloc != f'127.0.0.1:{server.server_port}':
            route.abort()
        elif parsed.path == '/exterior/':
            route.fulfill(body=entry.read_text(encoding='utf-8'), content_type='text/html; charset=utf-8')
        elif parsed.path.endswith('/favicon.ico'):
            route.fulfill(status=204)
        elif parsed.path.endswith('/news_data.js'):
            route.fulfill(body='window.LOADED_NEWS_DATA=' + json.dumps(news, ensure_ascii=False) + ';',
                          content_type='application/javascript; charset=utf-8')
        elif parsed.path.endswith('/insights_data.js'):
            route.fulfill(body='window.DAILY_INSIGHTS=' + json.dumps(insights, ensure_ascii=False) + ';',
                          content_type='application/javascript; charset=utf-8')
        elif parsed.path.endswith('/publication_status.json'):
            route.fulfill(json=publication)
        elif parsed.path.startswith('/exterior/api/'):
            route.fulfill(json={'authenticated': False, 'user': None,
                                'interactions': {'cn1': {'hidden': True}, 'jp2': {'likes': 20}},
                                'activity': [], 'notifications': [], 'unreadCount': 0,
                                'total': 0, 'daily': {}, 'users': []})
        else:
            route.continue_()

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel='msedge', headless=True)
            for name, width, height in [('desktop', 1440, 1000), ('mobile', 390, 844)]:
                context = browser.new_context(viewport={'width': width, 'height': height}, service_workers='block')
                context.route('**/*', route_request)
                context.add_init_script("localStorage.setItem('dailynews_exterior:favorites_v1', JSON.stringify(['jp2','jp3']));")
                page = context.new_page()
                page.on('pageerror', lambda error: result['page_errors'].append(str(error)))
                page.goto(origin + '/exterior/', wait_until='domcontentloaded')
                page.wait_for_function("document.getElementById('visibleCount').textContent === '1' && window.interactionsData?.cn1?.hidden")
                assert page.locator('#newsGrid > .card').count() == 1
                assert page.locator('#card-eu1').count() == 1
                assert page.locator('#totalCount').inner_text() == '2'
                assert page.locator('#exteriorPublicationStatus').inner_text() == '2026-09-20号：1件'
                assert page.locator('#countryFilters [data-country="world"].new-count').inner_text() == 'New 1'
                assert page.locator('#countryFilters [data-country="jp"].new-count').is_hidden()
                assert page.evaluate("JSON.parse(localStorage.getItem('dailynews_exterior:favorites_v1'))") == ['jp2', 'jp3']
                assert not any('favorites' in row['path'] for row in result['blocked_mutations'])
                page.locator('.analysis-ref-link').click()
                page.wait_for_function("document.getElementById('searchInput').value === 'jp1'")
                assert page.locator('#card-jp1').count() == 1
                assert page.locator('#card-jp2').count() == 0
                assert page.locator('#card-jp1 .favorite-btn').get_attribute('class').endswith(' active')
                assert page.locator('#dateFrom').input_value() == ''
                assert page.locator('#dateTo').input_value() == ''
                page.locator('.related-news-sources summary').click()
                links = page.locator('.related-news-sources a')
                assert links.count() == 1
                assert links.first.get_attribute('href') == 'https://syndicated.test/article'
                assert links.first.get_attribute('rel') == 'noopener noreferrer'
                page.locator('#card-jp1').screenshot(path=str(args.output / f'{name}_representative.png'))
                page.locator('#rankingBackBtn').click()
                page.wait_for_function("document.getElementById('searchInput').value === '' && document.getElementById('card-eu1')")
                assert page.locator('#dateFrom').input_value() == '2026-09-20'
                assert page.locator('#dateBasis').input_value() == 'issue'
                assert page.locator('#newsGrid > .card').count() == 1
                page.locator('.analysis-ref-link').click()
                page.wait_for_function("document.getElementById('searchInput').value === 'jp1'")
                page.reload(wait_until='domcontentloaded')
                page.wait_for_function("document.getElementById('visibleCount').textContent === '1'")
                assert page.locator('#card-jp1').count() == 1
                assert page.locator('#dateFrom').input_value() == ''
                page.evaluate("showNewsItem('cn2')")
                assert page.locator('#searchInput').input_value() == 'jp1'
                assert page.locator('#card-cn1').count() == 0
                page.evaluate("showNewsItem('us1')")
                assert page.locator('#searchInput').input_value() == 'jp1'
                page.locator('#searchInput').fill('')
                page.locator('#searchInput').dispatch_event('change')
                page.locator('#favoritesToggle').click()
                assert page.locator('#newsGrid > .card').count() == 1
                assert page.locator('#card-jp1').count() == 1
                page.evaluate("applyFilters(); applyFilters();")
                assert page.locator('#newsGrid > .card').count() == 1
                assert page.locator('#totalCount').inner_text() == '2'
                assert page.evaluate('document.documentElement.scrollWidth') <= width
                result['viewports'][name] = {'default_count': 1, 'total_count': 2,
                                             'historical_reference_resolved': True, 'reload_preserved': True,
                                             'back_to_issue_preserved': True,
                                             'favorites_display_count': 1, 'hidden_and_cycles_blocked': True,
                                             'related_source_count': 1, 'horizontal_overflow': False}
                context.close()
            browser.close()
        assert not result['page_errors'], result['page_errors']
        result['status'] = 'passed'
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except BaseException as error:
        result['status'] = 'failed'
        result['error'] = str(error)
        raise
    finally:
        (args.output / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    main()
