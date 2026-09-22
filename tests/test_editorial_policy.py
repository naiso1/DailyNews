"""Feedback-derived scope and grounded adoption evidence, entirely offline."""
from contextlib import ExitStack, redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ニュース収集"))
from dailynews.editorial_policy import (EVIDENCE_COLUMNS, POLICY_VERSION, apply_policy,
                                       classify_lighting, evidence_problems, extract_evidence, exterior_scope_rules)
from dailynews.editions import get_edition


def useful_article():
    body = "ドアトリムに静電容量センサーを内蔵し、表皮越しの操作に対応する。"
    return {"title": "ドアトリムの表皮一体操作部を公開", "desc": body, "url": "https://example.com/trim",
            "originalTitle": "ドアトリムの表皮一体操作部を公開", "originalDesc": body,
            "country": "jp", "date": "2026-09-20", "evidence": {
                "target_component": "ドアトリムの操作部", "new_information": "静電容量センサーを表皮の内側に内蔵した。",
                "development_reference": "表皮越しの操作部を設計する際の配置方式を比較する材料になる。",
                "source_quote": body}}


class EditorialPolicyTests(unittest.TestCase):
    def test_real_local_responses_keep_material_exclude_seat_and_hold_summary_contamination(self):
        fixture = json.loads((ROOT / "tests/fixtures/editorial_assessment_responses.json").read_text(encoding="utf-8"))
        for case in fixture["cases"]:
            with self.subTest(case=case["case"]):
                assessed = dict(case["article"], evidence=case["assessment"].get("evidence"),
                                reason=case["assessment"].get("reason"))
                policy = apply_policy(assessed)
                self.assertEqual(policy["decision"], case["expected_decision"])
                if policy["decision"] == "keep":
                    self.assertGreaterEqual(case["assessment"]["score"], 60)
                    self.assertEqual(evidence_problems(assessed), [])
                elif policy["decision"] == "hold":
                    self.assertIn("source_quote_not_found", policy["reason"])

    def test_feedback_seven_removed_two_recurrences_and_two_useful_material_articles(self):
        fixture = json.loads((ROOT / "tests/fixtures/editorial_feedback_cases.json").read_text(encoding="utf-8"))
        self.assertEqual(len(fixture["cases"]), 11)
        for case in fixture["cases"]:
            with self.subTest(id=case["id"]):
                self.assertEqual(apply_policy(case["article"], require_evidence=False)["decision"], case["expected_scope"])

    def test_source_grounded_four_part_rationale_is_required(self):
        article = useful_article()
        self.assertEqual(apply_policy(article)["decision"], "keep")
        for key in EVIDENCE_COLUMNS:
            missing = dict(article, evidence={name: value for name, value in article["evidence"].items() if name != key})
            self.assertEqual(apply_policy(missing)["decision"], "hold", key)

    def test_reused_example_reason_or_generic_evidence_is_held(self):
        article = useful_article()
        copied = dict(article, reason="seat and display plus cabin image")
        self.assertIn("copied_prompt_reason", apply_policy(copied)["reason"])
        for value in ("seat and display plus cabin image", "内装開発に役立つ", "useful"):
            article["evidence"]["development_reference"] = value
            self.assertEqual(apply_policy(article)["decision"], "hold")

    def test_generated_summary_cannot_supply_a_missing_original_quote(self):
        article = useful_article()
        article["originalDesc"] = "The maker announced a new vehicle. No cabin details were provided."
        self.assertEqual(apply_policy(article)["decision"], "hold")

    def test_explicitly_empty_original_fields_cannot_fall_back_to_generated_copy(self):
        for original_title in ("", "ドアトリムの新製品を発表"):
            article = dict(useful_article(), originalTitle=original_title, originalDesc="")
            self.assertIn("source_quote_not_found", apply_policy(article)["reason"])
        article = useful_article()
        del article["originalTitle"]
        del article["originalDesc"]
        article.update({"タイトル": "", "内容": ""})
        self.assertIn("source_quote_not_found", apply_policy(article)["reason"])

    def test_quote_must_be_one_passage_within_either_title_or_body_and_at_most_240_characters(self):
        article = useful_article()
        article["evidence"]["source_quote"] = article["originalTitle"] + " " + article["originalDesc"]
        self.assertIn("source_quote_not_found", apply_policy(article)["reason"])
        article["originalDesc"] = "ドアトリムの表皮材" + "あ" * 240
        article["evidence"]["source_quote"] = article["originalDesc"][:241]
        self.assertIn("source_quote_not_found", apply_policy(article)["reason"])
        article["evidence"]["source_quote"] = article["originalDesc"][:240]
        self.assertEqual(evidence_problems(article), [])

    def test_lighting_classifies_installation_not_generic_illumination(self):
        cases = [(("室内のアンビエント照明", "ドアトリムにライトを配置"), "interior"),
                 (("発光グリルとヘッドライト", "エンブレムが発光する"), "exterior"),
                 (("車室内照明とテールランプ", "双方を更新する"), "both"),
                 (("照明技術の展示", "新しい光源を開発"), ""),
                 (("新型車の変更", "コンソールの造形を変更。外装照明を刷新した。"), "exterior"),
                 (("外装アンビエント照明", "車外照明を更新"), "exterior")]
        for args, expected in cases:
            self.assertEqual(classify_lighting(*args), expected, args)
        self.assertEqual(apply_policy({"title": "発光グリル発売", "desc": "エンブレムとヘッドライトを点灯する。"}, require_evidence=False)["decision"], "exclude")

    def test_ambiguous_words_or_page_navigation_do_not_exclude_useful_article(self):
        article = useful_article()
        article["originalDesc"] += " Car loan calculator. Other news: Apollo travels and motorcycle sales."
        self.assertEqual(apply_policy(article)["decision"], "keep")
        storage = {"title": "バイクを積載できるミニバンの収納", "desc": "ミニバンの荷室収納と固定具を説明する。"}
        self.assertEqual(apply_policy(storage, require_evidence=False)["decision"], "keep")

    def test_seat_sensing_and_explicit_transfer_remain_in_scope(self):
        seat = {"title": "新シート発売、表皮一体の圧力センサーを内蔵", "desc": "体圧分布を計測する圧力センサーを表皮材へ統合した。"}
        self.assertEqual(apply_policy(seat, require_evidence=False)["decision"], "keep")
        transfer = {"title": "二輪技術を自動車内装へ転用", "desc": "乗用車のドアトリムへ静電容量センサーを応用する構造を開発した。"}
        self.assertEqual(apply_policy(transfer, require_evidence=False)["decision"], "keep")

    def test_vague_component_and_invented_numbers_do_not_pass_grounding(self):
        article = useful_article()
        article["evidence"]["target_component"] = "内装部品"
        self.assertIn("unspecified_target_component", apply_policy(article)["reason"])
        article = useful_article()
        article["evidence"]["new_information"] = "表皮一体操作部により重量を30%低減した。"
        self.assertIn("unsupported_number", apply_policy(article)["reason"])

    def test_only_approved_known_boolean_presets_can_change_policy(self):
        item = {"title": "BRIDEの新シート受注開始", "desc": "新シートは従来より20mm広く、価格は20万円。"}
        pending = {"key": "seat_requires_transferable_value", "enabled": False, "review_status": "pending", "version": 1}
        self.assertEqual(apply_policy(item, [pending], require_evidence=False)["decision"], "exclude")
        approved = dict(pending, review_status="approved")
        self.assertEqual(apply_policy(item, [approved], require_evidence=False)["decision"], "keep")
        invalid = dict(approved, enabled="false")
        self.assertEqual(apply_policy(item, [invalid], require_evidence=False)["decision"], "exclude")
        arbitrary = {"key": "eval", "enabled": True, "review_status": "approved", "version": 1, "text": ".*"}
        self.assertEqual(apply_policy(item, [arbitrary], require_evidence=False)["decision"], "exclude")

    def test_curated_paper_exception_and_published_fields_are_supported(self):
        self.assertEqual(apply_policy({"country": "paper", "title": "Study of seat surfaces"})["decision"], "keep")
        fields = {"selectionTargetComponent": "表皮材", "selectionNewInformation": "NUGRAINを採用した。",
                  "selectionDevelopmentReference": "触感と防汚性を両立する表皮の候補比較に用いる。", "selectionSourceQuote": "NUGRAIN表皮材を採用した。"}
        self.assertEqual(extract_evidence(fields)["target_component"], "表皮材")

    def test_exterior_has_no_implicit_interior_rules_or_unapproved_scope_gate(self):
        article = {"title": "Royal Enfield motorcycle grille", "desc": "A new grille design was announced."}
        self.assertEqual(apply_policy(article, exterior_scope_rules(), require_evidence=False)["decision"], "keep")
        pending = {"key": "exclude_non_passenger_vehicles", "enabled": True, "review_status": "pending", "version": 1}
        self.assertEqual(apply_policy(article, exterior_scope_rules([pending]), require_evidence=False)["decision"], "keep")
        approved = dict(pending, review_status="approved")
        self.assertEqual(apply_policy(article, exterior_scope_rules([approved]), require_evidence=False)["decision"], "exclude")
        lighting = {"title": "発光グリルとヘッドライト", "desc": "外装の照明を刷新する。"}
        interior_only = dict(approved, key="interior_lighting_only")
        self.assertEqual(apply_policy(lighting, exterior_scope_rules([interior_only]), require_evidence=False)["decision"], "keep")


class InteriorSelectionPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global collector
        import google_search_script as collector

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.context = get_edition("interior", directory.name)
        self.context.config_dir.mkdir(parents=True)
        self.context.collection_settings_path.write_text(json.dumps({"interior": {"selection": {"maximum_per_country": 10, "require_original_image": False}}}), encoding="utf-8")
        self.context.ensure_directories()
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(collector, "EDITION", self.context))
        self.stack.enter_context(patch.object(collector, "OUTPUT_PAPERS_SHEET2", False))
        self.stack.enter_context(patch.object(collector, "LLM_CACHE", {}))
        self.stack.enter_context(patch.object(collector, "LLM_IMAGE_INPUT", False))
        self.snapshot = {"status": "fresh", "rules": [], "excluded_urls": []}
        self.stack.enter_context(patch.object(collector, "editorial_feedback", return_value=self.snapshot))

    def row(self, key="trim", evidence=True):
        article = useful_article()
        row = {"国": "日本", "日付": "2026-09-20", "URL": f"https://example.com/{key}",
               "タイトル": article["title"], "内容": article["desc"], "タイトル（日本語）": article["title"],
               "内容（日本語）": article["desc"], "LLM判定": "対象", "LLM後処理": "実施", "内装関連度": 85}
        if evidence:
            row.update({column: article["evidence"][name] for name, column in EVIDENCE_COLUMNS.items()})
        return row

    def select(self, rows, history=(), assessment=None):
        target = self.context.runtime_dir / "search_results.csv"
        with patch.object(collector, "published_news", return_value=list(history)), \
                patch.object(collector, "summarize_article", side_effect=AssertionError("No summary calls")), \
                patch.object(collector, "call_llm_interior_assessment", return_value=assessment) as assess, redirect_stdout(io.StringIO()):
            collector.build_sheet2_and_csv(collector.pd.DataFrame(rows), target, ["2026-09-20"])
        selected = collector.pd.read_csv(target.with_name("sheet2_llm_targets.csv"), keep_default_na=False)
        return selected, assess

    def test_non_targets_do_not_fill_shortage_but_other_useful_articles_and_papers_survive(self):
        target, rejected, paper = self.row(), self.row("rejected"), self.row("paper", evidence=False)
        rejected["LLM判定"] = "非対象"
        paper.update({"国": "論文", "LLM判定": "非対象", "タイトル（日本語）": "Independent study", "内容（日本語）": "A separate scientific abstract."})
        selected, assess = self.select([target, rejected, paper])
        self.assertEqual(set(selected["URL"]), {target["URL"], paper["URL"]})
        assess.assert_not_called()

    def test_missing_rationale_is_repaired_and_stored_once(self):
        row = self.row(evidence=False)
        assessment = {"score": 83, "reason": "表皮一体操作部の配置を比較できる", "evidence": useful_article()["evidence"], "policy_decision": "keep"}
        selected, assess = self.select([row], assessment=assessment)
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected.iloc[0]["採用根拠_状態"], "検証済み")
        self.assertEqual(selected.iloc[0][EVIDENCE_COLUMNS["source_quote"]], assessment["evidence"]["source_quote"])
        assess.assert_called_once()
        stored = collector.pd.read_csv(self.context.runtime_dir / "search_results.csv", keep_default_na=False)
        self.assertEqual(stored.iloc[0][EVIDENCE_COLUMNS["new_information"]], assessment["evidence"]["new_information"])

    def test_ungrounded_failed_repair_falls_back_to_the_original_relevance_judgment(self):
        # No fuller text was ever fetched (repair returns None, same as the
        # original bare snippet), so a verbatim-quote requirement can never
        # be met here. The prior "対象" classification is trusted instead of
        # discarding the article outright.
        broken, valid = self.row("broken", evidence=False), self.row("valid")
        broken["内装関連度"] = 100
        selected, assess = self.select([broken, valid])
        self.assertEqual(set(selected["URL"]), {broken["URL"], valid["URL"]})
        assess.assert_called_once()
        self.assertEqual(collector.SHEET2_RESULT["editorial_held_count"], 0)
        self.assertEqual(collector.SHEET2_RESULT["selected_count"], 2)

    def test_grounded_failed_repair_still_held_and_does_not_displace_valid_rows(self):
        # Once real article text (>=150 chars) is available, a verbatim quote
        # is achievable; a repair that still cannot produce one is a genuine
        # evidence gap, not a fetch failure, and must stay held.
        long_body = "ドアトリムに静電容量センサーを内蔵し、表皮越しの操作に対応する。" * 8
        broken, valid = self.row("broken", evidence=False), self.row("valid")
        broken["内容"] = broken["内容（日本語）"] = long_body
        broken["内装関連度"] = 100
        selected, assess = self.select([broken, valid])
        self.assertEqual(selected["URL"].tolist(), [valid["URL"]])
        assess.assert_called_once()
        self.assertEqual(collector.SHEET2_RESULT["editorial_held_count"], 1)
        self.assertEqual(collector.SHEET2_RESULT["selected_count"], 1)

    def test_same_issue_legacy_is_preserved_but_reviewed_hidden_url_is_never_restored(self):
        row = self.row(evidence=False)
        published = {"id": "jp1", "url": row["URL"], "date": row["日付"], "country": "jp", "title": row["タイトル"], "desc": row["内容"], "interiorScore": 85}
        selected, assess = self.select([row], [published])
        self.assertEqual(len(selected), 1)
        assess.assert_not_called()
        self.snapshot["excluded_urls"] = [published["url"]]
        selected, assess = self.select([row], [published])
        self.assertTrue(selected.empty)
        assess.assert_not_called()

    def test_exterior_collector_applies_only_explicitly_approved_shared_scope_rules(self):
        context = get_edition("exterior", self.context.root / "outer")
        context.config_dir.mkdir(parents=True)
        context.collection_settings_path.write_text(json.dumps({"exterior": {"selection": {
            "lookback_days": 7, "minimum_score": 60, "require_original_image": False}}}), encoding="utf-8")
        context.ensure_directories()
        self.context = context
        row = self.row("bike", evidence=False)
        row.update({"タイトル": "Royal Enfield motorcycle grille", "内容": "A new grille design was announced.",
                    "タイトル（日本語）": "ロイヤルエンフィールドのグリル刷新", "内容（日本語）": "新しいグリルの意匠を公開した。"})
        with patch.object(collector, "EDITION", context):
            selected, assess = self.select([row])
            self.assertEqual(len(selected), 1)
            assess.assert_not_called()
            self.snapshot["rules"] = [{"key": "exclude_non_passenger_vehicles", "enabled": True,
                                       "review_status": "approved", "version": 1}]
            selected, assess = self.select([row])
            self.assertTrue(selected.empty)
            assess.assert_not_called()
    @staticmethod
    def response(value):
        return Mock(status_code=200, json=Mock(return_value={"choices": [{"message": {"content": value}}]}))

    def test_assessment_requires_evidence_and_does_not_cache_invalid_reason(self):
        article = useful_article()
        invalid = {"score": 98, "reason": "seat and display plus cabin image", "image_interior": True}
        valid = {"score": 83, "reason": "表皮一体操作部の設計を比較できる", "evidence": article["evidence"], "image_interior": None}
        with patch.object(collector, "USE_LLM", True), patch.object(collector, "_post_llm", side_effect=[self.response(json.dumps(invalid)), self.response(json.dumps(valid))]) as request, redirect_stdout(io.StringIO()):
            self.assertIsNone(collector.call_llm_interior_assessment(article["title"], article["desc"]))
            self.assertEqual(collector.LLM_CACHE, {})
            repaired = collector.call_llm_interior_assessment(article["title"], article["desc"])
            self.assertEqual(repaired["policy_decision"], "keep")
            self.assertEqual(collector.call_llm_interior_assessment(article["title"], article["desc"]), repaired)
        self.assertEqual(request.call_count, 2)
        prompt = request.call_args.kwargs["json"]["messages"][0]["content"]
        self.assertNotIn("seat and display plus cabin image", prompt)
        self.assertIn("source_quote", prompt)

    def test_unstructured_legacy_cache_cannot_bypass_the_new_policy(self):
        article = useful_article()
        old_key = ("interior", "product_assessment", article["title"], article["desc"], "", "", "")
        collector.LLM_CACHE[old_key] = {"score": 100, "reason": "seat and display plus cabin image"}
        with patch.object(collector, "USE_LLM", True), patch.object(collector, "_post_llm", return_value=self.response('{}')) as request, redirect_stdout(io.StringIO()):
            self.assertIsNone(collector.call_llm_interior_assessment(article["title"], article["desc"]))
        request.assert_called_once()

    def test_assessment_uses_original_source_without_generated_summary_or_prefilled_reply(self):
        article = useful_article()
        generated_summary = "要約だけが主張する未確認の燃費50パーセント改善"
        valid = {"score": 83, "reason": "表皮一体操作部を比較できる", "evidence": article["evidence"], "image_interior": None}
        with patch.object(collector, "USE_LLM", True), patch.object(collector, "_post_llm", return_value=self.response(json.dumps(valid))) as request, redirect_stdout(io.StringIO()):
            result = collector.call_llm_interior_assessment(article["title"], article["desc"], summary=generated_summary)
        self.assertEqual(result["policy_decision"], "keep")
        messages = request.call_args.kwargs["json"]["messages"]
        self.assertEqual([message["role"] for message in messages], ["user"])
        prompt = messages[0]["content"]
        self.assertNotIn(generated_summary, prompt)
        self.assertIn(article["title"], prompt)
        self.assertIn(article["desc"], prompt)
        schema = json.loads(next(line for line in prompt.splitlines() if line.startswith('{"type":"object"')))
        self.assertEqual(set(schema["properties"]["evidence"]["required"]), set(EVIDENCE_COLUMNS))
        self.assertNotIn('"default"', json.dumps(schema))
        self.assertNotIn('"examples"', json.dumps(schema))


if __name__ == "__main__":
    unittest.main()
