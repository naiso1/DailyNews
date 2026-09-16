"""Untranslated selected rows are held for repair, without stopping valid articles."""
from contextlib import ExitStack, redirect_stdout
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
from dailynews.digest import validated_issue_context
from dailynews.publication_language import SummaryQuarantineError, summary_language_problem


class SummaryQuarantineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global collector
        import google_search_script as collector

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(collector, "is_same_topic_text", return_value=False))
        self.stack.enter_context(patch.object(collector, "SHEET2_SIMILARITY_THRESHOLD", 1.1))
        self.stack.enter_context(patch.object(collector, "OUTPUT_PAPERS_SHEET2", False))
        self.stack.enter_context(patch.object(collector, "published_news", return_value=[]))
        self.stack.enter_context(patch.object(collector, "SHEET2_RESULT", None))
        self.stack.enter_context(patch.object(collector, "SOURCE_FETCH_COUNTS", {"attempted": 1, "succeeded": 1}))
        self.stack.enter_context(patch.object(collector, "EXTERIOR_REQUIRED_LLM_ERRORS", {"relevance": 0, "score": 0}))
        self.stack.enter_context(patch.object(collector, "TARGET_DATES_RUN", ["2026-09-16"]))

    def context(self, edition):
        context = get_edition(edition, self.root / edition)
        context.config_dir.mkdir(parents=True)
        context.collection_settings_path.write_text(json.dumps({edition: {"selection": {
            "require_original_image": edition == "interior", "maximum_per_country": 10,
            "lookback_days": 7, "minimum_score": 60, "trend_minimum_score": 65}}}), encoding="utf-8")
        context.ensure_directories()
        return context

    @staticmethod
    def row(index, valid=True, day="2026-09-16"):
        return {"国": "日本", "日付": day, "タイトル": f"Original grille {index}",
                "内容": f"Original source body for grille {index}.",
                "タイトル（日本語）": f"新型グリル{index}の発表" if valid else f"Original grille {index}",
                "内容（日本語）": f"新型グリル{index}を公開した。" if valid else f"Original source body for grille {index}.",
                "URL": f"https://example.com/{index}", "画像URL": f"https://example.com/photo{index}.jpg",
                "LLM判定": "対象", "LLM後処理": "実施", "内装関連度": 80,
                "記事区分": "product", "トレンド分類": ""}

    def test_partial_selection_preserves_source_and_receipt_consistency_both_editions(self):
        for edition in ("interior", "exterior"):
            context = self.context(edition)
            target = context.runtime_dir / "search_results.csv"
            rows = [self.row(1), self.row(2, False, "2026-09-15" if edition == "exterior" else "2026-09-16")]
            raw = collector.pd.DataFrame(rows)
            raw.to_csv(target, index=False, encoding="utf-8")
            with patch.object(collector, "EDITION", context), patch.object(collector, "summarize_article", return_value=(rows[1]["タイトル"], rows[1]["内容"])) as summarize, redirect_stdout(io.StringIO()) as output:
                collector.build_sheet2_and_csv(raw, target, ["2026-09-16"])
                result = dict(collector.SHEET2_RESULT)
            selected = collector.pd.read_csv(target.with_name("sheet2_llm_targets.csv"), keep_default_na=False)
            stored = collector.pd.read_csv(target, keep_default_na=False)
            self.assertEqual(selected["URL"].tolist(), [rows[0]["URL"]])
            self.assertEqual(stored["タイトル"].tolist(), raw["タイトル"].tolist())
            self.assertEqual(stored["内容"].tolist(), raw["内容"].tolist())
            self.assertEqual(stored["LLM判定"].tolist(), ["対象", "対象"])
            self.assertEqual(stored["内装関連度"].tolist(), [80, 80])
            self.assertEqual(stored["LLM後処理"].tolist(), ["実施", "日本語化失敗"])
            self.assertEqual(result["selected_count"], 1)
            self.assertEqual(result["quarantined_count"], 1)
            self.assertEqual(result["quarantined_urls"], [rows[1]["URL"]])
            receipt = json.loads(target.with_name("summary_quarantine.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["articles"][0]["reason"], "untranslated_title")
            self.assertIn(rows[1]["URL"], output.getvalue())
            summarize.assert_called_once()
            if edition == "exterior":
                self.assertEqual(result["source_dates"], ["2026-09-16"])
                self.assertEqual(result["selection_outcomes"]["summary_language_failed"], 1)
                completed = {"edition_id": edition, "completed": True, "target_dates": ["2026-09-16"], **result}
                context_result = validated_issue_context(completed, [{"country": "jp", "date": "2026-09-16", "url": rows[0]["URL"]}])
                self.assertEqual(context_result["selected_by_country"], {"jp": 1})

    def test_all_failed_selection_retains_previous_sheet_and_cannot_be_no_news(self):
        for edition in ("interior", "exterior"):
            context = self.context(edition)
            target = context.runtime_dir / "search_results.csv"
            sheet = target.with_name("sheet2_llm_targets.csv")
            sheet.write_text("PREVIOUS SELECTION", encoding="utf-8")
            raw = collector.pd.DataFrame([self.row(2, False)])
            with patch.object(collector, "EDITION", context), patch.object(collector, "summarize_article", return_value=("English title", "English body.")), redirect_stdout(io.StringIO()):
                with self.assertRaises(SummaryQuarantineError):
                    collector.build_sheet2_and_csv(raw, target, ["2026-09-16"])
                result = dict(collector.SHEET2_RESULT)
                with patch.object(collector, "_main"):
                    with self.assertRaises(SummaryQuarantineError):
                        collector.main()
            self.assertEqual(sheet.read_text(encoding="utf-8"), "PREVIOUS SELECTION")
            self.assertEqual(result["selected_count"], 0)
            self.assertEqual(result["quarantined_count"], 1)
            self.assertEqual(collector.pd.read_csv(target)["LLM後処理"].iloc[0], "日本語化失敗")
            self.assertFalse((context.runtime_dir / "collection_result.json").exists())

    def test_failed_state_must_be_saved_before_valid_selection_can_replace_sheet(self):
        context = self.context("interior")
        target = context.runtime_dir / "search_results.csv"
        sheet = target.with_name("sheet2_llm_targets.csv")
        sheet.write_text("KEEP", encoding="utf-8")
        with patch.object(collector, "EDITION", context), patch.object(collector, "summarize_article", return_value=("English", "Still English.")), patch.object(collector, "save_with_hyperlinks", side_effect=OSError("storage unavailable")), redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(SummaryQuarantineError, "preserve source rows"):
                collector.build_sheet2_and_csv(collector.pd.DataFrame([self.row(1), self.row(2, False)]), target, ["2026-09-16"])
        self.assertEqual(sheet.read_text(encoding="utf-8"), "KEEP")

    def test_manual_japanese_repair_finds_quarantined_raw_row_without_sheet_filter(self):
        context = self.context("exterior")
        target = context.runtime_dir / "search_results.csv"
        rows = [self.row(1), self.row(2, False), self.row(3, False, "2026-09-15")]
        rows[1]["LLM後処理"] = "日本語化失敗"
        original = collector.pd.DataFrame(rows)
        original.to_csv(target, index=False, encoding="utf-8")
        # The failed row is deliberately absent from Sheet2.
        original.iloc[:1].to_csv(target.with_name("sheet2_llm_targets.csv"), index=False, encoding="utf-8")
        cwd = Path.cwd()
        self.addCleanup(os.chdir, cwd)
        argv = ["collector", "--dept", "exterior", "--repair-target-dates", "--repair-japanese-only", "--dates", "2026-09-16"]
        with patch.multiple(collector, EDITION=context, EXCEL_FILE=str(target), LEGACY_EXCEL_FILE=str(target.with_suffix(".xlsx")),
                            ENRICH_ONLY=False, ENRICH_EXISTING=False, COUNTRY_SETTINGS={}, RSS_FEEDS=[]), \
                patch.object(collector, "configure_edition"), patch.object(collector, "build_rss_feed_list"), \
                patch.object(collector, "load_existing_data", return_value=original.copy()), \
                patch.object(collector, "summarize_article", side_effect=lambda title, *args: ("グリルの設計を更新", "グリルの意匠を改良した。") if title.endswith("2") else (title, args[0])) as summarize, \
                patch.object(collector, "fetch_from_rss", side_effect=AssertionError("No recollection during repair")), \
                patch.object(sys, "argv", argv), redirect_stdout(io.StringIO()):
            collector.main()
        stored = collector.pd.read_csv(target, keep_default_na=False)
        repaired = stored[stored["URL"].eq(rows[1]["URL"])].iloc[0]
        self.assertEqual(repaired["LLM後処理"], "補完")
        self.assertEqual(repaired["タイトル"], rows[1]["タイトル"])
        self.assertIn(rows[1]["URL"], collector.pd.read_csv(target.with_name("sheet2_llm_targets.csv"))["URL"].tolist())
        # Explicit repair first calls only the requested raw failed row. Final
        # exterior selection may also attempt older in-window candidates.
        self.assertEqual(summarize.call_args_list[0].args[0], rows[1]["タイトル"])
        self.assertTrue(json.loads((context.runtime_dir / "collection_result.json").read_text(encoding="utf-8"))["completed"])

    def test_language_policy_matches_publisher_and_preserves_curated_papers(self):
        import auto_update_daily_news as publisher
        for country, title, body in (("jp", "新型車発表", "内装を紹介した。"),
                                     ("eu", "WHAT・COPY", "Still English."),
                                     ("cn", "新車発表", "纯中文内容"),
                                     ("paper", "Study title", "Study abstract")):
            problem = summary_language_problem(country, title, body)
            item = {"country": country, "title": title, "desc": body}
            if problem:
                with self.assertRaises(RuntimeError):
                    publisher.validate_japanese_news_items([item])
            else:
                publisher.validate_japanese_news_items([item])

    def test_true_zero_match_exterior_still_has_a_completed_no_news_receipt(self):
        context = self.context("exterior")
        target = context.runtime_dir / "search_results.csv"
        with patch.object(collector, "EDITION", context), \
                patch.object(collector, "summarize_article", side_effect=AssertionError("No selected summaries to repair")), \
                redirect_stdout(io.StringIO()):
            collector.build_sheet2_and_csv(collector.pd.DataFrame([self.row(1, day="2026-09-01")]), target, ["2026-09-16"])
            self.assertEqual(collector.SHEET2_RESULT["selected_count"], 0)
            self.assertEqual(collector.SHEET2_RESULT["quarantined_count"], 0)
            with patch.object(collector, "_main"):
                collector.main()
        receipt = json.loads((context.runtime_dir / "collection_result.json").read_text(encoding="utf-8"))
        self.assertTrue(receipt["completed"])
        self.assertEqual(receipt["selected_count"], 0)
        self.assertEqual(receipt["source_dates"], [])
        self.assertTrue(collector.pd.read_csv(target.with_name("sheet2_llm_targets.csv")).empty)
        self.assertEqual(validated_issue_context(receipt, [])["selected_by_country"], {})

    def test_normal_collector_does_not_swallow_all_failed_existing_rows(self):
        context = self.context("exterior")
        target = context.runtime_dir / "search_results.csv"
        original = collector.pd.DataFrame([self.row(2, False)])
        original.to_csv(target, index=False, encoding="utf-8")
        cwd = Path.cwd()
        self.addCleanup(os.chdir, cwd)
        with patch.multiple(collector, EDITION=context, EXCEL_FILE=str(target), LEGACY_EXCEL_FILE=str(target.with_suffix(".xlsx")),
                            ENRICH_ONLY=False, ENRICH_EXISTING=False, COUNTRY_SETTINGS={}, RSS_FEEDS=[], ONLY_PAPERS_RSS=True), \
                patch.object(collector, "configure_edition"), patch.object(collector, "build_rss_feed_list"), \
                patch.object(collector, "load_existing_data", return_value=original.copy()), \
                patch.object(collector, "summarize_article", return_value=("English title", "Still English.")), \
                patch.object(collector, "fetch_from_rss", return_value=[]), \
                patch.object(sys, "argv", ["collector", "--dept", "exterior", "--dates", "2026-09-16"]), redirect_stdout(io.StringIO()):
            with self.assertRaises(SummaryQuarantineError):
                collector.main()
        receipt = json.loads((context.runtime_dir / "collection_result.json").read_text(encoding="utf-8"))
        self.assertFalse(receipt["completed"])
        self.assertFalse(target.with_name("sheet2_llm_targets.csv").exists())


if __name__ == "__main__":
    unittest.main()
