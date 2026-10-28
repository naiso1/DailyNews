import unittest
from urllib.parse import quote

from dailynews.source_policy import filter_sources, is_excluded_source
from auto_update_daily_news import validate_editorial_publication


class SourcePolicyTests(unittest.TestCase):
    def test_exterior_mota_exclusion_uses_host_boundaries(self):
        for host in ('autoc-one.jp', 'www.autoc-one.jp', 'AUTOC-ONE.JP.'):
            self.assertTrue(is_excluded_source(f'https://{host}/news/5045411/', 'exterior'))
        for url in ('https://not-autoc-one.jp/news', 'https://autoc-one.jp.example.com/news',
                    'https://prtimes.jp/article?reference=autoc-one.jp', 'https://[invalid'):
            self.assertFalse(is_excluded_source(url, 'exterior'))
        self.assertFalse(is_excluded_source('https://autoc-one.jp/news/5045411/', 'interior'))

    def test_search_wrapper_is_excluded_without_network(self):
        target = quote('https://autoc-one.jp/news/5045411/', safe='')
        for url in (f'https://www.bing.com/news/apiclick.aspx?url={target}',
                    f'https://news.google.com/articles/test?url={target}',
                    f'https://duckduckgo.com/l/?uddg={target}'):
            self.assertTrue(is_excluded_source(url, 'exterior'))

    def test_collection_filter_keeps_original_source_before_deduplication(self):
        original = {'URL': 'https://prtimes.jp/main/html/rd/p/000000415.000007223.html'}
        mota = {'URL': 'https://autoc-one.jp/news/5045411/'}
        self.assertEqual(filter_sources([mota, original], 'exterior'), [original])
        self.assertEqual(filter_sources([mota, original], 'interior'), [mota, original])

    def test_publisher_excludes_mota_even_when_resume_recognises_existing_url(self):
        item = dict(url='https://autoc-one.jp/news/5045411/', country='jp', title='自動車フィルム新工法')
        snapshot = dict(excluded_urls=[], rules=[])
        for existing in (set(), {item['url']}):
            self.assertEqual(validate_editorial_publication([item], existing, snapshot, 'exterior'), [])
        self.assertEqual(validate_editorial_publication([item], set(), snapshot, 'interior'), [item])


if __name__ == '__main__':
    unittest.main()
