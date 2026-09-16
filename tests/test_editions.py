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
        self.assertTrue(exterior_context.image_generation["enabled"])
        self.assertEqual(exterior_context.image_generation["provider"], "exabase")
        self.assertEqual(exterior_context.image_generation["max_images"], 4)
        self.assertNotEqual(exterior_context.image_generation["provider"], "gemini")
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

    def test_exterior_material_and_aero_synonyms_preserve_two_topics(self):
        # Paraphrased fixtures: the checks must work in both translation directions.
        for source, summary in (
            ("Carbon fiber grille inserts accompany a carbon-fiber splitter and an aramid diffuser.",
             "カーボンファイバー製スプリッターとアラミド製ディフューザーを用意する。"),
            ("A carbon fibre front splitter is available.", "炭素繊維製フロントスプリッタを設定する。"),
            ("The painted rear spoiler is optional.", "塗装したリアスポイラーを選択できる。"),
            ("エンブレムを変え、パノラマルーフのメッシュディフレクターで風切り音を抑える。",
             "エンブレムを刷新し、メッシュディフレクタで風切り音を抑える。"),
            ("炭素繊維製スプリッターとアラミド製ディフューザーを追加する。",
             "Carbon-fibre splitters and aramid diffusers are offered."),
        ):
            with self.subTest(summary=summary):
                self.assertFalse(summary_omits_interior_details(summary, source))

    def test_exterior_synonyms_do_not_accept_missing_material_or_product_details(self):
        source = "Carbon fiber grille inserts accompany an aramid diffuser and a front splitter."
        for summary in (
            "新型車の販売価格と発売時期を発表した。",
            "ディフューザーとスプリッターを用意する。",  # Only the aero topic remains.
            "カーボンファイバーとアラミドを使用する。",  # Only the material topic remains.
            "空力性能を訴求し、炭素排出量を削減する。",  # Carbon emissions are not carbon fiber.
        ):
            with self.subTest(summary=summary):
                self.assertTrue(summary_omits_interior_details(summary, source))

    def test_exterior_aero_parts_are_in_product_and_collection_scope(self):
        keywords = get_edition("exterior").config["keywords"]
        for term in ("スポイラー", "ディフューザー", "スプリッター", "ディフレクター",
                     "spoiler", "diffuser", "splitter", "deflector"):
            with self.subTest(term=term):
                self.assertTrue(exterior.has_product_details(term))
                self.assertEqual(exterior.calibrate_score(80, term)[0], 80)
                self.assertTrue(any(keyword.lower() in term.lower() for keyword in keywords))
        self.assertFalse(exterior.has_product_details("carbon fiber material"))

    def test_exterior_source_quote_matches_exterior_parts(self):
        from ニュース収集.source_highlights import choose_excerpt, fingerprint
        item = {"edition": "exterior", "title": "新しいグリルとバンパー", "desc": "グリルとバンパーの設計を刷新した。"}
        paragraph = "The redesigned grille and bumper integrate exterior lighting with radar-transparent materials."
        result = choose_excerpt(item, ["The interior has a display and heated seats for passengers.", paragraph])
        self.assertIn(result["sourceExcerpt"], paragraph)
        self.assertNotEqual(fingerprint(item), fingerprint({**item, "edition": "interior"}))

    def test_exterior_two_ideas_can_share_one_source(self):
        item = {"newsId": "jp1", "title": "発光グリル", "desc": "発光グリルの設計を公開した。", "exteriorScore": 80}
        groups = updater.select_idea_anchor_groups([item], need_count=2)
        self.assertEqual([[entry["newsId"] for entry in group] for group in groups], [["jp1"], ["jp1"]])
        prompt = updater.make_country_prompt("2026-09-14", "jp", [item], "外装開発", need_count=2)
        self.assertIn("ideas[0] anchor IDs: jp1", prompt)
        self.assertIn("ideas[1] anchor IDs: jp1", prompt)
        ideas = [{"title": "案一", "desc": "グリルを提案する。 [jp1]", "sourceNewsIds": ["jp1"]},
                 {"title": "案二", "desc": "グリルの補修部品を提案する。 [jp1]", "sourceNewsIds": ["jp1"]}]
        result = updater.prepare_exterior_idea_sources(ideas, [item])
        self.assertEqual([idea["sourceNewsIds"] for idea in result], [["jp1"], ["jp1"]])
        self.assertTrue(all(idea["desc"].endswith("[jp1]") for idea in result))
        # Repair legacy checkpoints whose second citation was removed by the old anchor loop.
        ideas[1]["sourceNewsIds"] = []
        result = updater.prepare_exterior_idea_sources(ideas, [item])
        self.assertEqual(result[1]["sourceNewsIds"], ["jp1"])

    def test_exterior_idea_rejects_unknown_or_unavailable_sources(self):
        item = {"newsId": "jp1", "title": "発光グリル", "desc": "発光グリルの設計を公開した。"}
        for ids in (["jp999"], ["jp1", "jp999"], ["cn1"]):
            with self.subTest(ids=ids), self.assertRaisesRegex(RuntimeError, "unknown news IDs"):
                updater.prepare_exterior_idea_sources([{"desc": "グリル案", "sourceNewsIds": ids}], [item])
        with self.assertRaisesRegex(RuntimeError, "no valid source article"):
            updater.prepare_exterior_idea_sources([{"desc": "グリル案", "sourceNewsIds": []}], [])

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
                self.assertEqual([idea["sourceNewsIds"] for idea in checkpoint["countries"]["jp"]["ideas"]], [["jp1"], ["jp1"]])
                checkpoint["countries"]["jp"]["ideas"][1]["sourceNewsIds"] = []
                updater.write_exterior_checkpoint("2026-09-14", checkpoint)
                failed.clear()
                llm.reset_mock()
                updater.main()
                self.assertEqual([call.args[2] for call in llm.call_args_list], ["cn"])
                self.assertEqual(json.loads(marker.read_text(encoding="utf-8"))["status"], "published")
                self.assertIn('jp: "', insights.read_text(encoding="utf-8"))
                self.assertIn('cn: "', insights.read_text(encoding="utf-8"))
                output = insights.read_text(encoding="utf-8")
                self.assertEqual(output.count('sourceNewsIds: ["jp1"]'), 2)
                self.assertEqual(output.count('sourceNewsIds: ["cn1"]'), 2)
                self.assertNotIn('sourceNewsIds: []', output)


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

    @staticmethod
    def llm_response(content, status=200):
        return Mock(status_code=status, text="test response", json=Mock(return_value={"choices": [{"message": {"content": content}}]}))

    def test_invalid_required_relevance_is_not_cached_or_reused(self):
        key = ("grille", "", "", "relevance")
        collector.LLM_CACHE[key] = ("", "")
        responses = [self.llm_response('{}'), self.llm_response('{"relevance":false}')]
        with patch.multiple(collector, USE_LLM=True, PROMPT_TEXT="test prompt", LLM_ERROR_LOGGED=False), patch.object(collector, "_post_llm", side_effect=responses) as request, redirect_stdout(io.StringIO()):
            self.assertEqual(collector.call_llm_classify("grille", "", mode="relevance"), ("", ""))
            self.assertNotIn(key, collector.LLM_CACHE)
            self.assertEqual(collector.EXTERIOR_REQUIRED_LLM_ERRORS["relevance"], 1)
            self.assertEqual(collector.call_llm_classify("grille", "", mode="relevance"), ("非対象", ""))
            self.assertEqual(request.call_count, 2)
            self.assertEqual(collector.EXTERIOR_REQUIRED_LLM_ERRORS["relevance"], 1)

    def test_invalid_required_score_is_not_cached_or_reused(self):
        key = ("exterior", "product_assessment", "grille", "", "", "", "")
        collector.LLM_CACHE[key] = {"score": None}
        responses = [self.llm_response('{}'), self.llm_response('{"score":20,"reason":"weak relevance"}')]
        with patch.multiple(collector, USE_LLM=True, LLM_IMAGE_INPUT=False, LLM_ERROR_LOGGED=False), patch.object(collector, "_post_llm", side_effect=responses) as request, redirect_stdout(io.StringIO()):
            self.assertIsNone(collector.call_llm_interior_assessment("grille", ""))
            self.assertNotIn(key, collector.LLM_CACHE)
            self.assertEqual(collector.EXTERIOR_REQUIRED_LLM_ERRORS["score"], 1)
            self.assertEqual(collector.call_llm_interior_assessment("grille", "")["score"], 20)
            self.assertEqual(request.call_count, 2)
            self.assertEqual(collector.EXTERIOR_REQUIRED_LLM_ERRORS["score"], 1)

    def test_optional_photo_errors_do_not_count_as_required_failures(self):
        with patch.multiple(collector, USE_LLM=True, PROMPT_TEXT="test prompt", LLM_IMAGE_INPUT=False, LLM_ERROR_LOGGED=False), patch.object(collector, "_post_llm", return_value=self.llm_response('{}', 503)), redirect_stdout(io.StringIO()):
            collector.call_llm_classify("grille", "", mode="photo")
            self.assertTrue(collector.LLM_ERROR_LOGGED)
            self.assertEqual(sum(collector.EXTERIOR_REQUIRED_LLM_ERRORS.values()), 0)

    def test_required_http_and_connection_failures_are_counted(self):
        failures = [self.llm_response('{}', 503), ConnectionError("model unavailable")]
        with patch.multiple(collector, USE_LLM=True, PROMPT_TEXT="test prompt", LLM_IMAGE_INPUT=False, LLM_ERROR_LOGGED=False), patch.object(collector, "_post_llm", side_effect=failures), redirect_stdout(io.StringIO()):
            self.assertEqual(collector.call_llm_classify("grille", "", mode="relevance"), ("", ""))
            self.assertIsNone(collector.call_llm_interior_assessment("grille", ""))
            self.assertEqual(collector.EXTERIOR_REQUIRED_LLM_ERRORS, {"relevance": 1, "score": 1})

    def test_zero_collection_fails_for_required_errors_but_partial_selection_is_recorded(self):
        with tempfile.TemporaryDirectory() as directory:
            context = get_edition("exterior", directory)
            context.runtime_dir.mkdir(parents=True)
            receipt = context.runtime_dir / "collection_result.json"
            with patch.multiple(collector, EDITION=context, SOURCE_FETCH_COUNTS={"attempted": 1, "succeeded": 1}, TARGET_DATES_RUN=["2026-09-14"], SHEET2_RESULT={"selected_count": 0, "candidate_count": 3}, LLM_ERROR_LOGGED=True), patch.object(collector, "_main"):
                # Optional photo failures may have set the logging flag, but no
                # required decisions failed: a valid no-match day remains valid.
                collector.main()
                self.assertTrue(json.loads(receipt.read_text(encoding="utf-8"))["completed"])
                collector.EXTERIOR_REQUIRED_LLM_ERRORS["relevance"] = 1
                receipt.write_text('{"completed": false}', encoding="utf-8")
                with self.assertRaisesRegex(RuntimeError, "LLM processing failed"):
                    collector.main()
                self.assertFalse(json.loads(receipt.read_text(encoding="utf-8"))["completed"])
                collector.SHEET2_RESULT["selected_count"] = 1
                collector.main()
                result = json.loads(receipt.read_text(encoding="utf-8"))
                self.assertEqual(result["selected_count"], 1)
                self.assertEqual(result["llm_required_error_count"], 1)
                self.assertEqual(result["llm_required_errors"], {"relevance": 1, "score": 0})

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
        with tempfile.TemporaryDirectory() as folder, patch.object(collector, "published_news", return_value=[]), patch.object(collector, "summarize_article", side_effect=AssertionError("Unexpected LLM call")):
            target = Path(folder) / "search_results.csv"
            collector.build_sheet2_and_csv(collector.pd.DataFrame(rows), target, ["2026-09-14"])
            selected = collector.pd.read_csv(target.with_name("sheet2_llm_targets.csv"))
            self.assertEqual(selected["URL"].tolist(), ["https://example.com/grille"])
            collector.build_sheet2_and_csv(collector.pd.DataFrame(rows), target, ["2026-09-13"])
            self.assertTrue(collector.pd.read_csv(target.with_name("sheet2_llm_targets.csv")).empty)

if __name__ == "__main__":
    unittest.main()
