"""Offline resume preflight; do not import the scheduled runner."""

import ast
import csv
from pathlib import Path
import tempfile
import unittest


class ResumeSheetTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        source = next(root.glob("*/run_search_and_update.py"))
        tree = ast.parse(source.read_text(encoding="utf-8-sig"))
        nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "validate_resume_sheet"]
        env = {"csv": csv, "Path": Path}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), env)
        self.validate = env["validate_resume_sheet"]

    def test_matching_export_is_accepted(self):
        self.check(["2026-09-10", "2026-09-10"], ["2026-09-10"], 2)

    def test_stale_empty_missing_or_mixed_dates_are_rejected(self):
        for rows, dates in [
            ([], ["2026-09-10"]),
            (["2026-09-09"], ["2026-09-10"]),
            (["2026-09-09", "2026-09-10"], ["2026-09-10"]),
            (["2026-09-10"], ["2026-09-09", "2026-09-10"]),
            ([""], ["2026-09-10"]),
            (["2026-09-10"], []),
        ]:
            with self.subTest(rows=rows, dates=dates), self.assertRaises(ValueError):
                self.check(rows, dates, None)

    def check(self, rows, dates, expected):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sheet.csv"
            with path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["\u65e5\u4ed8"])
                writer.writerows([[day] for day in rows])
            before = path.read_bytes()
            try:
                self.assertEqual(self.validate(path, dates), expected)
            finally:
                self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
