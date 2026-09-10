"""Offline source-text selection, bounded fetching and publication integration."""

import importlib.util
import csv
import io
from contextlib import redirect_stdout
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ニュース収集"))
import source_highlights as highlights
from backfill_source_highlights import add_highlight_fields


class SelectionTests(unittest.TestCase):
    def test_only_visible_article_not_related_or_hidden_json(self):
        html = '''<nav><p>Buy a new steering wheel with leather.</p></nav>
        <article><div class="entry-content">
        <p>The <strong>steering wheel</strong> has tactile controls and a leather finish.</p>
        <p hidden>A better steering wheel is here, hidden.</p>
        <div style="display:none"><div style="color:red">Nested hidden evidence.</div></div>
        <div class="related"><p>Other steering wheel stories and reviews.</p></div>
        <script type="application/ld+json">{"articleBody":"Hidden exclusive content"}</script>
        </div></article>'''
        paragraphs = highlights.article_paragraphs(html)
        self.assertEqual(paragraphs, ['The steering wheel has tactile controls and a leather finish.'])
        quote = highlights.choose_excerpt({"title": "触感を重視したステアリング", "desc": "革製ハンドルと操作系を紹介。"}, paragraphs)
        self.assertEqual(quote["sourceExcerpt"], paragraphs[0])

    def test_cross_language_topics_and_known_brand_names(self):
        paragraphs = ['Welcome to our website and read the latest stories.',
                      'Mazda values human craftsmanship and the gestures involved in shaping materials.']
        item = {"title": "マツダ、手仕事の価値を語る", "desc": "素材に向き合う工芸の意義を示す。"}
        self.assertEqual(highlights.choose_excerpt(item, paragraphs)["sourceExcerpt"], paragraphs[1])

    def test_absent_evidence_is_not_invented_or_translated(self):
        item = {"title": "ステアリングと照明", "desc": "触感を高めたハンドル。"}
        self.assertEqual(highlights.choose_excerpt(item, ["Weather forecast: rain with snow tomorrow."]), {})
        self.assertEqual(highlights.article_paragraphs('<body><nav><p>Steering wheel stories.</p></nav></body>'), [])

    def test_whitespace_only_normalization_and_literal_endpoints(self):
        text = 'Mazda’s craftsmanship values ' + ' '.join('material%d' % i for i in range(45)) + '.'
        quote = highlights.choose_excerpt({"title": "マツダの工芸", "desc": "素材を紹介。"}, [text])
        self.assertIn(quote["sourceExcerpt"], text)
        self.assertIn(quote["sourceExcerptEnd"], text)
        self.assertLessEqual(len((quote["sourceExcerpt"] + ' ' + quote["sourceExcerptEnd"]).split()), 24)
        self.assertEqual(highlights.plain('　ＡＩ　は\n“手仕事”'), 'ＡＩ は “手仕事”')

    def test_ambiguous_start_not_published(self):
        text = 'The steering wheel uses tactile switches for the driver.'
        self.assertEqual(highlights.choose_excerpt({"title": "ステアリング", "desc": "操作系。"}, [text, text]), {})

    def test_interior_details_outrank_generic_price_discussion(self):
        paragraphs = ['Honda luxury pricing keeps climbing because of financing costs.',
                      'The cabin uses improved materials and a clean dashboard layout.']
        item = {'title': 'ホンダの内装を改善', 'desc': '素材とダッシュボードを見直し、高級車より低価格に。'}
        self.assertEqual(highlights.choose_excerpt(item, paragraphs)['sourceExcerpt'], paragraphs[1])

    def test_japanese_reporter_and_photo_lines_not_joined_into_quote(self):
        text = '<article><p>REPORT author / click for photos\n\nステアリングの操作感を改善し、スイッチの触感を細かく調整した。\n\n別の本文も紹介する。</p></article>'
        quote = highlights.choose_excerpt({'title': 'ステアリングの操作感', 'desc': '触感を改善。'}, highlights.article_paragraphs(text))
        self.assertNotIn('REPORT', quote['sourceExcerpt'])


class FetchTests(unittest.TestCase):
    def test_private_urls_and_schemes_rejected(self):
        for url in ['file:///a', 'http://localhost/a', 'http://ieweb01/a', 'http://127.0.0.1/a', 'http://192.168.1.1/a', 'https://user:pass@example.com/a']:
            self.assertFalse(highlights.public_url(url))
        self.assertTrue(highlights.public_url('https://example.com/story?q=1'))

    def test_redirect_cannot_request_localhost(self):
        response = Mock(status_code=302, headers={"Location": "http://127.0.0.1/api"})
        session = Mock()
        session.get.return_value.__enter__ = Mock(return_value=response)
        session.get.return_value.__exit__ = Mock(return_value=False)
        with self.assertRaises(ValueError):
            highlights.fetch_html(session, 'https://example.com/story')
        self.assertEqual(session.get.call_count, 1)


