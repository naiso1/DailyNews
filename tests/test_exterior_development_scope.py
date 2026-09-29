"""Exterior scope and engineering papers; no network or generation in tests."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "ニュース収集")]
from dailynews import exterior, exterior_scope as scope, exterior_papers as papers
from dailynews.collection_digest import published_news, published_row
from dailynews.digest import validated_issue_context
from dailynews.editions import get_edition
from dailynews.llm_budget import budget_exterior_payload


class DevelopmentScopeTests(unittest.TestCase):
    def test_body_transfer_and_performance_are_not_capped_by_old_vocabulary(self):
        samples = [
            ("Vehicle tailgate design", "A lightweight polymer liftgate reduces parts."),
            ("Automotive front-end modules", "Cooling and drag coefficient measurements were compared."),
            ("Steel polymer joining", "Laser processing improves the joint strength in surface tests."),
            ("Automotive NVH", "A new door seal reduces cabin noise."),
            ("汽车车顶和白车身", "通过热冲压工艺实现轻量化。"),
            ("車両の走行安定", "Cd値と揚力の試験結果を示す。"),
        ]
        for title, content in samples:
            with self.subTest(title=title):
                self.assertEqual(exterior.news_category(title, content, "product"), ("product", ""))
                self.assertEqual(exterior.calibrate_score(78, title, content, category="product")[0], 78)
        self.assertEqual(exterior.news_category("IT backdoor", "Cyberattack on banking software", "product"), ("", ""))
        self.assertEqual(exterior.news_category("Kitchen hood", "A home ventilation appliance", "product"), ("", ""))
        self.assertEqual(scope.theme_hits("advanced CNC server"), [])

    def test_transfer_requires_both_fact_and_application_but_no_fixed_numeric_fields(self):
        self.assertEqual(scope.review_fields({"development_lane":"transfer"}, "product")["development_lane"], "exclude")
        fields = scope.review_fields({"development_lane":"transfer", "source_evidence":"鋼と樹脂をレーザー接合", "application":"ルーフの接合に応用できるか検証する"}, "product")
        self.assertEqual(fields["development_lane"], "transfer")
        self.assertFalse(exterior.out_of_scope_idea("ルーフの異材接合を検討する"))

    def test_full_classification_and_image_assessment_fit_running_model_budget(self):
        instructions = scope.SCOPE_TEXT + (ROOT / "editions/exterior/prompts/collection.md").read_text(encoding="utf-8")
        article = "钢塑连接与汽车外饰表面性能。" * 1000
        for prompt, photo in [(instructions + "\n本文:\n" + article, False),
                              (exterior.assessment_prompt("Joining", article, "https://example.com", ""), True)]:
            parts = [{"type":"text", "text":prompt}]
            if photo:
                parts.append({"type":"image_url", "image_url":{"url":"data:image/png;base64,test"}})
            result = budget_exterior_payload({"messages":[{"role":"user", "content":parts}]})
            self.assertIn("钢塑连接", result["messages"][0]["content"][0]["text"])

    def test_all_39_requested_labels_are_preserved(self):
        labels = "冷却 3Dプリンター CN/CE NV 低コスト化 バックドア フェンダー ドア ルーフ リアスポイラー ピラー フード 型内塗装 ホットスタンプ インクジェット フィルム 印刷 メッキ レーザー ミリ波 Lidar カメラ ソナー フロントエンドモジュール 軽量 アブソーバー シームレス 樹脂化 鉄との接合 塗装 歩行者保護 軽衝突 法規 アセス 自動運転 車両骨格 ADAS 走行安定 Cd値".split()
        self.assertEqual(len(labels), 39)
        vocabulary = {word for terms in scope.THEMES.values() for word in terms}
        self.assertTrue(set(labels).issubset(vocabulary))
        config = get_edition("exterior").config
        self.assertEqual(config["development_themes"], {k:list(v) for k,v in scope.THEMES.items()})
        self.assertEqual(config["selection"]["maximum_per_country"], 10)
        self.assertFalse(config["selection"]["fill_quota_with_rejected"])


class PaperSourceTests(unittest.TestCase):
    @staticmethod
    def html(publication="2026/09/10", online="2026/09/12", doi="10.1299/mej.26-12345"):
        return f'''<meta name="citation_title" content="Polymer metal joining for automotive roofs">
        <meta name="citation_doi" content="{doi}">
        <meta name="citation_publication_date" content="{publication}">
        <meta name="citation_online_date" content="{online}">
        <div id="article-overiew-abstract-wrap"><h2>Abstract</h2><p>Laser joining was applied to steel and polymer surfaces. The study compares joint strength under thermal cycling and reports the observed failure modes.</p></div>
        <div>Unrelated references and navigation must not enter the abstract.</div>'''

    def test_notification_resolves_doi_not_journal_home_or_updated_date(self):
        entry = {"title":"The new article is now available", "link":"https://www.jstage.jst.go.jp/browse/mej/",
                 "summary":"[ Title ] Joining [ DOI ] https://doi.org/10.1299/mej.26-12345",
                 "published":"2026-09-10T00:00:00+09:00", "updated":"2026-09-29T03:00:00+09:00"}
        identity = papers.feed_identity(entry)
        self.assertEqual(identity["url"], "https://doi.org/10.1299/mej.26-12345")
        row = papers.parse_article(self.html(), identity, papers.paper_window("2026-09-29"), "2026-09-29")
        self.assertEqual(row["日付"], "2026-09-10")
        self.assertEqual(row["論文公開日"], "2026-09-12")
        self.assertNotIn("references", row["内容"])
        self.assertEqual(row["画像URL"], "")
        self.assertEqual(row["論文要約根拠"], "要旨に基づく要約")
        for html in [self.html(publication="2026/07/01"), self.html(doi="10.1299/mej.other"), self.html().replace('article-overiew-abstract-wrap', 'not-abstract')]:
            self.assertIsNone(papers.parse_article(html, identity, papers.paper_window("2026-09-29"), "2026-09-29"))
        get = Mock(return_value=Mock(status_code=200, url="https://www.jstage.jst.go.jp/article/mej/advpub/0/abc/_article", content=self.html()))
        with redirect_stdout(io.StringIO()):
            rows = papers.collect_entries([entry,entry], "MEJ", "2026-09-29", get, {})
        self.assertEqual(len(rows), 1)
        self.assertEqual(get.call_count, 1)


class DevelopmentPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global collector, updater
        import google_search_script as collector
        import auto_update_daily_news as updater

    def setUp(self):
        collector.configure_edition("exterior")
        updater.configure_edition("exterior")
        self.folder = tempfile.TemporaryDirectory()
        self.context = get_edition("exterior", self.folder.name)
        self.context.config_dir.mkdir(parents=True)
        self.context.collection_settings_path.write_text(json.dumps({"exterior":get_edition("exterior").config}),encoding="utf-8")
        self.context.ensure_directories()

    def tearDown(self):
        self.folder.cleanup()
        collector.configure_edition("interior")
        updater.configure_edition("interior")

    def row(self, index, country="論文", day="2026-09-10", score=75, lane="direct"):
        return {"国":country, "日付":day, "タイトル":f"Automotive roof joining {index}",
                "内容":"Automotive roof polymer steel laser joining and surface tests.",
                "タイトル（日本語）":f"ルーフの接合を検証 {index}", "内容（日本語）":"鋼と樹脂の接合試験で破壊の状態を比較した。",
                "URL":f"https://doi.org/10.1299/mej.26-{index:05d}", "画像URL":"", "LLM判定":"対象",
                "LLM後処理":"実施", "内装関連度":score, "記事区分":"product", "トレンド分類":"",
                "外装関連区分":lane, "外装技術根拠":"鋼と樹脂の接合試験", "外装応用仮説":"ルーフの接合を検討する" if lane=="transfer" else "",
                "外装選定基準":scope.POLICY_VERSION,
                "論文DOI":f"10.1299/mej.26-{index:05d}" if country=="論文" else "",
                "論文発行日":day if country=="論文" else "", "論文公開日":day if country=="論文" else "",
                "論文要約根拠":"要旨に基づく要約" if country=="論文" else ""}

    def select(self, rows):
        target = self.context.runtime_dir / "search_results.csv"
        with patch.object(collector,"EDITION",self.context), patch.object(collector,"published_news",return_value=[]), \
             patch.object(collector,"deduplicate_articles",side_effect=lambda candidates,*a,**kw:(candidates,[])), \
             patch.object(collector,"summarize_article",side_effect=AssertionError("No LLM in selection fixture")), redirect_stdout(io.StringIO()):
            collector.build_sheet2_and_csv(collector.pd.DataFrame(rows),target,["2026-09-29"])
        return collector.pd.read_csv(target.with_name("sheet2_llm_targets.csv"),keep_default_na=False)

    def test_papers_have_separate_window_quota_and_no_relevance_bypass(self):
        rows = [self.row(i) for i in range(7)] + [self.row(20+i,"日本","2026-09-29") for i in range(10)]
        rows += [self.row(80, day="2026-08-30"), self.row(81, score=59), {**self.row(82),"LLM判定":"非対象"},self.row(83,"日本","2026-09-10")]
        selected = self.select(rows)
        self.assertEqual(selected["国"].value_counts().to_dict(), {"日本":10,"論文":5})
        self.assertFalse(set(selected["URL"]) & {row["URL"] for row in rows[-4:]})
        items = [dict(country="paper" if row["国"]=="論文" else "jp",date=row["日付"],url=row["URL"]) for row in selected.to_dict("records")]
        receipt = dict(collector.SHEET2_RESULT,edition_id="exterior",completed=True,target_dates=["2026-09-29"])
        self.assertEqual(validated_issue_context(receipt,items)["selected_paper_count"],5)
        with self.assertRaises(ValueError):
            validated_issue_context({**receipt,"papers_enabled":False},items)
        self.assertTrue(collector.summary_language_problem("論文","English only","Untranslated abstract"))
        collector.configure_edition("interior")
        self.assertFalse(collector.summary_language_problem("論文","English only","Untranslated abstract"))

    def test_transfer_gets_room_but_does_not_displace_direct_technical_news(self):
        rows=[self.row(20+i,"日本","2026-09-29",score=70) for i in range(10)]
        rows += [self.row(40+i,"日本","2026-09-29",score=95,lane="transfer") for i in range(10)]
        selected=self.select(rows)
        self.assertEqual(selected["外装関連区分"].value_counts().to_dict(),{"direct":7,"transfer":3})

    def test_paper_enrichment_never_scrapes_images_or_replaces_abstract_with_navigation(self):
        row=self.row(1); abstract=row["内容"]
        assessment=dict(score=76,reason="車体接合の研究",category="product",trend_topic="",development_lane="direct")
        with patch.multiple(collector,USE_LLM=True,FETCH_MISSING_IMAGES=True,_ensure_llm_model_loaded=lambda:True), \
             patch.object(collector,"fetch_article_text",side_effect=AssertionError("Abstract already verified")), \
             patch.object(collector,"resolve_with_playwright",side_effect=AssertionError("No paper image scraping")), \
             patch.object(collector,"check_url_ok",return_value=True), \
             patch.object(collector,"call_llm_classify",return_value=("非対象","なし")) as classify, \
             patch.object(collector,"call_llm_interior_assessment",return_value=dict(score=20,category="",development_lane="exclude")), \
             patch.object(collector,"summarize_article",side_effect=AssertionError("Rejected paper must not be summarized")), redirect_stdout(io.StringIO()):
            result=collector.enrich_results([row])
        self.assertEqual(result[0]["LLM判定"],"非対象")
        self.assertEqual(classify.call_args.args[1],abstract)

    def test_detailed_review_rescues_transfer_after_false_negative_without_keyword_acceptance(self):
        for accepted in (True,False):
            row=self.row(1)
            row.update(タイトル="Steel polymer laser joining",内容="Laser joining was tested with steel and polymer coupons. Joint strength was compared after thermal cycling.")
            assessment=dict(score=72 if accepted else 20,reason="異材接合の評価",category="product" if accepted else "",
                            development_lane="transfer" if accepted else "exclude",source_evidence="Steel polymer laser joining",
                            application="ルーフの接合への応用を検討する")
            with patch.multiple(collector,USE_LLM=True,FETCH_MISSING_IMAGES=False,_ensure_llm_model_loaded=lambda:True), \
                 patch.object(collector,"check_url_ok",return_value=True), \
                 patch.object(collector,"call_llm_classify",return_value=("非対象","なし")), \
                 patch.object(collector,"call_llm_interior_assessment",return_value=assessment) as scorer, \
                 patch.object(collector,"summarize_article",return_value=("鋼と樹脂の接合を検証","レーザーによる接合を試験した。")) as summarizer, redirect_stdout(io.StringIO()):
                result=collector.enrich_results([row])[0]
            self.assertEqual(result["LLM判定"],"対象" if accepted else "非対象")
            self.assertEqual(scorer.call_count,1)
            self.assertEqual(summarizer.call_count,1 if accepted else 0)

    def test_paper_metadata_survives_publication_and_retry(self):
        rows=self.select([self.row(1),self.row(2,"日本","2026-09-29",lane="transfer")])
        receipt=dict(collector.SHEET2_RESULT,edition_id="exterior",completed=True,target_dates=["2026-09-29"])
        (self.context.runtime_dir/"collection_result.json").write_text(json.dumps(receipt),encoding="utf-8")
        news=self.context.content_dir/"news_data.js"
        argv=["publisher","--edition","exterior","--skip-insights","--skip-html"]
        with patch.multiple(updater,EDITION=self.context,NEWS_PATH=news,DEFAULT_SHEET=self.context.runtime_dir/"sheet2_llm_targets.csv",INSIGHTS_PATH=self.context.content_dir/"insights_data.js"), \
             patch.object(sys,"argv",argv), patch("ニュース収集.source_highlights.enrich_items"), redirect_stdout(io.StringIO()):
            updater.main()
        published=published_news(news)
        paper=next(item for item in published if item["country"]=="paper")
        self.assertEqual(paper["summaryBasis"],"要旨に基づく要約")
        self.assertEqual(paper["date"],"2026-09-10")
        self.assertEqual(paper["digestDate"],"2026-09-29")
        self.assertEqual(published_row(paper)["論文DOI"],paper["doi"])
        self.assertEqual(published_row(paper)["国"],"論文")

    def test_technical_words_are_not_forced_into_japanese_as_company_names(self):
        source="Laser joining of steel and polymer. Laser joining tests compared thermal properties."
        self.assertEqual(collector.extract_latin_source_anchors(source),[])
        self.assertTrue(collector.summary_matches_source("鋼と樹脂のレーザー接合を試験した。",source))
        self.assertIn("Toyota",collector.extract_latin_source_anchors("Toyota applies laser joining to its Toyota roof"))


if __name__ == "__main__":
    unittest.main()
