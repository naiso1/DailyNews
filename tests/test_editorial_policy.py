"""Feedback-derived scope and grounded adoption evidence, entirely offline."""
import json
from pathlib import Path
import unittest

from dailynews.editorial_policy import (EVIDENCE_COLUMNS, apply_policy,
                                       classify_lighting, evidence_problems, extract_evidence, exterior_scope_rules)

ROOT = Path(__file__).resolve().parents[1]


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


if __name__ == "__main__":
    unittest.main()
