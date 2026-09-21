"""Source-language component names must survive strict quotation validation."""
import unittest

from dailynews.editorial_policy import evidence_problems


class EditorialQuoteVocabularyTests(unittest.TestCase):
    @staticmethod
    def article(quote):
        return {"originalTitle": "Automotive component development",
                "originalDesc": quote,
                "evidence": {"target_component": "加飾面の操作部品",
                             "new_information": "原文に記載された操作部品の構成を確認する。",
                             "development_reference": "内装操作部品の配置設計と評価条件を比較する。",
                             "source_quote": quote}}

    def test_smart_surface_and_touch_interface_terms_are_specific_components(self):
        quotes = (
            "The partners are developing smart surfaces for vehicle cabins.",
            "The supplier provides solid-state user-interface technology and sensing architecture.",
            "The system integrates touch controls with visual feedback.",
            "The panel combines touch and force sensing with decorative lighting.",
        )
        for quote in quotes:
            with self.subTest(quote=quote):
                self.assertEqual(evidence_problems(self.article(quote)), [])

    def test_chinese_original_component_names_are_recognized(self):
        for component in ("内饰材料", "方向盘", "仪表板", "显示屏", "门饰板", "座椅", "电容式触控", "触觉反馈"):
            quote = f"新型{component}采用集成式设计改善操作体验。"
            with self.subTest(component=component):
                self.assertEqual(evidence_problems(self.article(quote)), [])

    def test_market_statement_and_vague_interior_mention_still_fail(self):
        for quote in ("The company expanded its international market presence.",
                      "公司表示汽车市场的销售持续增长。", "新车型的内饰设计受到广泛关注。"):
            with self.subTest(quote=quote):
                self.assertEqual(evidence_problems(self.article(quote)), ["source_quote_has_no_component"])

    def test_component_word_does_not_allow_a_quote_absent_from_source(self):
        article = self.article("A company announces a partnership for future development.")
        article["evidence"]["source_quote"] = "The door trim integrates smart surfaces and touch controls."
        self.assertEqual(evidence_problems(article), ["source_quote_not_found"])


if __name__ == "__main__":
    unittest.main()
