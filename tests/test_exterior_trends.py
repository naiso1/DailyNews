"""Exterior editorial lanes and calendar boundaries; all model/network calls mocked."""
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
from dailynews import exterior
from dailynews.editions import get_edition


class ExteriorTrendRulesTests(unittest.TestCase):
    def test_market_and_material_evidence_can_qualify_without_a_part_name(self):
        for title, text, topic in (
            ("India passenger car sales", "SUV segment share rose to 55% in August.", "market"),
            ("自動車用再生樹脂", "樹脂メーカーが再生材の供給計画を公表した。", "materials"),
            ("Vehicle pedestrian protection regulations", "New safety standards take effect in 2028.", "regulation"),
            ("New Toyota model strategy", "The automaker will launch three passenger car models.", "competitor"),
            ("Car design direction", "The concept vehicle previews a new styling direction.", "design"),
        ):
            with self.subTest(topic=topic):
                self.assertEqual(exterior.news_category(title, text, "trend", topic), ("trend", topic))
                self.assertEqual(exterior.calibrate_score(78, title, text, category="trend", trend_topic=topic)[0], 78)

    def test_unrelated_or_invented_context_cannot_remove_the_score_cap(self):
        self.assertEqual(exterior.calibrate_score(90, "Restaurant market growth", "Meal sales rose 10%.",
                                                   category="trend", trend_topic="market")[0], 35)
        self.assertEqual(exterior.calibrate_score(90, "Battery capacity", "Energy density increased.",
                                                   summary="自動車の販売台数とグリルが増えた。")[0], 35)
        self.assertEqual(exterior.calibrate_score(90, "Ford stock price", "Quarterly earnings were announced.",
                                                   category="trend", trend_topic="market")[0], 35)
        self.assertEqual(exterior.news_category("Passenger car sales", "SUV demand rose.", "trend", "unknown"), ("", ""))


class ExteriorTrendPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global collector, updater
        import google_search_script as collector
        import auto_update_daily_news as updater

    def setUp(self):
        collector.configure_edition("exterior")
        updater.configure_edition("exterior")

    def tearDown(self):
        collector.configure_edition("interior")
        updater.configure_edition("interior")

    def test_jst_calendar_boundary_and_interior_compatibility(self):
        self.assertEqual(collector.parse_date("2026-09-14T21:10:00Z"), "2026-09-15")
        self.assertEqual(collector.parse_date("2026-09-15T14:59:59Z"), "2026-09-15")
        self.assertEqual(collector.parse_date("2026-09-15T15:00:00Z"), "2026-09-16")
        self.assertEqual(collector.parse_date("2026-09-15"), "2026-09-15")
        self.assertEqual(collector.parse_date("2026-09-15T06:10:00+09:00"), "2026-09-15")
        collector.configure_edition("interior")
        self.assertEqual(collector.parse_date("2026-09-14T21:10:00Z"), "2026-09-14")
        self.assertEqual(collector.search_date_clause(["2026-09-14"]), "when:1d")

    def test_search_and_candidate_limits_keep_a_trend_lane(self):
        settings = {"keywords": ["grille", "bumper", "emblem"], "trend_keywords": ["car sales", "car design"]}
        self.assertEqual(collector.edition_search_keywords(settings, 4), ["grille", "car sales", "bumper", "car design"])
        products = [{"国": "日本", "タイトル": f"グリル バンパー エンブレム 樹脂設計 {index}", "内容": "部品を開発。", "URL": str(index)} for index in range(10)]
        trend = {"国": "日本", "タイトル": "Passenger car market share", "内容": "SUV sales rose 20%.", "URL": "trend"}
        picked = collector.prefilter_results_for_enrichment(products + [trend], 6)
        self.assertEqual(len(picked), 6)
        self.assertIn(trend, picked)

    def test_first_relevance_decision_sees_article_body(self):
        body = "Passenger car sales shifted toward SUVs in August, reaching 55 percent of registrations. " * 3
        item = {"国": "インド", "タイトル": "August market report", "内容": "A monthly report.", "URL": "https://example.com/market", "画像URL": "", "ソース": "RSS"}
        assessment = {"score": 78, "reason": "乗用車の車種別需要の変化", "category": "trend", "trend_topic": "market"}
        with patch.multiple(collector, USE_LLM=True, FETCH_MISSING_IMAGES=False), patch.object(collector, "fetch_article_text", return_value=body), patch.object(collector, "check_url_ok", return_value=True), patch.object(collector, "call_llm_classify", return_value=("対象", "なし")) as classifier, patch.object(collector, "summarize_article", return_value=("乗用車の需要構成が変化", "SUVの販売構成比が変わった。")), patch.object(collector, "call_llm_interior_assessment", return_value=assessment), redirect_stdout(io.StringIO()):
            result = collector.enrich_results([item])
        self.assertEqual(classifier.call_args_list[0].args[1], body)
        self.assertEqual(result[0]["記事区分"], "trend")
        self.assertEqual(result[0]["トレンド分類"], "market")

    def test_assistant_prefix_continuation_preserves_explicit_trend_category(self):
        response = Mock(status_code=200, json=Mock(return_value={"choices": [{"message": {"content":
            '78,"reason":"乗用車の需要構成","category":"trend","trend_topic":"market","image_interior":null}'}}]}))
        with patch.object(collector, "_post_llm", return_value=response):
            result = collector.call_llm_interior_assessment("Passenger car market report", "SUV demand changed, including grille customization.")
        self.assertEqual(result["score"], 78)
        self.assertEqual(result["category"], "trend")
        self.assertEqual(result["trend_topic"], "market")

    @staticmethod
    def rows(products, trends):
        rows = []
        for category, count in (("product", products), ("trend", trends)):
            for index in range(count):
                title = f"グリル部品の開発情報{index}" if category == "product" else f"乗用車市場の販売構成{index}"
                body = "グリルの設計を公表した。" if category == "product" else "乗用車の販売構成が変化した。"
                rows.append({"国": "日本", "日付": "2026-09-15", "タイトル": title, "内容": body,
                             "タイトル（日本語）": title, "内容（日本語）": body, "URL": f"https://example.com/{category}/{index}",
                             "LLM判定": "対象", "内装関連度": 90-index, "LLM後処理": "実施", "記事区分": category,
                             "トレンド分類": "market" if category == "trend" else "", "画像URL": ""})
        return rows

    def test_balanced_selection_and_diagnostic_counts_do_not_backfill(self):
        for products, trends, expected in ((8, 6, {"product": 6, "trend": 4}), (2, 8, {"product": 2, "trend": 4}), (8, 1, {"product": 8, "trend": 1})):
            with self.subTest(products=products, trends=trends), tempfile.TemporaryDirectory() as folder:
                rows = self.rows(products, trends)
                rows.append({**rows[0], "URL": "https://example.com/rejected", "LLM判定": "非対象", "内装関連度": 99})
                rows.append({**rows[0], "URL": "https://example.com/old", "日付": "2026-09-14"})
                target = Path(folder) / "search_results.csv"
                with patch.object(collector, "is_same_topic_text", return_value=False), patch.object(collector, "SHEET2_SIMILARITY_THRESHOLD", 1.1), patch.object(collector, "summarize_article", side_effect=AssertionError("Unexpected LLM call")), redirect_stdout(io.StringIO()):
                    collector.build_sheet2_and_csv(collector.pd.DataFrame(rows), target, ["2026-09-15"])
                self.assertEqual(collector.SHEET2_RESULT["selected_by_category"], expected)
                self.assertEqual(collector.SHEET2_RESULT["candidate_count"], products+trends+1)
                self.assertEqual(collector.SHEET2_RESULT["selection_outcomes"]["not_relevant_or_unclassified"], 1)
                self.assertTrue(target.with_name("selection_review.csv").exists())

    def test_reassessment_preserves_other_days_and_reconsiders_prior_targets(self):
        rows = self.rows(2, 1)
        rows.append({**rows[0], "日付": "2026-09-14", "URL": "https://example.com/old"})
        kept, candidates = collector.split_exterior_reassessment(collector.pd.DataFrame(rows), ["2026-09-15"])
        self.assertEqual(kept["URL"].tolist(), ["https://example.com/old"])
        self.assertEqual(len(candidates), 3)
        self.assertTrue(all(item["_previous_target"] and item["LLM判定"] == "" for item in candidates))
        self.assertEqual({item["URL"] for item in candidates}, {row["URL"] for row in rows[:3]})

    def test_market_items_have_citable_idea_anchors(self):
        item = {"newsId": "in7", "title": "乗用車の販売構成", "desc": "SUVの需要が増えた。", "contentCategory": "trend", "trendTopic": "market"}
        groups = updater.select_idea_anchor_groups([item], 2)
        self.assertEqual([[entry["newsId"] for entry in group] for group in groups], [["in7"], ["in7"]])
        prompt = updater.make_country_prompt("2026-09-15", "in", [item], "", idea_anchor_groups=groups)
        self.assertIn("trend/market", prompt)
        self.assertIn("仮説", prompt)


if __name__ == "__main__":
    unittest.main()
