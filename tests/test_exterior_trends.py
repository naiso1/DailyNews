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
from unittest.mock import MagicMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ニュース収集"))
from dailynews import exterior
from dailynews.editions import get_edition


class ExteriorTrendRulesTests(unittest.TestCase):
    def test_insight_context_contains_both_lanes_when_product_scores_are_higher(self):
        products = [{"newsId": f"jp{index}", "title": "グリル", "desc": "製品の設計。", "interiorScore": 90,
                     "contentCategory": "product"} for index in range(1, 7)]
        trends = [{"newsId": f"jp{index}", "title": "乗用車市場", "desc": "需要の変化。", "interiorScore": 70,
                   "contentCategory": "trend", "trendTopic": "market"} for index in range(7, 10)]
        selected = exterior.select_items(products + trends, 6)
        self.assertEqual(len(selected), 6)
        self.assertEqual(sum(item["contentCategory"] == "trend" for item in selected), 2)
        self.assertEqual(exterior.select_items(products, 6), products)

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

    def test_exterior_does_not_merge_jsw_and_bmw_on_generic_summary_words(self):
        # Actual collection summaries: the shared words were only
        # バッテリー / 発揮 / 同車 / 投入, despite covering independent vehicles.
        jsw = "JSW Combat、初SUVにプラグインハイブリッド採用 JSW Motorsは、中国Cheryと提携し初のSUV「JSW Combat」をDiwali前後に投入する。同車はJetour T2を基盤とし、1.5Lターボエンジンと18.4kWhバッテリーで構成されるPHEVシステムを搭載し、総出力360bhpを発揮する見込みである。"
        bmw = "BMW i5 LWB、インドで796万ルピーから発売開始 BMWはインド市場向けにi5 LWBを796万ルピー（車両価格）から投入した。同車は現行のインド市場における唯一のロングホイールベースEVセダンであり、Chennai工場で組立生産されている。外装にはIlluminated Kidney GrilleやM専用バンパーなどを採用し、81.6kWhバッテリーと268bhpモーターを搭載して最高出力を発揮する。"
        self.assertFalse(collector.is_same_topic_text(jsw, bmw))
        self.assertTrue(collector.is_same_topic_text(jsw, jsw + " 詳細を報じた。"))
        collector.configure_edition("interior")
        self.assertTrue(collector.is_same_topic_text(jsw, bmw))

    def test_exterior_still_merges_distinct_reports_of_same_volvo_models(self):
        european = "ボルボXC60とXC90に長距離PHEV追加、米市場で最大78マイルのEV航続 ボルボはXC60とXC90に長距離プラグインハイブリッドを追加し、米国向けにそれぞれ最大78マイル・73マイルのEV航続を確保した。XC60ではグリルやバンパー、ヘッドライトなど外装デザインも刷新されている。"
        indian = "ボルボXC60・XC90フェイスリフト、41.2kWhバッテリー採用 ボルボは国際仕様のXC60とXC90のPHEVモデルを刷新し、両車に41.2kWhバッテリーを搭載した。XC60はT字型LED DRLや新グリルなど外装を更新し、WLTP基準で最大200kmのEV航続距離を実現している。"
        self.assertTrue(collector.is_same_topic_text(european, indian))

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

    def test_exterior_google_search_keeps_all_original_and_trend_queries(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(collector.google_news_keyword_limit(), 15)
            for settings in collector.COUNTRY_SETTINGS.values():
                queries = collector.edition_search_keywords(settings, collector.google_news_keyword_limit())
                self.assertEqual(len(queries), 15)
                self.assertTrue(set(settings["keywords"]).issubset(queries))
                self.assertTrue(set(settings["trend_keywords"]).issubset(queries))
            collector.configure_edition("interior")
            self.assertEqual(collector.google_news_keyword_limit(), collector.GOOGLE_NEWS_KEYWORD_LIMIT)
        collector.configure_edition("exterior")
        with patch.dict(os.environ, {"GOOGLE_NEWS_KEYWORD_LIMIT": "3"}), patch.object(collector, "GOOGLE_NEWS_KEYWORD_LIMIT", 3):
            self.assertEqual(collector.google_news_keyword_limit(), 3)

    def test_google_redirect_keeps_s_characters_and_rejects_image_urls(self):
        source = "https://news.google.com/articles/test"
        article = "https://news.example.com/news/exterior-styling"
        manager = MagicMock()
        page = manager.__enter__.return_value.chromium.launch.return_value.new_page.return_value
        page.url = source
        page.locator.return_value.first.count.return_value = 0
        page.content.return_value = (
            '<img src="https://lh3.googleusercontent.com/news-logo.svg">'
            '<img src="https://images.example.com/automotive.jpg">'
            '<script src="https://www.google-analytics.com/analytics.js"></script>'
            '<script src="https://unrelated.example.com/ad-endpoint"></script>'
            f'<a href="{article}">Exterior news</a>'
        )
        with patch.multiple(collector, PLAYWRIGHT_AVAILABLE=True, USE_PLAYWRIGHT=True), \
                patch.object(collector, "sync_playwright", return_value=manager, create=True):
            final_url, image = collector.resolve_with_playwright(source)
        self.assertEqual(final_url, article)
        self.assertIsNone(image)
        self.assertFalse(collector.is_valid_article_url("https://lh3.googleu", allow_google_news=False))
        self.assertFalse(collector.is_valid_article_url("https://cdn.example.com/news.png?size=large", allow_google_news=False))
        self.assertFalse(collector.is_valid_article_url("https://cdn.example.com/analytics.js", allow_google_news=False))
        self.assertTrue(collector.is_valid_article_url(article, allow_google_news=False))
        page.content.return_value = '<script src="https://unrelated.example.com/ad-endpoint"></script><a href="https://cdn.example.com/logo.svg">Logo</a>'
        with patch.multiple(collector, PLAYWRIGHT_AVAILABLE=True, USE_PLAYWRIGHT=True), \
                patch.object(collector, "sync_playwright", return_value=manager, create=True):
            self.assertEqual(collector.resolve_with_playwright(source), (None, None))

    def test_first_relevance_decision_sees_article_body(self):
        body = "Passenger car sales shifted toward SUVs in August, reaching 55 percent of registrations. " * 3
        item = {"国": "インド", "タイトル": "August market report", "内容": "A monthly report.", "URL": "https://example.com/market", "画像URL": "", "ソース": "RSS"}
        assessment = {"score": 78, "reason": "乗用車の車種別需要の変化", "category": "trend", "trend_topic": "market"}
        with patch.multiple(collector, USE_LLM=True, FETCH_MISSING_IMAGES=False), patch.object(collector, "fetch_article_text", return_value=body), patch.object(collector, "check_url_ok", return_value=True), patch.object(collector, "call_llm_classify", return_value=("対象", "なし")) as classifier, patch.object(collector, "summarize_article", return_value=("乗用車の需要構成が変化", "SUVの販売構成比が変わった。")), patch.object(collector, "call_llm_interior_assessment", return_value=assessment), redirect_stdout(io.StringIO()):
            result = collector.enrich_results([item])
        self.assertEqual(classifier.call_args_list[0].args[1], body)
        self.assertEqual(result[0]["記事区分"], "trend")
        self.assertEqual(result[0]["トレンド分類"], "market")

    def test_compact_headline_preserves_trend_subject_without_interior_focus(self):
        with patch.object(collector, "call_llm_text", return_value="SUVの販売構成比が55％に上昇") as model:
            collector.compact_title_with_llm("Passenger car sales", "SUV share rose to 55% in August.", "乗用車市場の動向")
        prompt = model.call_args.args[0]
        self.assertIn("market", prompt)
        self.assertIn("do not invent component details", prompt)
        self.assertNotIn("automotive-interior", prompt)
        collector.configure_edition("interior")
        with patch.object(collector, "call_llm_text", return_value="新型車がシートの調整機構を採用") as model:
            collector.compact_title_with_llm("New vehicle seat", "A seat adjustment mechanism was announced.", "新しい座席を発表")
        self.assertIn("automotive-interior", model.call_args.args[0])

    def test_summary_detail_dispatch_does_not_apply_interior_topics_to_exterior(self):
        from summary_grounding import summary_omits_interior_details
        source = "乗用車の市場シェアが変化した。シートとディスプレイを備える車種が対象。"
        summary = "乗用車の市場シェアが変化した。"
        self.assertFalse(summary_omits_interior_details(summary, source))
        self.assertFalse(summary_omits_interior_details("SUVの販売構成比が55％に上昇した。", "Passenger car sales: SUV share rose to 55%."))
        self.assertTrue(summary_omits_interior_details("新型グリルを採用した。", "グリルとバンパーの構造を変更した。"))
        collector.configure_edition("interior")
        self.assertTrue(summary_omits_interior_details(summary, source))

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

    def test_corrected_next_day_candidate_survives_url_dedup_without_new_llm(self):
        with tempfile.TemporaryDirectory() as directory:
            context = get_edition("exterior", directory)
            context.config_dir.mkdir(parents=True)
            context.collection_settings_path.write_text(json.dumps({"exterior": {"selection": {"minimum_score": 60, "trend_minimum_score": 65, "require_original_image": False}}}), encoding="utf-8")
            context.ensure_directories()
            target = context.runtime_dir / "search_results.csv"
            row = {**self.rows(1, 0)[0], "日付": "2026-09-16"}
            collector.pd.DataFrame([row]).to_csv(target, encoding="utf-8-sig", index=False)
            argv = ["collector", "--dept", "exterior", "--dates", "2026-09-16"]
            log = io.StringIO()
            with patch.object(collector, "configure_edition"), patch.object(collector.os, "chdir"), \
                    patch.multiple(collector, EDITION=context, EXCEL_FILE=str(target), LEGACY_EXCEL_FILE=str(target.with_suffix(".xlsx")),
                                   ENRICH_ONLY=False, ENRICH_EXISTING=False, ONLY_PAPERS_RSS=False, ENABLE_GOOGLE_NEWS=False), \
                    patch.object(sys, "argv", argv), patch.object(collector, "build_rss_feed_list"), \
                    patch.object(collector, "fetch_from_rss", return_value=[row.copy()]), \
                    patch.object(collector, "fetch_from_bing_search", return_value=[]), \
                    patch.object(collector, "fetch_from_duckduckgo", return_value=[]), \
                    patch.object(collector, "fetch_from_newsapi", return_value=[]), \
                    patch.object(collector, "enrich_results", side_effect=AssertionError("Duplicate URL must reuse its completed assessment")), \
                    patch.object(collector, "summarize_article", side_effect=AssertionError("Stored summary must be reused")), redirect_stdout(log):
                collector._main()
            self.assertEqual(collector.COLLECTION_METRICS["duplicate_reasons"], {"既存URL": 1})
            self.assertEqual(collector.SHEET2_RESULT["selected_count"], 1, log.getvalue() + str(collector.SHEET2_RESULT))
            with target.with_name("sheet2_llm_targets.csv").open(encoding="utf-8-sig", newline="") as handle:
                selected = list(csv.DictReader(handle))
            self.assertEqual(selected[0]["URL"], row["URL"])
            self.assertEqual(selected[0]["日付"], "2026-09-16")

    def test_market_items_have_citable_idea_anchors(self):
        item = {"newsId": "in7", "title": "乗用車の販売構成", "desc": "SUVの需要が増えた。", "contentCategory": "trend", "trendTopic": "market"}
        groups = updater.select_idea_anchor_groups([item], 2)
        self.assertEqual([[entry["newsId"] for entry in group] for group in groups], [["in7"], ["in7"]])
        prompt = updater.make_country_prompt("2026-09-15", "in", [item], "", idea_anchor_groups=groups)
        self.assertIn("trend/market", prompt)
        self.assertIn("仮説", prompt)

    def test_csv_category_reaches_js_and_existing_url_keeps_its_id_across_dates(self):
        with tempfile.TemporaryDirectory() as directory:
            context = get_edition("exterior", directory)
            context.config_dir.mkdir(parents=True)
            context.collection_settings_path.write_text(json.dumps({"exterior": {"selection": {"minimum_score": 60, "trend_minimum_score": 65}, "image_generation": {"enabled": False, "provider": "none"}}}), encoding="utf-8")
            context.ensure_directories()
            rows = self.rows(1, 1)
            sheet = context.runtime_dir / "sheet2_llm_targets.csv"
            with sheet.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            news = context.content_dir / "news_data.js"
            news.write_text('window.LOADED_NEWS_DATA = [\n{ id: "jp9", title: "既存のグリル", desc: "グリルを紹介する。", url: "https://example.com/product/0", date: "2026-09-14", country: "jp" },\n];\n', encoding="utf-8")
            (context.runtime_dir / "collection_result.json").write_text(json.dumps({"edition_id": "exterior", "completed": True, "source_count": 1, "selected_count": 2, "target_dates": ["2026-09-15"]}), encoding="utf-8")
            argv = ["publisher", "--edition", "exterior", "--sheet", str(sheet), "--skip-insights", "--skip-html"]
            with patch.multiple(updater, EDITION=context, NEWS_PATH=news, INSIGHTS_PATH=context.content_dir / "insights_data.js"), patch.object(sys, "argv", argv), patch("ニュース収集.source_highlights.enrich_items"), redirect_stdout(io.StringIO()):
                updater.main()
            output = news.read_text(encoding="utf-8")
            self.assertEqual(output.count('https://example.com/product/0'), 1)
            self.assertIn('id: "jp9"', output)
            self.assertIn('date: "2026-09-14"', output)
            self.assertIn('id: "jp10"', output)
            self.assertIn('contentCategory: "trend", trendTopic: "market"', output)


if __name__ == "__main__":
    unittest.main()
