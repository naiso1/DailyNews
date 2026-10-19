"""Event discovery is bounded and does not bypass relevance or day ordering."""
from pathlib import Path
import sys
import unittest
from contextlib import redirect_stdout
import io
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'ニュース収集'))
from dailynews import event_collection
import google_search_script as collector


class EventCollectionTests(unittest.TestCase):
    def tearDown(self):
        collector.configure_edition('interior')

    def test_queries_added_for_both_editions_only_in_japan_event_window(self):
        for edition in ('interior', 'exterior'):
            collector.configure_edition(edition)
            all_ordinary = set(collector.edition_search_keywords(collector.COUNTRY_SETTINGS['日本']))
            current = collector.google_news_search_keywords('日本', ['2026-10-15'])
            self.assertEqual(current[-2:], list(event_collection.QUERIES))
            self.assertEqual(len(current), collector.google_news_keyword_limit() + 2)
            self.assertTrue(set(current[:-2]).issubset(all_ordinary))
            for dates in ([], ['2025-10-15'], ['2026-10-24'], ['2027-10-15']):
                ordinary = collector.google_news_search_keywords('日本', dates)
                self.assertEqual(len(ordinary), collector.google_news_keyword_limit())
                self.assertTrue(set(ordinary).issubset(all_ordinary))
            self.assertEqual(event_collection.search_keywords('欧州', ['2026-10-15']), [])

    def test_prefilter_reserves_three_candidates_without_increasing_budget(self):
        for edition in ('interior', 'exterior'):
            collector.configure_edition(edition)
            ordinary = [dict(国='日本', 日付='2026-10-15', タイトル='HMI グリル 冷却 コックピット ディスプレイ センサー', 内容='技術資料', URL=f'https://example.com/{i}') for i in range(10)]
            events = [dict(国='日本', 日付='2026-10-15', タイトル=f'CEATEC 2026 展示 {i}', 内容='デモの紹介', URL=f'https://example.com/event{i}') for i in range(4)]
            picked = collector.prefilter_results_for_enrichment(ordinary + events, 5)
            self.assertEqual(len(picked), 5)
            self.assertEqual(sum(item in events for item in picked), 3)

    def test_exterior_retains_newest_day_and_previous_targets(self):
        collector.configure_edition('exterior')
        recent = [dict(国='日本', 日付='2026-10-15', タイトル='製品発表', 内容='', URL=f'https://example.com/{i}', _previous_target=True) for i in range(3)]
        older = dict(国='日本', 日付='2026-10-13', タイトル='JMS Bizweek 2026', 内容='', URL='https://example.com/old')
        self.assertEqual(collector.prefilter_results_for_enrichment(recent + [older], 3), recent)

    def test_search_word_and_recommendations_are_not_evidence(self):
        rows = [dict(国='日本', 日付='2026-10-15', タイトル='新製品', 内容='記事本文。【関連リンク】CEATEC2026', URL='https://news.yahoo.co.jp/articles/test', 検索ワード='CEATEC 2026')]
        self.assertEqual(event_collection.review_candidates(rows), [])

    def test_exterior_reservation_is_three_per_run_not_three_per_day(self):
        collector.configure_edition('exterior')
        events = [dict(国='日本', 日付=day, タイトル=f'CEATEC2026 展示 {day} {i}', 内容='', URL=f'https://example.com/{day}/{i}')
                  for day in ('2026-10-15', '2026-10-14') for i in range(2)]
        ordinary = [dict(国='日本', 日付='2026-10-14', タイトル='グリル 冷却 フィルム 塗装 ミリ波', 内容='', URL=f'https://example.com/product{i}') for i in range(4)]
        picked = collector.prefilter_results_for_enrichment(events + ordinary, 4)
        self.assertEqual(len(picked), 4)
        self.assertEqual(sum(item in events for item in picked), 3)

    def test_event_feed_filters_dates_before_fifteen_entry_cap(self):
        collector.configure_edition('interior')
        entries = [dict(title='CEATEC 2026 announcement', published='2026-10-01', link=f'https://example.com/old{i}') for i in range(20)]
        entries.append(dict(title='CEATEC 2026 new sensor', published='2026-10-15', link='https://example.com/current'))
        with patch.object(collector, 'google_news_search_keywords', side_effect=lambda country, dates: list(event_collection.QUERIES[:1]) if country=='日本' else []), \
             patch.object(collector.requests, 'get', return_value=SimpleNamespace(status_code=200, content=b'feed')), \
             patch.object(collector.feedparser, 'parse', return_value=SimpleNamespace(entries=entries)), \
             patch.object(collector, 'resolve_final_url', side_effect=lambda url:url), \
             patch.object(collector, 'extract_image_from_rss', return_value='https://example.com/sensor.jpg'), \
             patch.object(collector.time, 'sleep'), redirect_stdout(io.StringIO()):
            result = collector.fetch_from_google_news(['2026-10-15'])
        self.assertEqual([row['URL'] for row in result], ['https://example.com/current'])


if __name__ == '__main__':
    unittest.main()
