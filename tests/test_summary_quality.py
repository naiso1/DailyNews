"""Exercise summary helpers without importing the collection script's entry point."""

import ast
import json
from pathlib import Path
import re
import sys
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
COLLECTION = ROOT / "ニュース収集"
sys.path.insert(0, str(COLLECTION))
from summary_grounding import summary_omits_interior_details


def helpers():
    tree = ast.parse((COLLECTION / "google_search_script.py").read_text(encoding="utf-8-sig"))
    names = {
        "normalize_text", "ends_with_sentence", "trim_to_sentence", "trim_title_safely",
        "has_suspicious_truncation", "title_looks_incomplete", "parse_json_field",
        "compact_summary_with_llm", "build_source_faithful_japanese_summary",
    }
    selected = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    assert len(selected) == len(names)
    env = {"re": re, "json": json, "SUMMARY_TITLE_LIMIT": 50, "SUMMARY_CONTENT_LIMIT": 150,
           "_is_valid_japanese": lambda text: bool(re.search(r"[ぁ-んァ-ヶ]", text)),
           "extract_latin_source_anchors": lambda *args, **kwargs: ["Skynomad"]}
    exec(compile(ast.Module(body=selected, type_ignores=[]), "summary-helpers", "exec"), env)
    return env


SOURCE = "Skynomad N90 Max has a movable central island with a refrigerator. A 16.1-inch infotainment screen and 2+2+3 seating offer eleven layouts."
GOOD = "小米Skynomad N90 Maxは、9L冷蔵庫を内蔵する可動式センターコンソールを搭載する。16.1インチ画面とHyperOSを備え、2＋2＋3席で11通りの空間レイアウトに対応する。"
BAD = "Xiaomiは9月7日にSkynomad N90 Maxを発売し、39,700ドルから販売を開始します。"
BROKEN_TITLE = "Xiaomiは、電動ポップアップルーフを備えたSkynomad N90 Maxを9月7"


class SummaryQualityTests(unittest.TestCase):
    def setUp(self):
        self.env = helpers()

    def test_long_headline_is_not_sliced_mid_date_or_model(self):
        title = BROKEN_TITLE + "日に発売、可動式センターコンソールも採用"
        self.assertEqual(self.env["trim_title_safely"](title, 50), title)
        self.assertEqual(self.env["trim_title_safely"]("新型SUVの可動式コンソールを公開。" + "本文" * 40, 30), "新型SUVの可動式コンソールを公開")

    def test_partial_date_is_rejected_but_complete_titles_are_allowed(self):
        check = self.env["title_looks_incomplete"]
        self.assertTrue(check(BROKEN_TITLE))
        self.assertTrue(check("新型SUVの内装公開を2026年9月7"))
        for title in ["新型SUVを9月7日に発売", "新型SUV、可動式コンソールを採用", "BMW i7"]:
            self.assertFalse(check(title), title)

    def test_coverage_is_based_on_the_source_not_invented_features(self):
        self.assertTrue(summary_omits_interior_details(BAD, SOURCE))
        self.assertFalse(summary_omits_interior_details(GOOD, SOURCE))
        self.assertFalse(summary_omits_interior_details(BAD, "The vehicle launched today for 39,700 USD."))
        self.assertFalse(summary_omits_interior_details("新型シートを採用。", "The model has new seats."))
        for console in ["center console", "centre console", "central island"]:
            self.assertTrue(summary_omits_interior_details(BAD, console + " with a refrigerator"))

    def test_compaction_retries_a_price_only_summary(self):
        llm = Mock(side_effect=[BAD, GOOD])
        self.env["call_llm_text"] = llm
        self.assertEqual(self.env["compact_summary_with_llm"]("Skynomad", SOURCE, BAD), GOOD)
        self.assertEqual(llm.call_count, 2)

    def test_failed_compaction_does_not_accept_lost_interior_details(self):
        self.env["call_llm_text"] = Mock(return_value=BAD)
        self.assertEqual(self.env["compact_summary_with_llm"]("Skynomad", SOURCE, BAD), "")
        self.assertEqual(self.env["call_llm_text"].call_count, 2)

    def test_source_repair_rejects_incomplete_output(self):
        title = "小米Skynomad N90 Max、可動式コンソールを採用"
        self.env["call_llm_text"] = Mock(side_effect=[
            json.dumps({"title": BROKEN_TITLE, "summary": BAD}, ensure_ascii=False),
            json.dumps({"title": title, "summary": GOOD}, ensure_ascii=False),
        ])
        self.assertEqual(self.env["build_source_faithful_japanese_summary"]("Skynomad", SOURCE), (title, GOOD))


if __name__ == "__main__":
    unittest.main()
