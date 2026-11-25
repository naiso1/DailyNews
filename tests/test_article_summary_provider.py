import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from dailynews import article_summaries as provider

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ニュース収集"))
import google_search_script as collector


class ArticleSummaryProviderTests(unittest.TestCase):
    title = "日産が新型シートを発表"
    body = "日産は新型車に電動シートを採用した。"

    def setUp(self):
        for context in (
            patch.dict(os.environ, DAILYNEWS_SUMMARY_PROVIDER="copilot"),
            patch.object(collector, "_summary_cache", {}),
            patch.object(collector, "USE_LLM", True),
            patch.object(collector, "fetch_article_text", return_value=""),
            patch.object(provider, "_retry_after", 0.0),
            patch.object(provider, "_last_failure", ""),
        ):
            context.start()
            self.addCleanup(context.stop)
        self.answer = json.dumps({"title": self.title, "summary": self.body}, ensure_ascii=False)

    def article(self, url="https://example.com/news"):
        return collector.summarize_article(self.title, self.body, url, "日本")

    def test_valid_answer_uses_copilot_and_cache(self):
        with patch.object(provider, "_run_worker", return_value=("DONE", self.answer)) as worker, \
             patch.object(collector, "call_llm_text", side_effect=AssertionError("Unexpected local call")):
            self.assertEqual(self.article(), (self.title, self.body))
            self.assertEqual(self.article(), (self.title, self.body))
        worker.assert_called_once()
        prompt = worker.call_args.args[0]
        self.assertIn(self.body, prompt)
        self.assertNotIn("https://example.com", prompt)

    def test_unusable_answer_goes_to_original_local_prompt(self):
        for answer in ("unexpected", '{"title":"No translation","summary":"Not Japanese."}',
                       json.dumps({"title": self.title, "summary": "あ" * 150 + "。"})):
            with self.subTest(answer=answer[:20]), patch.object(collector, "_summary_cache", {}), \
                 patch.object(provider, "_run_worker", return_value=("DONE", answer)), \
                 patch.object(collector, "call_llm_text", return_value=self.answer) as local:
                self.assertEqual(self.article(), (self.title, self.body))
                self.assertIn("https://example.com/news", local.call_args.args[0])

    def test_unavailable_worker_uses_local_and_recovers_after_cooldown(self):
        with patch.object(provider, "_run_worker", side_effect=[("AUTH_REQUIRED", ""), ("DONE", self.answer)]) as worker, \
             patch.object(provider.time, "monotonic", return_value=1000) as clock, \
             patch.object(collector, "call_llm_text", return_value=self.answer) as local:
            self.article()
            self.article("https://example.com/2")
            clock.return_value = 1610
            self.article("https://example.com/3")
            self.assertEqual(worker.call_count, 2)
            self.assertEqual(local.call_count, 2)

    def test_previously_submitted_article_does_not_block_next_article(self):
        with patch.object(provider, "_run_worker", side_effect=[("ALREADY_SUBMITTED", ""), ("DONE", self.answer)]), \
             patch.object(collector, "call_llm_text", return_value=self.answer) as local:
            self.article()
            self.article("https://example.com/2")
            local.assert_called_once()

    def test_local_override_skips_copilot(self):
        with patch.dict(os.environ, DAILYNEWS_SUMMARY_PROVIDER="local"), \
             patch.object(provider, "_run_worker", side_effect=AssertionError("Unexpected Copilot call")), \
             patch.object(collector, "call_llm_text", return_value=self.answer):
            self.assertEqual(self.article(), (self.title, self.body))
