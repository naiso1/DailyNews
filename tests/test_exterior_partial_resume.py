"""Preserve validated partial work while keeping publication checks strict."""
from contextlib import ExitStack, redirect_stdout
import csv
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import auto_update_daily_news as updater
from dailynews.editions import get_edition


class ExteriorPartialResumeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.edition = get_edition("exterior", self.temp.name)
        self.edition.config_dir.mkdir(parents=True)
        self.edition.collection_settings_path.write_text(
            json.dumps({"exterior": {"selection": {"minimum_score": 60}}}), encoding="utf-8")
        self.edition.ensure_directories()
        self.news = self.edition.content_dir / "news_data.js"
        self.insights = self.edition.content_dir / "insights_data.js"
        self.insights.write_text("window.DAILY_INSIGHTS = [];\n", encoding="utf-8")
        self.sheet = self.edition.runtime_dir / "sheet2_llm_targets.csv"
        with self.sheet.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["国", "日付", "タイトル（日本語）", "内容（日本語）", "URL", "画像URL", "LLM判定", "内装関連度"])
            writer.writerow(["日本", "2026-09-21", "発光グリル", "外装の発光グリルを試作した。", "https://example.com/grille", "", "対象", 80])
            writer.writerow(["日本", "2026-09-21", "交換式バンパー", "バンパーの交換構造を開発した。", "https://example.com/bumper", "", "対象", 80])
        self.analysis = "発光グリル[jp1]の試作が進む。バンパー[jp2]では交換構造を検討できる。"
        self.ideas = [
            {"title": "光学グリルの視認性", "desc": "発光グリルの試作を参考に、昼夜の輝度と均一性を評価する。", "sourceNewsIds": ["jp1"]},
            {"title": "分割バンパーの補修性", "desc": "交換式バンパーを起点に、破損部のみ外せる締結部を検討して工数を調べる。", "sourceNewsIds": ["jp2"]},
        ]
        self.sources = [{"newsId": "jp1", "title": "グリル", "desc": "発光グリルを試作。"},
                        {"newsId": "jp2", "title": "バンパー", "desc": "交換構造を開発。"}]

    def mocked_run(self, outputs):
        stack = ExitStack()
        stack.enter_context(patch.multiple(updater, EDITION=self.edition, NEWS_PATH=self.news, INSIGHTS_PATH=self.insights))
        stack.enter_context(patch.dict(os.environ, {"TARGET_DATES": ""}))
        stack.enter_context(patch.object(sys, "argv", ["publisher", "--edition", "exterior", "--sheet", str(self.sheet), "--skip-html", "--skip-images"]))
        stack.enter_context(patch("ニュース収集.source_highlights.enrich_items"))
        stack.enter_context(patch.object(updater, "rewrite_analysis_with_refs", side_effect=lambda _e, _m, _c, text, _s: text))
        stack.enter_context(patch.object(updater, "ensure_analysis_ref_quality", side_effect=lambda _e, _m, _c, text, _s: text))
        stack.enter_context(patch.object(updater, "shorten_analysis_with_llm", side_effect=lambda _e, _m, text: text))
        stack.enter_context(redirect_stdout(io.StringIO()))
        llm = stack.enter_context(patch.object(updater, "call_llm", side_effect=outputs))
        return stack, llm

    def checkpoint(self):
        return json.loads((self.edition.runtime_dir / "insights_checkpoint_2026-09-21.json").read_text(encoding="utf-8"))["countries"]["jp"]

    def test_partial_idea_survives_bounded_failures_and_resume_only_requests_missing_one(self):
        invalid = {**self.ideas[1], "sourceNewsIds": ["jp999"]}
        first = [json.dumps({"analysis": self.analysis, "ideas": self.ideas[:1]}, ensure_ascii=False),
                 json.dumps({"ideas": [invalid]}, ensure_ascii=False),
                 json.dumps({"ideas": self.ideas[:1]}, ensure_ascii=False)]
        stack, llm = self.mocked_run(first)
        with stack:
            with self.assertRaisesRegex(RuntimeError, "Exterior insights incomplete for: jp"):
                updater.main()
            self.assertEqual(llm.call_count, 3)  # initial request + two bounded supplements
        saved = self.checkpoint()
        self.assertEqual(saved["analysis"], self.analysis)
        self.assertEqual(len(saved["ideas"]), 1)
        self.assertFalse((self.edition.content_dir / "publication_status.json").exists())
        self.assertEqual(self.insights.read_text(encoding="utf-8"), "window.DAILY_INSIGHTS = [];\n")
        stack, llm = self.mocked_run([json.dumps({"analysis": "", "ideas": self.ideas[1:]}, ensure_ascii=False)])
        with stack:
            updater.main()
            llm.assert_called_once()
            self.assertIn("不足しているideasだけ", llm.call_args.args[2])
            self.assertIn("ideasは最大1件", llm.call_args.args[2])
        self.assertEqual(self.checkpoint()["analysis"], self.analysis)
        self.assertEqual(len(self.checkpoint()["ideas"]), 2)
        self.assertEqual(self.insights.read_text(encoding="utf-8").count('date: "2026-09-21"'), 1)

    def test_two_ideas_are_saved_when_analysis_fails_and_resume_only_requests_analysis(self):
        uncited = "根拠が示されていない結論。"
        stack, llm = self.mocked_run([json.dumps({"analysis": uncited, "ideas": self.ideas}, ensure_ascii=False), uncited, uncited])
        with stack:
            with self.assertRaisesRegex(RuntimeError, "Exterior insights incomplete"):
                updater.main()
            self.assertEqual(llm.call_count, 3)
        self.assertEqual(self.checkpoint()["analysis"], "")
        self.assertEqual(len(self.checkpoint()["ideas"]), 2)
        stack, llm = self.mocked_run([json.dumps({"analysis": self.analysis, "ideas": []}, ensure_ascii=False)])
        with stack:
            updater.main()
            llm.assert_called_once()
            self.assertIn("analysisだけ", llm.call_args.args[2])
        self.assertEqual(self.checkpoint()["analysis"], self.analysis)

    def test_numeric_duplicate_ref_is_removed_without_guessing_an_unknown_id(self):
        idea = {**self.ideas[0], "desc": "グリル[1]の形状を検討する。[1] [jp1]"}
        fixed = updater.prepare_exterior_idea_sources([idea], self.sources)[0]
        self.assertNotIn("[1]", fixed["desc"])
        self.assertTrue(fixed["desc"].endswith("[jp1]"))
        for invalid in ({**idea, "desc": "グリル[999]を検討する。"},
                        {**idea, "desc": "グリル[jp2]を検討する。"},
                        {**idea, "desc": "グリルを検討する。", "sourceNewsIds": []}):
            with self.subTest(invalid=invalid), self.assertRaises(RuntimeError):
                updater.prepare_exterior_idea_sources([invalid], self.sources)

    def test_invalid_idea_does_not_discard_a_valid_sibling(self):
        with patch.object(updater, "EDITION", self.edition):
            result = updater.validated_exterior_ideas(
                [{**self.ideas[0], "sourceNewsIds": ["cn999"]}, self.ideas[1]], self.sources)
        self.assertEqual([x["title"] for x in result], [self.ideas[1]["title"]])

    def test_stale_fingerprint_does_not_reuse_saved_components(self):
        checkpoint = {"edition_id": "exterior", "date": "2026-09-21", "countries": {"jp": {
            "fingerprint": "changed-source", "analysis": self.analysis, "ideas": self.ideas,
        }}}
        (self.edition.runtime_dir / "insights_checkpoint_2026-09-21.json").write_text(json.dumps(checkpoint), encoding="utf-8")
        stack, llm = self.mocked_run([json.dumps({"analysis": self.analysis, "ideas": self.ideas}, ensure_ascii=False)])
        with stack:
            updater.main()
            llm.assert_called_once()
            self.assertNotIn("考察は検証済み", llm.call_args.args[2])


if __name__ == "__main__":
    unittest.main()
