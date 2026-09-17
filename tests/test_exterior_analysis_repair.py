"""Final regional analysis failures must not invent references or rerun good regions."""
from contextlib import redirect_stdout
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


class ExteriorAnalysisRepairTests(unittest.TestCase):
    def setUp(self):
        self.sources = [
            {"newsId": "eu1", "title": "バンパーを刷新", "desc": "試作車の専用バンパーを確認した。"},
            {"newsId": "eu2", "title": "外装カラー追加", "desc": "外装カラーの選択肢を増やした。"},
            {"newsId": "eu3", "title": "グリルを変更", "desc": "グリルの加飾形状を変更した。"},
            {"newsId": "eu4", "title": "新車計画", "desc": "新車の投入計画を発表した。"},
        ]
        self.cited = "試作車のバンパー[eu1]が刷新された。外装カラー[eu2]とグリル[eu3]でも選択肢が広がる。"
        self.incomplete = self.cited + "これらから、外装開発では素材と意匠の両立が求められる。"
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.edition = get_edition("exterior", self.directory.name)
        self.edition_patch = patch.object(updater, "EDITION", self.edition)
        self.edition_patch.start()
        self.addCleanup(self.edition_patch.stop)

    def finish(self, text=None, **kwargs):
        with redirect_stdout(io.StringIO()):
            return updater.finalize_exterior_analysis(
                "http://unused", "mock", "eu", "2026-09-17",
                self.incomplete if text is None else text, self.sources, **kwargs,
            )

    def test_valid_analysis_or_previous_candidate_never_calls_model(self):
        with patch.object(updater, "call_llm") as llm:
            self.assertEqual(self.finish(self.cited), self.cited)
            self.assertEqual(self.finish(prior_candidates=(self.cited,)), self.cited)
        llm.assert_not_called()

    def test_final_repair_is_one_call_and_must_use_current_source_ids(self):
        fixed = self.cited + "カラー選択肢の拡大[eu2]を受け、塗装材の比較を開発上の仮説とする。"
        with patch.object(updater, "call_llm", return_value=fixed) as llm:
            result = self.finish()
        self.assertEqual(result, fixed)
        llm.assert_called_once()
        prompt = llm.call_args.args[2]
        self.assertIn("試作車の専用バンパーを確認した。", prompt)
        self.assertIn("無関係なIDを割り当てない", prompt)
        self.assertTrue(updater.exterior_analysis_complete(result, self.sources))

    def test_recorded_failure_pattern_drops_only_uncited_closing_inference(self):
        # The overnight model repeated the uncited conclusion even after repair.
        with patch.object(updater, "call_llm", return_value=self.incomplete) as llm:
            result = self.finish()
        llm.assert_called_once()
        self.assertEqual(result, self.cited)
        self.assertEqual(updater.analysis_unique_refs(result), {"eu1", "eu2", "eu3"})
        self.assertNotIn("素材と意匠", result)

    def test_failed_repair_does_not_keep_new_claims_or_arbitrary_references(self):
        bad_repair = self.cited + "全車で採用済み[cn999]。"
        with patch.object(updater, "call_llm", return_value=bad_repair):
            result = self.finish()
        self.assertEqual(result, self.cited)
        self.assertNotIn("cn999", result)
        self.assertNotIn("採用済み", result)
        self.assertFalse(updater.exterior_analysis_complete(bad_repair, self.sources))

    def test_fallback_does_not_remove_caveats_or_uncited_middle_sentences(self):
        for text in (
            self.cited + "ただし試作車なので量産仕様は未確認である。",
            self.cited + "豊田合成の検討では効果を断定できない点に注意が必要だ。",
            "外装開発への示唆をまとめる。" + self.cited,
            "バンパー[eu1]を刷新した。販売状況は不明だ。カラー[eu2]とグリル[eu3]も変わる。",
        ):
            with self.subTest(text=text):
                self.assertEqual(updater.cited_exterior_analysis_prefix(text, self.sources), "")

    def test_fallback_requires_multiple_sentences_and_sufficient_real_refs(self):
        for text in (
            "バンパー[eu1,eu2,eu3]を見直した。これらから、開発への示唆を得る。",
            "バンパー[eu1]を見直した。加飾[eu1]も変わる。これらから、開発への示唆を得る。",
            "バンパー[eu1]を見直した。加飾[eu2]も変わる。これらから、開発への示唆を得る。 関連画像: [eu3]",
        ):
            with self.subTest(text=text):
                self.assertEqual(updater.cited_exterior_analysis_prefix(text, self.sources), "")
        # Sparse regions can still keep two grounded sentences from one article.
        sparse = "バンパー[eu1]を見直した。専用形状[eu1]を試作する。これらから、開発への示唆を得る。"
        self.assertEqual(updater.cited_exterior_analysis_prefix(sparse, self.sources[:1]),
                         "バンパー[eu1]を見直した。専用形状[eu1]を試作する。")

    def test_failure_diagnostic_is_private_and_excludes_secrets_and_exceptions(self):
        secret = "secret-provider-token-value"
        candidate = "根拠が示されていない考察。 " + secret
        with patch.dict(os.environ, TEST_API_TOKEN=secret), patch.object(
            updater, "call_llm", side_effect=RuntimeError("Authorization: Bearer " + secret)
        ) as llm:
            self.assertEqual(self.finish(candidate), candidate)
        llm.assert_called_once()
        path = self.edition.runtime_dir / "insights_analysis_failure_2026-09-17_eu.json"
        raw = path.read_text(encoding="utf-8")
        saved = json.loads(raw)
        self.assertNotIn(secret, raw)
        self.assertNotIn("Authorization", raw)
        self.assertEqual(saved["repair_error"], "LLM_UNAVAILABLE")
        self.assertIn("UNCITED_SENTENCES", saved["candidates"][0]["reasons"])
        self.assertIn("NO_VALID_CITATIONS", saved["candidates"][0]["reasons"])
        self.assertEqual(saved["source_ids"], ["eu1", "eu2", "eu3", "eu4"])
        self.assertFalse(self.edition.content_dir.exists())

    def test_dry_run_failure_never_writes_diagnostic(self):
        with patch.object(updater, "call_llm", return_value="根拠なし。"):
            self.finish("根拠なし。", dry_run=True)
        self.assertFalse(self.edition.runtime_dir.exists())

    def test_publication_checkpoints_repaired_analysis_before_advancing_marker(self):
        self.edition.config_dir.mkdir(parents=True)
        self.edition.collection_settings_path.write_text(
            json.dumps({"exterior": {"selection": {"minimum_score": 60}}}), encoding="utf-8")
        self.edition.ensure_directories()
        sheet = self.edition.runtime_dir / "sheet2_llm_targets.csv"
        with sheet.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["国", "日付", "タイトル（日本語）", "内容（日本語）", "URL", "画像URL", "LLM判定", "内装関連度"])
            for source in self.sources[:3]:
                writer.writerow(["欧州", "2026-09-17", source["title"], source["desc"],
                                 "https://example.com/" + source["newsId"], "", "対象", 80])
        news = self.edition.content_dir / "news_data.js"
        insights = self.edition.content_dir / "insights_data.js"
        insights.write_text("window.DAILY_INSIGHTS = [];\n", encoding="utf-8")
        ideas = [
            {"title": "交換式バンパー", "desc": "専用バンパーを分割して交換する取付構造を提案する。", "sourceNewsIds": ["eu1"]},
            {"title": "塗装色の試験片", "desc": "外装カラーを比較する加飾試験片を提案する。", "sourceNewsIds": ["eu2"]},
        ]
        argv = ["publisher", "--edition", "exterior", "--sheet", str(sheet), "--skip-html", "--skip-images"]
        with patch.multiple(updater, NEWS_PATH=news, INSIGHTS_PATH=insights), \
                patch.object(sys, "argv", argv), patch("ニュース収集.source_highlights.enrich_items"), \
                patch.object(updater, "rewrite_analysis_with_refs", side_effect=lambda _e, _m, _c, text, _s: text), \
                patch.object(updater, "ensure_analysis_ref_quality", side_effect=lambda _e, _m, _c, text, _s: text), \
                patch.object(updater, "shorten_analysis_with_llm", side_effect=lambda _e, _m, text: text), \
                patch.object(updater, "call_llm", side_effect=[json.dumps({"analysis": self.incomplete, "ideas": ideas}), self.incomplete]) as llm, \
                redirect_stdout(io.StringIO()):
            updater.main()
        self.assertEqual(llm.call_count, 2)
        checkpoint = updater.read_exterior_checkpoint("2026-09-17")
        self.assertEqual(checkpoint["countries"]["eu"]["analysis"], self.cited)
        self.assertEqual(len(checkpoint["countries"]["eu"]["ideas"]), 2)
        status = json.loads((self.edition.content_dir / "publication_status.json").read_text(encoding="utf-8"))
        self.assertEqual(status["processed_through"], "2026-09-17")
        self.assertIn(self.cited, insights.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
