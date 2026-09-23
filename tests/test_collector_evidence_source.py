"""Keep assessment quotations grounded in the persisted original article body."""
import ast
from contextlib import redirect_stdout
import io
import json
import math
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from dailynews.article_text import unusable_text
from dailynews.deduplication import normalize_article_url
from dailynews.editorial_policy import EVIDENCE_COLUMNS, apply_policy, extract_evidence


ROOT = Path(__file__).resolve().parents[1]
SNIPPET = "A supplier announces an update for passenger-car interiors."
QUOTE = "The door trim integrates a capacitive sensor under its decorative surface."
BODY = QUOTE + " The surface responds to light finger pressure and hides the switches behind the trim. The supplier will compare installation and validation methods for the new design."
EVIDENCE = {"target_component": "ドアトリムの静電容量センサー",
            "new_information": "加飾表面の下へ静電容量センサーを一体化する。",
            "development_reference": "加飾面へのセンサー配置と作動確認の設計比較に利用する。",
            "source_quote": QUOTE}


def isolated_collector():
    names = {"interior_evidence_source", "store_exterior_assessment", "collector_article",
             "enrich_results", "enrich_existing_df"}
    source = (ROOT / "ニュース収集/google_search_script.py").read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    if len(nodes) != len(names):
        raise AssertionError("Collector helper names changed")
    env = {"pd": None, "math": math, "json": json,
           "EDITION": SimpleNamespace(id="interior"), "USE_LLM": True,
           "EVIDENCE_COLUMNS": EVIDENCE_COLUMNS, "extract_evidence": extract_evidence,
           "apply_editorial_policy": apply_policy, "unusable_text": unusable_text,
           "normalize_article_url": normalize_article_url,
           "is_valid_article_url": lambda url, **kwargs: str(url).startswith("https://") and "news.google.com" not in str(url),
           "fetch_article_text": Mock(return_value=BODY),
           "compute_relevance": Mock(return_value=(0.9, "高", ["door trim"])),
           "call_llm_classify": Mock(return_value=("対象", "あり")),
           "call_llm_interior_assessment": Mock(return_value={"score": 85, "reason": "センサー内蔵加飾の比較",
                 "image_interior": None, "evidence": EVIDENCE, "policy_decision": "keep"}),
           "summarize_article": Mock(return_value=("加飾面の下にセンサーを配置", "静電容量センサーをドアトリムへ一体化する。")),
           "check_url_ok": Mock(return_value=True), "is_missing_url": lambda value: not value,
           "FETCH_MISSING_IMAGES": False, "LLM_SAVE_INTERVAL": 0, "PROGRESS_EVERY": 20,
           "LLM_ONLY": False, "RESUME_LLM": False, "PROCESS_LLM_SKIPPED": False, "ENRICH_ONLY": False}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "isolated-evidence-source", "exec"), env)
    return env


class CollectorEvidenceSourceTests(unittest.TestCase):
    def setUp(self):
        self.env = isolated_collector()
        self.row = {"タイトル": "Supplier develops capacitive door trim", "内容": SNIPPET,
                    "URL": "https://example.com/capacitive-trim", "画像URL": "https://example.com/trim.jpg",
                    "国": "米国", "日付": "2026-09-21", "ソース": "Example", "LLM判定": "対象",
                    "採用根拠_状態": "", "LLM後処理": "実施", "内装関連度": "", "内装判定理由": "",
                    "内装関連度_原判定": "", "内装判定理由_原判定": ""}

    def assert_preserved_evidence(self, row):
        self.assertEqual(row["内容"], BODY)
        self.assertEqual(row["採用根拠_出典"], QUOTE)
        article = self.env["collector_article"](row)
        self.assertEqual(apply_policy(article)["decision"], "keep")
        self.assertEqual(self.env["call_llm_interior_assessment"].call_args.args[1], BODY)

    def test_new_articles_assess_and_store_the_body_used_for_summary(self):
        with redirect_stdout(io.StringIO()):
            result = self.env["enrich_results"]([self.row.copy()])
        self.assert_preserved_evidence(result[0])
        self.assertEqual(self.env["summarize_article"].call_args.args[1], BODY)

    def test_saved_target_reassessment_preserves_source_and_evidence_columns(self):
        import pandas as pd
        self.env["pd"] = pd
        with redirect_stdout(io.StringIO()):
            result = self.env["enrich_existing_df"](pd.DataFrame([self.row]))
        self.assert_preserved_evidence(result.iloc[0])

    def test_fetch_failure_short_body_or_error_page_keeps_original_snippet(self):
        for body in ("", "Brief body", "Access Denied " * 30):
            with self.subTest(body=body[:25]):
                self.env["fetch_article_text"].return_value = body
                row = self.row.copy()
                self.assertEqual(self.env["interior_evidence_source"](row), SNIPPET)
                self.assertEqual(row["内容"], SNIPPET)

    def test_translated_summary_never_becomes_source_and_offline_is_unchanged(self):
        row = dict(self.row, **{"内容（日本語）": "要約だけに書かれた根拠を原文へ混ぜない。"})
        self.env["fetch_article_text"].return_value = ""
        self.assertEqual(self.env["interior_evidence_source"](row), SNIPPET)
        self.env["fetch_article_text"].reset_mock()
        for edition, use_llm in (("exterior", True), ("interior", False)):
            self.env["EDITION"] = SimpleNamespace(id=edition)
            self.env["USE_LLM"] = use_llm
            self.assertEqual(self.env["interior_evidence_source"](row), SNIPPET)
        self.env["fetch_article_text"].assert_not_called()


if __name__ == "__main__":
    unittest.main()