class CacheAndPatchTests(unittest.TestCase):
    def test_success_reused_and_summary_change_invalidates(self):
        item = {"id": "eu1", "url": "https://example.com/a", "title": "ステアリング", "desc": "触感を改善。"}
        html = b'<article><p>The steering wheel uses tactile controls for the driver.</p></article>'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'cache.json'
            with patch.object(highlights, 'fetch_html', return_value=(html, item['url'])) as fetch:
                one = dict(item)
                highlights.enrich_items([one], session=Mock(), cache_path=path, log=lambda _: None)
                two = dict(item)
                highlights.enrich_items([two], session=Mock(), cache_path=path, log=lambda _: None)
                self.assertEqual(one, two)
                self.assertEqual(fetch.call_count, 1)
                highlights.enrich_items([{**item, 'desc': '新しい操作感。'}], session=Mock(), cache_path=path, log=lambda _: None)
                self.assertEqual(fetch.call_count, 2)
                self.assertNotIn('html', path.read_text())

    def test_fetch_failure_preserves_content_and_has_no_false_quote(self):
        item = {"url": "https://example.com/a", "title": "題名", "desc": "記事を紹介。"}
        original = dict(item)
        with tempfile.TemporaryDirectory() as directory, patch.object(highlights, 'fetch_html', side_effect=ValueError('unavailable')):
            report = highlights.enrich_items([item], session=Mock(), cache_path=Path(directory) / 'cache.json', log=lambda _: None)
        self.assertEqual(item, original)
        self.assertEqual(report[0]['status'], 'fetch_failed')

    def test_targeted_patch_preserves_other_fields_and_crlf(self):
        before = 'window.X=[{\r\n    id: "eu1",\r\n    title: "日本語",\r\n}];\r\n'
        quote = 'an exact "quoted" phrase'
        after = add_highlight_fields(before, [{"id": "eu1", "sourceExcerpt": quote}])
        addition = '    sourceExcerpt: ' + json.dumps(quote, ensure_ascii=False) + ',\r\n'
        self.assertEqual(after.replace(addition, ''), before)
        with self.assertRaises(ValueError):
            add_highlight_fields(before, [{"id": "eu2", "sourceExcerpt": quote}])


class PublisherIntegrationTests(unittest.TestCase):
    def test_only_new_items_are_enriched_and_dry_run_never_fetches(self):
        spec = importlib.util.spec_from_file_location('publisher_highlight_test', ROOT / 'auto_update_daily_news.py')
        publisher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(publisher)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sheet = root / 'sheet.csv'
            news = root / 'news.js'
            original = 'window.NEWS_UPDATED_AT = "2026-09-09 00:00";\nwindow.LOADED_NEWS_DATA = [\n    {id: "eu1", url: "https://example.com/old"},\n];\n'
            with sheet.open('w', encoding='utf-8', newline='') as handle:
                writer = csv.writer(handle)
                writer.writerow(['国', '日付', 'タイトル（日本語）', '内容（日本語）', 'URL', '画像URL', 'LLM判定'])
                for kind in ['old', 'new']:
                    writer.writerow(['欧州', '2026-09-09', 'ステアリングの操作性', '触感を改善する。', 'https://example.com/' + kind, 'https://example.com/pic.jpg', '対象'])

            def enrich(items):
                self.assertEqual([i['url'] for i in items], ['https://example.com/new'])
                items[0]['sourceExcerpt'] = 'The steering wheel uses tactile controls.'

            argv = ['publisher', '--sheet', str(sheet), '--skip-insights', '--skip-html']
            with patch.object(publisher, 'NEWS_PATH', news), patch('ニュース収集.source_highlights.enrich_items', side_effect=enrich) as mocked, redirect_stdout(io.StringIO()):
                news.write_text(original, encoding='utf-8')
                with patch.object(sys, 'argv', argv + ['--dry-run']):
                    publisher.main()
                mocked.assert_not_called()
                self.assertEqual(news.read_text(encoding='utf-8'), original)
                with patch.object(sys, 'argv', argv):
                    publisher.main()
                mocked.assert_called_once()
                self.assertIn('sourceExcerpt: "The steering wheel uses tactile controls."', news.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
