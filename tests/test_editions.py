"""Edition isolation and strict exterior selection, without network or model calls."""
import importlib.util
import csv
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ニュース収集"))

from dailynews.editions import get_edition
from dailynews import exterior
import auto_update_daily_news as updater
from summary_grounding import summary_grounding_rules, summary_omits_interior_details


class EditionTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"DAILYNEWS_EDITION": "exterior"})
        self.env.start()
        updater.configure_edition("exterior")

    def tearDown(self):
        self.env.stop()
        updater.configure_edition("interior")

    def test_paths_and_unknown_edition_fail_closed(self):
        interior = get_edition("interior")
        exterior_context = get_edition("exterior")
        self.assertEqual(interior.content_dir, ROOT)
        self.assertEqual(exterior_context.content_dir, ROOT / "content/exterior")
        self.assertEqual(exterior_context.runtime_dir, ROOT / "runtime/exterior")
        self.assertFalse(exterior_context.image_generation["enabled"])
        for value in ("", "exterir", "../interior"):
            with self.assertRaises(ValueError):
                get_edition(value)
        self.assertEqual(updater.NEWS_PATH, exterior_context.content_dir / "news_data.js")
        self.assertNotEqual(updater.HTML_PATH, ROOT / "内装製品デイリーニュース.html")

    def test_exterior_summary_and_scope_do_not_prefer_interior_products(self):
        self.assertIn("外装", summary_grounding_rules())
        self.assertNotIn("内装", summary_grounding_rules())
        source = "A new grille has a radar-transparent emblem and revised bumper."
        self.assertTrue(summary_omits_interior_details("新型車を発売。", source))
        self.assertFalse(summary_omits_interior_details("新型グリルとバンパーを採用。", source))
        self.assertFalse(updater._is_out_of_scope_idea("レーダー透過エンブレムとフロントグリル"))
        self.assertTrue(updater._is_out_of_scope_idea("シート内蔵スピーカーとセンターコンソール"))
        self.assertEqual(exterior.calibrate_score(90, "Luxury seat cover", "interior cabin display")[0], 35)

    def test_exterior_prompt_and_item_overrides(self):
        item = {"newsId": "jp1", "title": "発光グリルを公開", "desc": "新型車の発光グリルと透過エンブレム。", "interiorScore": 85}
        prompt = updater.make_country_prompt("2026-09-14", "jp", [item], "外装開発向け", need_count=1)
        self.assertIn("発光グリル", prompt)
        self.assertNotIn("内装開発", prompt)
        self.assertNotIn("外装製品も企画対象外", prompt)
        self.assertNotIn("imagePromptは必須", prompt)
        known_url = next(iter(updater.ITEM_OVERRIDES))
        item = {"url": known_url, "title": "外装に関する本文の要約"}
        self.assertEqual(updater.apply_item_overrides(item), item)

    def test_exterior_source_quote_matches_exterior_parts(self):
        from ニュース収集.source_highlights import choose_excerpt, fingerprint
        item = {"edition": "exterior", "title": "新しいグリルとバンパー", "desc": "グリルとバンパーの設計を刷新した。"}
        paragraph = "The redesigned grille and bumper integrate exterior lighting with radar-transparent materials."
        result = choose_excerpt(item, ["The interior has a display and heated seats for passengers.", paragraph])
        self.assertIn(result["sourceExcerpt"], paragraph)
        self.assertNotEqual(fingerprint(item), fingerprint({**item, "edition": "interior"}))

    def test_empty_publication_requires_collection_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            context = get_edition("exterior", root)
            context.runtime_dir.mkdir(parents=True)
            context.content_dir.mkdir(parents=True)
            with patch.object(updater, "EDITION", context), patch.object(updater, "NEWS_PATH", context.content_dir / "news_data.js"), patch.object(updater, "INSIGHTS_PATH", context.content_dir / "insights_data.js"), patch.dict(os.environ, {"TARGET_DATES": "2026-09-14"}):
                with self.assertRaises(RuntimeError):
                    updater.write_exterior_publication_status([], require_empty_collection=True)
                receipt = {"edition_id": "exterior", "completed": True, "selected_count": 0, "source_count": 5, "target_dates": ["2026-09-14"]}
                (context.runtime_dir / "collection_result.json").write_text(json.dumps(receipt), encoding="utf-8")
                result = updater.write_exterior_publication_status([], require_empty_collection=True)
                self.assertEqual(result["processed_through"], "2026-09-14")
                self.assertEqual(result["status"], "no_matching_news")
                self.assertTrue((context.content_dir / "news_data.js").exists())
                receipt["selected_count"] = 1
                receipt["target_dates"] = ["2026-09-13", "2026-09-14"]
                (context.runtime_dir / "collection_result.json").write_text(json.dumps(receipt), encoding="utf-8")
                with patch.dict(os.environ, {"TARGET_DATES": "2026-09-13,2026-09-14"}):
                    result = updater.write_exterior_publication_status([{"date": "2026-09-13"}])
                    self.assertEqual(result["processed_through"], "2026-09-14")
                receipt["selected_count"] = 0
                receipt["target_dates"] = ["2026-09-13"]
                (context.runtime_dir / "collection_result.json").write_text(json.dumps(receipt), encoding="utf-8")
                with self.assertRaises(RuntimeError):
                    updater.write_exterior_publication_status([], require_empty_collection=True)

    def test_partial_insights_fail_and_retry_reuses_completed_region(self):
        with tempfile.TemporaryDirectory() as directory:
            context = get_edition("exterior", directory)
            context.config_dir.mkdir(parents=True)
            context.collection_settings_path.write_text(json.dumps({"exterior": {"selection": {"minimum_score": 60}}}), encoding="utf-8")
            context.ensure_directories()
            sheet = context.runtime_dir / "sheet2_llm_targets.csv"
            with sheet.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["国", "日付", "タイトル（日本語）", "内容（日本語）", "URL", "画像URL", "LLM判定", "内装関連度"])
                for country, key in (("日本", "jp"), ("中国", "cn")):
                    writer.writerow([country, "2026-09-14", "発光グリルの開発", "新型グリルとバンパーの設計を紹介した。", f"https://example.com/{key}", "", "対象", 80])
            news = context.content_dir / "news_data.js"
            insights = context.content_dir / "insights_data.js"
            marker = context.content_dir / "publication_status.json"
            original_insights = 'window.DAILY_INSIGHTS = [\n];\n'
            insights.write_text(original_insights, encoding="utf-8")
            failed = {"cn"}

            def generate(_endpoint, _model, country):
                if country in failed:
                    raise RuntimeError("Simulated regional model failure")
                return json.dumps({"analysis": f"発光グリル[{country}1]は部品の一体化を検討する材料となる。",
                                   "ideas": [{"title": "発光グリル", "desc": "新型グリルの設計を参考に発光機能を提案する。", "sourceNewsIds": [country + "1"]},
                                             {"title": "補修用バンパー", "desc": "新型バンパーの部品交換を容易にする接合構造を提案する。", "sourceNewsIds": [country + "1"]}]}, ensure_ascii=False)

            argv = ["publisher", "--edition", "exterior", "--sheet", str(sheet), "--skip-html"]
            with patch.multiple(updater, EDITION=context, NEWS_PATH=news, INSIGHTS_PATH=insights), patch.object(sys, "argv", argv), patch("ニュース収集.source_highlights.enrich_items"), patch.object(updater, "make_country_prompt", side_effect=lambda _date, country, *_args, **_kwargs: country), patch.object(updater, "call_llm", side_effect=generate) as llm, redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(RuntimeError, "Exterior insights incomplete for: cn"):
                    updater.main()
                self.assertTrue(news.exists())  # Article text alone is an incomplete first build.
                self.assertFalse(marker.exists())
                self.assertEqual(insights.read_text(encoding="utf-8"), original_insights)
                checkpoint = updater.read_exterior_checkpoint("2026-09-14")
                self.assertEqual(set(checkpoint["countries"]), {"jp"})
                failed.clear()
                llm.reset_mock()
                updater.main()
                self.assertEqual([call.args[2] for call in llm.call_args_list], ["cn"])
                self.assertEqual(json.loads(marker.read_text(encoding="utf-8"))["status"], "published")
                self.assertIn('jp: "', insights.read_text(encoding="utf-8"))
                self.assertIn('cn: "', insights.read_text(encoding="utf-8"))


class CollectorEditionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global collector
        import google_search_script as collector

    def setUp(self):
        collector.configure_edition("exterior")

    def tearDown(self):
        collector.configure_edition("interior")

    def test_caches_are_cleared_on_edition_change(self):
        collector.LLM_CACHE["same-url"] = "interior decision"
        collector._summary_cache["same-url"] = "interior summary"
        collector.configure_edition("exterior")
        self.assertFalse(collector.LLM_CACHE)
        self.assertFalse(collector._summary_cache)
        self.assertEqual(Path(collector.EXCEL_FILE).parent, get_edition("exterior").runtime_dir)

    def test_bing_processes_each_result_and_skips_only_wrong_dates(self):
        entries = [
            {"title": "First grille", "link": "https://example.com/one", "published": "2026-09-14", "summary": "First body"},
            {"title": "Second bumper", "link": "https://example.com/two", "published": "2026-09-14", "summary": "Second body"},
            {"title": "Old emblem", "link": "https://example.com/old", "published": "2026-09-13", "summary": "Old body"},
        ]
        response = Mock(status_code=200, headers={"Content-Type": "application/rss+xml"}, content=b"<rss/>")
        with patch.object(collector, "COUNTRY_SETTINGS", {"日本": {"bing_market": "ja-JP", "keywords": ["test grille"]}}), patch.object(collector.requests, "get", return_value=response), patch.object(collector.feedparser, "parse", return_value=Mock(entries=entries)), patch.object(collector, "resolve_final_url", side_effect=lambda url: url), patch.object(collector, "extract_image_from_rss", return_value="https://example.com/image.jpg"), patch.object(collector.time, "sleep"), redirect_stdout(io.StringIO()):
            results = collector.fetch_from_bing_search(["2026-09-14"])
        self.assertEqual([item["URL"] for item in results], ["https://example.com/one", "https://example.com/two"])

    def test_strict_selection_does_not_backfill_rejected_or_require_images(self):
        rows = [
            {"国": "日本", "日付": "2026-09-14", "タイトル": "新型グリルの透過技術", "タイトル（日本語）": "新型グリルの透過技術", "内容": "グリルとバンパーの設計を紹介する。", "内容（日本語）": "グリルとバンパーの設計を紹介する。", "URL": "https://example.com/grille", "LLM判定": "対象", "内装関連度": 82, "画像URL": "", "LLM後処理": "実施"},
            {"国": "日本", "日付": "2026-09-14", "タイトル（日本語）": "販売台数を公表", "内容（日本語）": "新車の販売台数を公表した。", "URL": "https://example.com/sales", "LLM判定": "非対象", "内装関連度": 90, "画像URL": "https://example.com/photo.jpg", "LLM後処理": "実施"},
            {"国": "日本", "日付": "2026-09-14", "タイトル（日本語）": "バンパーの外観を公開", "内容（日本語）": "外観写真のみ紹介する。", "URL": "https://example.com/photo-only", "LLM判定": "対象", "内装関連度": 35, "画像URL": "https://example.com/photo.jpg", "LLM後処理": "実施"},
        ]
        with tempfile.TemporaryDirectory() as folder, patch.object(collector, "summarize_article", side_effect=AssertionError("Unexpected LLM call")):
            target = Path(folder) / "search_results.csv"
            collector.build_sheet2_and_csv(collector.pd.DataFrame(rows), target, ["2026-09-14"])
            selected = collector.pd.read_csv(target.with_name("sheet2_llm_targets.csv"))
            self.assertEqual(selected["URL"].tolist(), ["https://example.com/grille"])
            collector.build_sheet2_and_csv(collector.pd.DataFrame(rows), target, ["2026-09-13"])
            self.assertTrue(collector.pd.read_csv(target.with_name("sheet2_llm_targets.csv")).empty)

if __name__ == "__main__":
    unittest.main()
