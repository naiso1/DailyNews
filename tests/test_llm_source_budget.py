"""Prompts stay inside the model context; raw bodies never become summaries."""
import ast
from pathlib import Path
import unittest

import auto_update_daily_news as publisher

ROOT = Path(__file__).resolve().parents[1]


def bounded_llm_source():
    tree = ast.parse((ROOT / "ニュース収集/google_search_script.py").read_text(encoding="utf-8-sig"))
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "bounded_llm_source")
    env = {"LLM_SOURCE_CHAR_BUDGET": 3500}
    exec(compile(ast.Module(body=[node], type_ignores=[]), "bounded", "exec"), env)
    return env["bounded_llm_source"]


class LlmSourceBudgetTests(unittest.TestCase):
    def test_full_body_stored_as_content_is_not_sent_twice(self):
        body = "内装の新しいシート表皮を採用した。" * 500
        content, html = bounded_llm_source()(body, body)
        self.assertEqual((len(content), html), (3500, ""))

    def test_short_snippet_leaves_room_for_the_article_text(self):
        content, html = bounded_llm_source()("RSS snippet.", "記事本文。" * 2000)
        self.assertEqual(content, "RSS snippet.")
        self.assertEqual(len(content) + len(html), 3500)

    def test_publisher_drops_raw_article_bodies(self):
        items = [dict(country="jp", url="a", desc="要約。"), dict(country="jp", url="b", desc="本文。" * 3000),
                 dict(country="paper", url="c", desc="Abstract " * 100)]
        self.assertEqual([item["url"] for item in publisher.drop_unsummarised_bodies(items)], ["a", "c"])


if __name__ == "__main__":
    unittest.main()
