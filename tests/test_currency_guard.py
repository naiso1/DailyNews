"""Offline source-unit regressions. Never import the collection entry point."""

import ast
import csv
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
COLLECTION = ROOT / "\u30cb\u30e5\u30fc\u30b9\u53ce\u96c6"
sys.path.insert(0, str(COLLECTION))
from currency_guard import CurrencyUnitError, repair_indian_price_units

RUPEES = "\u30eb\u30d4\u30fc"
MAN = "\u4e07"


class CurrencyGuardTests(unittest.TestCase):
    def test_known_lakh_loss_and_man_mistranslation(self):
        for n, source, expected in [
            ("19.22", "Rs 19.22 lakh", "192.2"),
            ("19.21", "Rs. 19.21 Lakh", "192.1"),
            ("24.49", "INR 24.49 lakhs", "244.9"),
            ("2", "2 crore rupees", "2000"),
        ]:
            for wrong in [n + RUPEES, n + MAN + RUPEES]:
                fixed, changes = repair_indian_price_units(wrong, source, "in")
                self.assertEqual(fixed, expected + MAN + RUPEES)
                self.assertEqual(changes, [(wrong, fixed)])
                self.assertEqual(repair_indian_price_units(fixed, source, "in"), (fixed, []))

    def test_correct_prices_accessories_and_other_countries_are_unchanged(self):
        source = "Rs 19.22 lakh; accessories cost Rs 19.22 or Rs 90,000."
        for text in ["192.2" + MAN + RUPEES, "19.22" + RUPEES, "90000" + RUPEES, "Rs 19.22 lakh"]:
            self.assertEqual(repair_indian_price_units(text, source, "in"), (text, []))
        for country in ["jp", "us", "Nepal", ""]:
            text = "19.22" + RUPEES
            self.assertEqual(repair_indian_price_units(text, source, country), (text, []))

    def test_source_range_inherits_scale_and_preserves_both_endpoints(self):
        wrong = "19.21\u301c24.49" + MAN + RUPEES
        fixed, changes = repair_indian_price_units(wrong, "Rs 19.21 - 24.49 lakh", "in")
        self.assertEqual(fixed, "192.1" + MAN + "\u301c244.9" + MAN + RUPEES)
        self.assertEqual(len(changes), 1)
        good = "59.9" + MAN + "\u301c99.9" + MAN + RUPEES
        self.assertEqual(repair_indian_price_units(good, "Rs 5.99 lakh - Rs 9.99 lakh", "in"), (good, []))

    def test_no_guess_for_unrelated_numbers_or_malformed_source(self):
        for source in ["A 19.22-inch display.", "Rs 19,22 lakh", "Rs 1", "Rs 21.80 lakh"]:
            text = "19.22" + RUPEES
            self.assertEqual(repair_indian_price_units(text, source, "in"), (text, []))
        text = "11.6-inch display, 2026 edition, 19.22" + MAN + RUPEES
        fixed, _ = repair_indian_price_units(text, "Rs 19.22 lakh", "in")
        self.assertTrue(fixed.startswith("11.6-inch display, 2026 edition, "))

    def test_ambiguous_scale_fails_closed_instead_of_guessing(self):
        with self.assertRaises(CurrencyUnitError):
            repair_indian_price_units("2" + RUPEES, "2 lakh or 2 crore rupees", "in")

    def test_collection_guard_runs_after_the_last_llm_rewrite_before_caching(self):
        tree = ast.parse((COLLECTION / "google_search_script.py").read_text(encoding="utf-8-sig"))
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "summarize_article")
        calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
        guard_lines = [n.lineno for n in calls if n.func.id == "repair_indian_price_units"]
        llm_lines = [n.lineno for n in calls if n.func.id in ("call_llm_text", "build_source_faithful_japanese_summary")]
        self.assertEqual(len(guard_lines), 2)
        self.assertGreater(min(guard_lines), max(llm_lines))
        exports = [n for n in ast.walk(tree) if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == "sheet_cols" for t in n.targets)]
        self.assertTrue(any({"col_title", "col_content"}.issubset(
            {v.id for v in n.value.elts if isinstance(v, ast.Name)}
        ) for n in exports))

    def test_resumed_csv_publication_also_repairs_title_and_summary(self):
        spec = importlib.util.spec_from_file_location("currency_publisher", ROOT / "auto_update_daily_news.py")
        publisher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(publisher)
        with tempfile.TemporaryDirectory() as directory:
            sheet = Path(directory) / "sheet.csv"
            header = ["\u56fd", "\u65e5\u4ed8", "\u30bf\u30a4\u30c8\u30eb", "\u5185\u5bb9",
                      "\u30bf\u30a4\u30c8\u30eb\uff08\u65e5\u672c\u8a9e\uff09", "\u5185\u5bb9\uff08\u65e5\u672c\u8a9e\uff09",
                      "\u753b\u50cfURL", "URL"]
            with sheet.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(header)
                writer.writerow(["in", "2026-09-10", "Creta Rs 19.21 lakh", "Creta Rs 19.21 lakh",
                                 "19.21" + MAN + RUPEES, "19.21" + RUPEES,
                                 "https://example.com/a.jpg", "https://example.com/a"])
            with patch.object(sys, "argv", ["publisher", "--sheet", str(sheet)]), patch.object(
                publisher, "validate_japanese_news_items", side_effect=RuntimeError("stop-before-writes")
            ) as validate:
                with self.assertRaisesRegex(RuntimeError, "stop-before-writes"):
                    publisher.main()
                items = validate.call_args.args[0]
                self.assertEqual(items[0]["title"], "192.1" + MAN + RUPEES)
                self.assertEqual(items[0]["desc"], "192.1" + MAN + RUPEES)


if __name__ == "__main__":
    unittest.main()
