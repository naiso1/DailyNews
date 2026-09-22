"""A model's explicit rejection is distinct from malformed or missing evidence."""
import ast
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import re
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from dailynews.editorial_policy import (EVIDENCE_COLUMNS, POLICY_VERSION, apply_policy, assessment_prompt,
                                        explicit_model_rejection, extract_evidence)


ROOT = Path(__file__).resolve().parents[1]


class CollectorRejectionOutcomeTests(unittest.TestCase):
    def setUp(self):
        names = {"call_llm_interior_assessment", "normalize_interior_score", "extract_json_object", "store_exterior_assessment"}
        tree = ast.parse((ROOT / "ニュース収集/google_search_script.py").read_text(encoding="utf-8-sig"))
        nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
        self.assertEqual(len(nodes), len(names))
        self.env = {"json": json, "re": re, "EDITION": SimpleNamespace(id="interior"),
                    "USE_LLM": True, "LLM_ERROR_LOGGED": False, "LLM_IMAGE_INPUT": False,
                    "LLM_CACHE": {}, "POLICY_VERSION": POLICY_VERSION, "EVIDENCE_COLUMNS": EVIDENCE_COLUMNS,
                    "apply_editorial_policy": apply_policy, "extract_evidence": extract_evidence,
                    "explicit_model_rejection": explicit_model_rejection, "assessment_prompt": assessment_prompt,
                    "editorial_feedback": Mock(return_value={"rules": []}),
                    "normalize_text": lambda value: re.sub(r"\s+", " ", value).strip(),
                    "LLM_MODEL": "fixture-model", "LLM_REASONING_EFFORT": "none", "LLM_TIMEOUT": 1,
                    "spread_interior_score": Mock(side_effect=lambda score, *args: score),
                    "calibrate_interior_score": Mock(return_value=(85, "")),
                    "record_exterior_llm_failure": Mock()}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "isolated-rejection-outcome", "exec"), self.env)

    def assess(self, *, score=10, reason="対象外。店舗の営業案内のみで内装機能の具体的な変更がない。", evidence=None):
        self.data = {"score": score, "reason": reason, "image_interior": True,
                     "evidence": dict.fromkeys(EVIDENCE_COLUMNS, "") if evidence is None else evidence}
        response = Mock(status_code=200)
        response.json.return_value = {"choices": [{"message": {"content": "```json\n" + json.dumps(self.data, ensure_ascii=False) + "\n```"}}]}
        self.env["_post_llm"] = Mock(return_value=response)
        self.output = io.StringIO()
        with redirect_stdout(self.output):
            return self.env["call_llm_interior_assessment"]("Interior showroom update", "The shop has extended its opening hours.", url="https://example.com/news")

    def test_explicit_rejection_keeps_raw_decision_even_when_picture_has_a_cabin(self):
        result = self.assess()
        self.assertEqual(result["policy_decision"], "exclude")
        self.assertEqual(result["raw_score"], 10)
        self.assertEqual(result["score"], 10)
        self.assertEqual(result["raw_reason"], self.data["reason"])
        self.env["spread_interior_score"].assert_not_called()
        row = {"LLM判定": "対象"}
        self.env["store_exterior_assessment"](row, result)
        self.assertEqual(row["LLM判定"], "非対象")
        self.assertEqual(row["採用根拠_状態"], "対象外")
        self.assertEqual(row["内装関連度_原判定"], 10)
        self.assertEqual(row["内装判定理由_原判定"], self.data["reason"])
        self.assertIn("[EDITORIAL_EXCLUDED]", self.output.getvalue())
        self.assertNotIn("[EDITORIAL_EVIDENCE_HELD]", self.output.getvalue())

    def test_low_score_without_clear_rejection_remains_held(self):
        self.assertIsNone(self.assess(reason="追加の原文情報が必要であり、現時点では判断できない。"))
        self.assertIn("[EDITORIAL_EVIDENCE_HELD]", self.output.getvalue())

    def test_high_score_or_incomplete_structure_is_not_misread_as_explicit_rejection(self):
        self.assertIsNone(self.assess(score=80))
        self.assertIsNone(self.assess(evidence={}))
        self.assertIsNone(self.assess(evidence={"target_component": "ドアトリム"}))
        self.assertIsNone(self.assess(reason="対象外ではないが、原文が不足している。"))

    def test_hmi_prompt_has_independent_criteria_and_preserves_grounding_requirements(self):
        prompt = assessment_prompt("Article", "Original source")
        self.assertIn("HMI・センシング・車室内の快適性も独立した採用分野", prompt)
        self.assertIn("一般的な機能紹介", prompt)
        self.assertIn("4項目すべて", prompt)
        self.assertIn("原文にない内容を採用根拠へ追加しない", prompt)


if __name__ == "__main__":
    unittest.main()
