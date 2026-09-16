"""Validate the issue receipt at runner count/resume boundaries without processes."""
import ast
import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class RunnerDigestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = ROOT / "ニュース収集/run_search_and_update.py"
        tree = ast.parse(source.read_text(encoding="utf-8-sig"))
        names = {"validate_exterior_sheet_receipt", "count_sheet_targets", "validate_resume_sheet"}
        nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
        cls.env = {"csv": csv, "json": json, "Path": Path}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), cls.env)

    def fixture(self, directory, rows, **overrides):
        path = Path(directory) / "sheet2_llm_targets.csv"
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["日付", "国", "URL"])
            writer.writeheader()
            writer.writerows(rows)
        receipt = {"edition_id": "exterior", "completed": True, "target_dates": ["2026-09-15"],
                   "issue_date": "2026-09-15", "lookback_start": "2026-09-09",
                   "source_dates": sorted({row["日付"] for row in rows}), "selected_count": len(rows)}
        receipt.update(overrides)
        path.with_name("collection_result.json").write_text(json.dumps(receipt), encoding="utf-8")
        return path

    def test_supplement_only_issue_is_counted_and_can_resume(self):
        rows = [{"日付": "2026-09-12", "国": "日本", "URL": "https://example.com/a"}]
        with tempfile.TemporaryDirectory() as directory:
            path = self.fixture(directory, rows)
            before = path.read_bytes()
            self.assertEqual(self.env["count_sheet_targets"](path, {"2026-09-15"}, edition_id="exterior"), 1)
            self.assertEqual(self.env["validate_resume_sheet"](path, ["2026-09-15"], edition_id="exterior"), 1)
            self.assertEqual(path.read_bytes(), before)

    def test_mixed_original_dates_are_valid_only_with_matching_new_receipt(self):
        rows = [{"日付": day, "国": country, "URL": f"https://example.com/{index}"}
                for index, (day, country) in enumerate((("2026-09-15", "米国"), ("2026-09-09", "インド")))]
        with tempfile.TemporaryDirectory() as directory:
            path = self.fixture(directory, rows)
            self.assertEqual(self.env["validate_resume_sheet"](path, ["2026-09-15"], edition_id="exterior"), 2)
            with self.assertRaises(ValueError):
                self.env["validate_resume_sheet"](path, ["2026-09-15"])
            self.assertEqual(self.env["count_sheet_targets"](path, {"2026-09-15"}), 1)

    def test_stale_incomplete_mismatched_or_out_of_window_issue_is_rejected(self):
        rows = [{"日付": "2026-09-12", "国": "中国", "URL": "https://example.com/a"}]
        invalid = ({"completed": False}, {"edition_id": "interior"}, {"issue_date": "2026-09-14"},
                   {"selected_count": 2}, {"source_dates": ["2026-09-13"]}, {"lookback_start": "2026-09-13"},
                   {"lookback_start": "2026-09-08"}, {"target_dates": ["2026-09-14"]})
        with tempfile.TemporaryDirectory() as directory:
            for changes in invalid:
                with self.subTest(changes=changes):
                    path = self.fixture(directory, rows, **changes)
                    for name in ("validate_resume_sheet", "count_sheet_targets"):
                        with self.assertRaises(ValueError):
                            self.env[name](path, ["2026-09-15"], edition_id="exterior")

    def test_empty_new_issue_counts_zero_but_cannot_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.fixture(directory, [])
            self.assertEqual(self.env["count_sheet_targets"](path, {"2026-09-15"}, edition_id="exterior"), 0)
            with self.assertRaises(ValueError):
                self.env["validate_resume_sheet"](path, ["2026-09-15"], edition_id="exterior")

    def test_legacy_exterior_keeps_original_date_resume_rule(self):
        rows = [{"日付": "2026-09-15", "国": "日本", "URL": "https://example.com/a"}]
        with tempfile.TemporaryDirectory() as directory:
            path = self.fixture(directory, rows, issue_date=None)
            self.assertEqual(self.env["validate_resume_sheet"](path, ["2026-09-15"], edition_id="exterior"), 1)


if __name__ == "__main__":
    unittest.main()
