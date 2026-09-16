"""Seven-day exterior selection keeps source dates and published issue history."""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ニュース収集"))
from dailynews.collection_digest import collection_window, published_news
from dailynews.editions import get_edition


class CollectionWindowTests(unittest.TestCase):
    def test_seven_calendar_days_include_issue_and_cross_months(self):
        window = collection_window(["2026-09-01"])
        self.assertEqual(window["lookback_start"], "2026-08-26")
        self.assertEqual(window["collection_dates"][-1], "2026-09-01")
        self.assertEqual(len(window["collection_dates"]), 7)
        with self.assertRaises(ValueError):
            collection_window([])

    def test_js_literals_keep_escaped_text_and_digest_date_without_execution(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "news.js"
            item = {"id": "jp3", "url": "https://example.com/a", "date": "2026-09-12", "digestDate": "2026-09-15", "title": '引用 "{ }" を含む見出し', "country": "jp"}
            path.write_text("window.LOADED_NEWS_DATA = [// example\n" + json.dumps(item, ensure_ascii=False) + "];", encoding="utf-8")
            self.assertEqual(published_news(path), [item])
            path.write_text("window.LOADED_NEWS_DATA = [{id: \"broken\"", encoding="utf-8")
            with self.assertRaises(ValueError):
                published_news(path)


class CollectionSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global collector
        import google_search_script as collector

    def setUp(self):
        collector.configure_edition("exterior")
        self.folder = tempfile.TemporaryDirectory()
        self.context = get_edition("exterior", self.folder.name)
        self.context.config_dir.mkdir(parents=True)
        self.context.collection_settings_path.write_text(json.dumps({"exterior": {
            "selection": {"lookback_days": 7, "minimum_score": 60, "trend_minimum_score": 65,
                          "require_original_image": False, "maximum_per_country": 10,
                          "product_priority_count": 6, "maximum_trends_per_country": 10},
            "search": {"maximum_candidates_per_country": 60}}}), encoding="utf-8")
        self.context.ensure_directories()
        self.edition_patch = patch.object(collector, "EDITION", self.context)
        self.edition_patch.start()

    def tearDown(self):
        self.edition_patch.stop()
        self.folder.cleanup()
        collector.configure_edition("interior")

    @staticmethod
    def row(index, day="2026-09-15", category="product", score=80):
        title = f"新型グリルの設計情報 {index}" if category == "product" else f"乗用車市場の販売動向 {index}"
        body = "グリルの新しい意匠を公表した。" if category == "product" else "乗用車の販売台数と市場シェアが変化した。"
        return {"国": "日本", "日付": day, "タイトル": title, "内容": body,
                "タイトル（日本語）": title, "内容（日本語）": body, "URL": f"https://example.com/{index}",
                "LLM判定": "対象", "LLM後処理": "実施", "内装関連度": score,
                "記事区分": category, "トレンド分類": "market" if category == "trend" else "", "画像URL": ""}

    def select(self, rows):
        target = self.context.runtime_dir / "search_results.csv"
        with patch.object(collector, "is_same_topic_text", return_value=False), patch.object(collector, "SHEET2_SIMILARITY_THRESHOLD", 1.1), patch.object(collector, "summarize_article", side_effect=AssertionError("No model calls in selection tests")), redirect_stdout(io.StringIO()):
            collector.build_sheet2_and_csv(collector.pd.DataFrame(rows), target, ["2026-09-15"])
        return collector.pd.read_csv(target.with_name("sheet2_llm_targets.csv"), keep_default_na=False)

    def test_today_beats_old_higher_score_and_trends_fill_product_shortage(self):
        rows = [self.row(i, category="trend", score=65) for i in range(10)]
        rows.extend(self.row(100+i, day="2026-09-14", score=99) for i in range(10))
        selected = self.select(rows)
        self.assertEqual(selected["URL"].tolist(), [row["URL"] for row in rows[:10]])
        self.assertEqual(collector.SHEET2_RESULT["selected_by_category"], {"trend": 10})
        self.assertEqual(collector.SHEET2_RESULT["selected_lookback_count"], 0)

    def test_lookback_fills_to_ten_preserving_source_dates_and_thresholds(self):
        rows = [self.row(i) for i in range(2)] + [self.row(10+i, "2026-09-09", "trend") for i in range(9)]
        rows.extend([self.row(90, "2026-09-08"), self.row(91, "2026-09-16"), self.row(92, "2026-09-14", "trend", 64)])
        selected = self.select(rows)
        self.assertEqual(len(selected), 10)
        self.assertEqual(set(selected["日付"]), {"2026-09-09", "2026-09-15"})
        self.assertEqual(collector.SHEET2_RESULT["source_dates"], ["2026-09-09", "2026-09-15"])
        self.assertEqual(collector.SHEET2_RESULT["issue_date"], "2026-09-15")
        self.assertEqual(collector.SHEET2_RESULT["selected_lookback_count"], 8)
        self.assertNotIn("https://example.com/92", selected["URL"].tolist())

    def test_previous_issue_is_excluded_current_issue_retains_reviewed_copy(self):
        previous = {"id": "jp1", "url": "https://example.com/1", "date": "2026-09-14", "country": "jp", "title": "既報グリル", "desc": "グリルを紹介した。"}
        current = {"id": "jp2", "url": "https://example.com/2", "date": "2026-09-12", "digestDate": "2026-09-15", "country": "jp", "title": "校正済みグリル記事", "desc": "公表されたグリルの意匠を説明した。", "exteriorScore": 75}
        path = self.context.content_dir / "news_data.js"
        path.write_text("window.LOADED_NEWS_DATA = " + json.dumps([previous, current], ensure_ascii=False) + ";", encoding="utf-8")
        selected = self.select([self.row(1, "2026-09-14"), self.row(2, "2026-09-12"), self.row(3)])
        self.assertEqual(set(selected["URL"]), {current["url"], "https://example.com/3"})
        retained = selected[selected["URL"].eq(current["url"])].iloc[0]
        self.assertEqual(retained["タイトル（日本語）"], current["title"])
        self.assertEqual(retained["日付"], "2026-09-12")
        self.assertEqual(collector.SHEET2_RESULT["selection_outcomes"]["already_published_in_another_issue"], 1)

    def test_current_issue_recovers_missing_checkpoint_and_empty_receipt_has_window(self):
        current = {"id": "jp2", "url": "https://example.com/2", "date": "2026-09-15", "country": "jp", "title": "校正済みグリル記事", "desc": "グリルの意匠を説明した。", "exteriorScore": 75}
        with patch.object(collector, "published_news", return_value=[current]):
            self.assertEqual(len(self.select([])), 1)
        with patch.object(collector, "published_news", return_value=[]):
            self.assertTrue(self.select([]).empty)
            self.assertEqual(collector.SHEET2_RESULT["source_dates"], [])
            self.assertEqual(collector.SHEET2_RESULT["lookback_start"], "2026-09-09")

    def test_exterior_reviews_sixty_newest_candidates_interior_stays_thirty(self):
        older = [self.row(100+i, "2026-09-14") for i in range(60)]
        today = [self.row(i) for i in range(60)]
        with patch.dict(os.environ, {}, clear=True):
            chosen = collector.prefilter_results_for_enrichment(older + today)
            self.assertEqual(len(chosen), 60)
            self.assertTrue(all(row["日付"] == "2026-09-15" for row in chosen))
            with patch.object(collector, "EDITION", get_edition("interior")):
                self.assertEqual(len(collector.prefilter_results_for_enrichment(older + today)), 30)


if __name__ == "__main__":
    unittest.main()
