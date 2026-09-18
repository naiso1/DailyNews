"""Exercise a local PackageOnly preview; all external and mutating requests are blocked."""

import argparse
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright


class PreviewHandler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        if path.startswith('/exterior/'):
            path = '/' + path[len('/exterior/'):]
        return super().translate_path(path)

    def log_message(self, *args):
        pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--channel', default='msedge')
    args = parser.parse_args()
    package = args.package.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    receipt = json.loads((package / 'publication_status.json').read_text(encoding='utf-8-sig'))
    issue_date = receipt['issue_date']
    selected = set(receipt['selected_news_ids'])
    result = {'package': str(package), 'issue_date': issue_date, 'status': 'running',
              'viewports': {}, 'blocked_mutations': [], 'blocked_external_count': 0, 'page_errors': []}
    server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(PreviewHandler, directory=str(package)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    origin = f'http://127.0.0.1:{server.server_port}'

    def route_request(route):
        request = route.request
        parsed = urlparse(request.url)
        if request.method not in {'GET', 'HEAD'}:
            result['blocked_mutations'].append({'method': request.method, 'path': parsed.path})
            route.abort()
        elif parsed.netloc != f'127.0.0.1:{server.server_port}':
            result['blocked_external_count'] += 1
            route.abort()
        elif parsed.path.startswith('/exterior/api/'):
            route.fulfill(json={'authenticated': False, 'user': None, 'interactions': {},
                                'activity': [], 'notifications': [], 'unreadCount': 0,
                                'total': 0, 'daily': {}, 'users': []})
        else:
            route.continue_()

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel=args.channel, headless=True)
            for name, width, height in [('desktop', 1440, 1000), ('mobile', 390, 844)]:
                context = browser.new_context(viewport={'width': width, 'height': height},
                                              device_scale_factor=1, service_workers='block')
                context.route('**/*', route_request)
                page = context.new_page()
                page.on('pageerror', lambda error: result['page_errors'].append(str(error)))
                observed = result['viewports'][name] = {}

                def check_count(expected):
                    page.wait_for_function('(count) => document.querySelectorAll("#newsGrid > .card").length === count', arg=expected)
                    assert page.locator('#visibleCount').inner_text() == str(expected)

                def rendered_ids():
                    return set(page.locator('#newsGrid > .card').evaluate_all('(cards) => cards.map(c => c.id.replace(/^card-/, ""))'))

                def check_width(label):
                    dimensions = page.evaluate('''() => ({width: innerWidth,
                        documentWidth: document.documentElement.scrollWidth,
                        bodyWidth: document.body.scrollWidth})''')
                    observed.setdefault('layout', {})[label] = dimensions
                    assert dimensions['documentWidth'] <= width + 1, dimensions
                    assert dimensions['bodyWidth'] <= width + 1, dimensions

                page.goto(origin + '/exterior/', wait_until='domcontentloaded')
                check_count(len(selected))
                assert page.locator('#dateBasis').input_value() == 'issue'
                assert page.locator('#dateFrom').input_value() == issue_date
                assert page.locator('#dateTo').input_value() == issue_date
                assert rendered_ids() == selected
                observed['default_count'] = len(selected)
                observed['default_range'] = [page.locator('#dateFrom').input_value(), page.locator('#dateTo').input_value()]
                if name == 'mobile':
                    positions = page.evaluate('''() => Object.fromEntries(['dateBasis', 'dateFrom', 'dateTo']
                        .map(id => [id, document.getElementById(id).getBoundingClientRect().top]))''')
                    assert abs(positions['dateFrom'] - positions['dateTo']) < 2, positions
                    assert positions['dateBasis'] < positions['dateFrom'], positions
                    observed['date_control_rows'] = positions
                check_width('default')
                page.screenshot(path=str(output / f'{name}_default.png'))
                page.locator('.date-inputs').screenshot(path=str(output / f'{name}_date_controls.png'))
                page.locator('.filters').screenshot(path=str(output / f'{name}_filters.png'))
                original_dates = page.evaluate('''() => Object.fromEntries(window.LOADED_NEWS_DATA.map(n => [n.id, n.date]))''')
                source_count = sum(date == issue_date for date in original_dates.values())
                earlier_id = next(item_id for item_id in selected if original_dates[item_id] < issue_date)
                assert page.locator(f'#card-{earlier_id} .card-date-meta').inner_text() == '掲載日 ' + original_dates[earlier_id]
                observed['earlier_original_dates'] = sum(original_dates[item_id] < issue_date for item_id in selected)
                page.locator(f'#card-{earlier_id}').screenshot(path=str(output / f'{name}_earlier_source_card.png'))

                page.locator('#dateBasis').select_option('source')
                check_count(source_count)
                observed['source_date_count'] = source_count
                assert all(original_dates[item_id] == issue_date for item_id in rendered_ids())
                page.reload(wait_until='domcontentloaded')
                check_count(source_count)
                assert page.locator('#dateBasis').input_value() == 'source'
                check_width('source')
                page.locator('.filters').screenshot(path=str(output / f'{name}_source_filters.png'))

                page.locator('#dateBasis').select_option('issue')
                check_count(len(selected))
                observed['countries'] = {}
                for country, expected in receipt['selected_by_country'].items():
                    page.locator(f'#countryFilters [data-country="{country}"].chip').click()
                    check_count(expected)
                    assert page.locator('#dateBasis').input_value() == 'issue'
                    observed['countries'][country] = expected
                page.reload(wait_until='domcontentloaded')
                check_count(expected)
                assert page.locator('#dateBasis').input_value() == 'issue'
                page.locator('#countryFilters [data-country="world"].chip').click()
                check_count(len(selected))
                page.locator('#loadMoreBtn').click()
                page.wait_for_function('(count) => document.querySelectorAll("#newsGrid > .card").length > count', arg=len(selected))
                archive_count = page.locator('#newsGrid > .card').count()
                assert selected <= rendered_ids()
                assert page.locator('#dateFrom').input_value() == ''
                assert page.locator('#dateBasis').input_value() == 'issue'
                page.reload(wait_until='domcontentloaded')
                check_count(archive_count)
                assert page.locator('#dateFrom').input_value() == ''
                assert page.locator('#dateBasis').input_value() == 'issue'
                assert selected <= rendered_ids()
                observed['archive_count_after_reload'] = archive_count
                check_width('archive')
                page.locator('.filters').screenshot(path=str(output / f'{name}_archive_filters.png'))
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
        (output / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    main()
