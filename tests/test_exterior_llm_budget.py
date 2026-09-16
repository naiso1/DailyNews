"""Oversized Chinese source regression; no collector import or real HTTP/LLM."""

import ast
from copy import deepcopy
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dailynews.exterior import assessment_prompt
from dailynews.llm_budget import (
    CHAT_TOKEN_RESERVE, IMAGE_TOKEN_RESERVE, OMISSION, budget_exterior_payload,
)


class ExteriorLLMBudgetTests(unittest.TestCase):
    def assert_fits(self, payload, context=8192):
        text_bytes, images = 0, 0
        for message in payload["messages"]:
            content = message["content"]
            if isinstance(content, str):
                text_bytes += len(content.encode("utf-8"))
            else:
                for part in content:
                    if part["type"] == "text":
                        text_bytes += len(part["text"].encode("utf-8"))
                    elif part["type"] == "image_url":
                        images += 1
        self.assertLessEqual(text_bytes + payload["max_tokens"] + CHAT_TOKEN_RESERVE
                             + images * IMAGE_TOKEN_RESERVE, context)

    def test_8000_chinese_characters_keep_rules_head_and_qualification_tail(self):
        instructions = (ROOT / "editions/exterior/prompts/collection.md").read_text(encoding="utf-8")
        article = "格栅设计采用树脂材料。" + "汽车外饰的设计与材料。" * 800 + "仅为试验方案，尚未量产。"
        prompt = instructions + "\nタイトル:\n中国外装製品\n本文:\n" + article + '\nReturn JSON: {"relevance":true}'
        original = {"messages": [{"role": "user", "content": prompt},
                                 {"role": "assistant", "content": "<think>\n</think>\n"}]}
        before = deepcopy(original)
        bounded = budget_exterior_payload(original)
        text = bounded["messages"][0]["content"]
        self.assertTrue(text.startswith(instructions))
        self.assertIn("格栅设计采用树脂材料。", text)
        self.assertIn("尚未量产", text)
        self.assertTrue(text.endswith('Return JSON: {"relevance":true}'))
        self.assertIn(OMISSION, text)
        self.assertNotIn("\ufffd", text)
        self.assertEqual(original, before)
        self.assert_fits(bounded)

    def test_assessment_reserves_image_and_preserves_its_data_url(self):
        prompt = assessment_prompt("中国乘用车", "保险杠采用新材料。" * 1000, "https://example.test/news", "検証段階。")
        payload = {"messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,FAKE"}},
        ]}, {"role": "assistant", "content": '{"score":'}]}
        bounded = budget_exterior_payload(payload)
        self.assertIn("Use semantic relevance", bounded["messages"][0]["content"][0]["text"])
        self.assertEqual(bounded["messages"][0]["content"][1], payload["messages"][0]["content"][1])
        self.assert_fits(bounded)

    def test_summary_reserves_system_rules_and_honors_smaller_context(self):
        rules = "Keep source qualifications and original currency units. " * 8
        payload = {"max_tokens": 700, "messages": [
            {"role": "system", "content": rules},
            {"role": "user", "content": "Summarize as JSON.\nSource content: " + "原文信息。" * 3000},
            {"role": "assistant", "content": "<think>\n</think>\n"},
        ]}
        bounded = budget_exterior_payload(payload, 4096)
        self.assertEqual(bounded["messages"][0]["content"], rules)
        self.assertEqual(bounded["max_tokens"], 700)
        self.assert_fits(bounded, 4096)

    def test_short_text_unchanged_and_oversized_fixed_rules_rejected(self):
        short = {"messages": [{"role": "user", "content": "短い本文。"}]}
        self.assertEqual(budget_exterior_payload(short)["messages"], short["messages"])
        with self.assertRaises(ValueError):
            budget_exterior_payload({"messages": [{"role": "system", "content": "文" * 4000}]})
        with self.assertRaises(ValueError):
            budget_exterior_payload({"messages": [{"role": "user", "content": "指示" * 4000 + "\nArticle: text"}]})

    def test_transport_only_budgets_exterior_and_reuses_bounded_payload_on_reload(self):
        # The collector historically has startup side effects; extract this one
        # transport function without importing or running collection setup.
        path = ROOT / "ニュース収集" / "google_search_script.py"
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_post_llm")
        session = Mock()
        response = Mock()
        session.post.return_value = response
        namespace = {"EDITION": SimpleNamespace(id="exterior"), "LLM_CONTEXT_LENGTH": "8192",
                     "LLM_ENDPOINT": "http://127.0.0.1:1234/v1/chat/completions",
                     "requests": SimpleNamespace(Session=Mock(return_value=session)),
                     "_is_loopback_url": lambda url: True,
                     "_response_needs_model_reload": lambda response: True,
                     "_ensure_llm_model_loaded": lambda: True}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), "exec"), namespace)
        payload = {"messages": [{"role": "user", "content": "Title: test\nArticle: " + "格栅" * 4000}]}
        namespace["_post_llm"](json=payload, timeout=5)
        self.assertEqual(session.post.call_count, 2)
        for call in session.post.call_args_list:
            self.assert_fits(call.kwargs["json"])
        namespace["EDITION"].id = "interior"
        namespace["_post_llm"](json=payload, timeout=5)
        self.assertIs(session.post.call_args.kwargs["json"], payload)
        self.assertNotIn("max_tokens", payload)


if __name__ == "__main__":
    unittest.main()
