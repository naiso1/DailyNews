"""Offline collector identity checks after URL resolution and Japanese repair."""
from contextlib import ExitStack, redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ニュース収集"))
from dailynews.editions import get_edition


class CollectorDeduplicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global collector
        import google_search_script as collector

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(collector, "OUTPUT_PAPERS_SHEET2", False))
        # These fixtures exercise identity/ranking; editorial value has its own suite.
        self.stack.enter_context(patch.object(collector, "apply_editorial_policy",
                                             return_value={"decision": "keep", "reason": "fixture", "evidence": {}}))

    def context(self, edition):
        context = get_edition(edition, Path(self.folder.name) / edition)
        context.config_dir.mkdir(parents=True, exist_ok=True)
        context.collection_settings_path.write_text(json.dumps({edition: {"selection": {
            "maximum_per_country": 10, "lookback_days": 7,
            "minimum_score": 60, "trend_minimum_score": 65,
            "require_original_image": edition == "interior"}}}), encoding="utf-8")
        context.ensure_directories()
        return context

    @staticmethod
    def row(key, title=None, body=None, country="日本", day="2026-09-20", score=80):
        title = title or f"新型グリル{key}を公開"
        body = body or f"新型グリル{key}の造形を発表した。"
        return {"国": country, "日付": day, "URL": f"https://example.com/{key}",
                "タイトル": title, "内容": body, "タイトル（日本語）": title,
                "内容（日本語）": body, "内装関連度": score,
                "画像URL": f"https://example.com/{key}.jpg", "LLM判定": "対象",
                "LLM後処理": "実施", "記事区分": "product", "トレンド分類": ""}

    @classmethod
    def kicks(cls, key, **kwargs):
        return cls.row(key, "日産キックス、英国サンダーランド工場で生産へ",
                       "日産は欧州向けキックスの生産に1億7000万ポンドを投資し、英国サンダーランド工場で2027年に生産する計画だ。グリルも刷新する。", **kwargs)

    def select(self, context, rows, history=(), summarize=None, dates=("2026-09-20",)):
        target = context.runtime_dir / "search_results.csv"
        with patch.object(collector, "EDITION", context), \
                patch.object(collector, "published_news", return_value=list(history)), \
                patch.object(collector, "summarize_article", side_effect=summarize or AssertionError("No LLM calls")), \
                patch.object(collector, "is_same_topic_text", side_effect=AssertionError("Legacy token heuristic must not gate articles")), \
                redirect_stdout(io.StringIO()):
            collector.build_sheet2_and_csv(collector.pd.DataFrame(rows), target, list(dates))
        return collector.pd.read_csv(target.with_name("sheet2_llm_targets.csv"), keep_default_na=False)

    def test_entry_normalizes_tracking_but_retains_article_query_ids(self):
        first, tracking, distinct = self.row("a"), self.row("b"), self.row("c")
        first["URL"] = "https://Example.com/article?id=1&utm_source=feed"
        tracking["URL"] = "https://example.com/article?id=1&source=rss"
        distinct["URL"] = "https://example.com/article?id=2"
        kept, decisions = collector.deduplicate_fetched_articles([first, tracking, distinct], [])
        self.assertEqual([item["URL"] for item in kept], ["https://example.com/article?id=1", distinct["URL"]])
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0]["reason"], "normalized_url")

    def test_recent_history_uses_explicit_dates_not_checkpoint_tail(self):
        newest = self.kicks("new")
        old = [self.row(f"old{i}", day="2026-01-01") for i in range(501)]
        history = collector.collection_history_articles([newest, *old])
        self.assertEqual(len(history), 500)
        self.assertEqual(history[0]["url"], newest["URL"])
        copied = self.kicks("copy")
        kept, decisions = collector.deduplicate_fetched_articles([copied], [*old, newest])
        self.assertEqual(kept, [])
        self.assertEqual(decisions[0]["duplicate_of"], newest["URL"])

    def test_global_dedup_runs_after_japanese_repair_and_does_not_refill(self):
        context = self.context("exterior")
        first, second = self.row("brief1", country="米国"), self.row("brief2", country="欧州")
        for index, row in enumerate((first, second)):
            row.update({"タイトル": f"Factory brief {index}", "内容": f"Source grille report {index}.",
                        "タイトル（日本語）": "", "内容（日本語）": "", "LLM後処理": "スキップ"})
        source = self.kicks("translated")
        calls = []

        def repair(*args):
            calls.append(args)
            return source["タイトル"], source["内容"]

        selected = self.select(context, [first, second], summarize=repair)
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(selected), 1)
        self.assertEqual(json.loads(selected.iloc[0]["関連URL"]), [second["URL"]])
        self.assertEqual(collector.SHEET2_RESULT["selected_count"], 1)
        self.assertEqual(collector.SHEET2_RESULT["duplicate_count"], 1)
        for name in ("summary_quarantine.json", "deduplication_review.json"):
            receipt = json.loads((context.runtime_dir / name).read_text(encoding="utf-8"))
            self.assertEqual(receipt["selected_count"], 1)
        self.assertEqual(sum(collector.SHEET2_RESULT["selected_by_country"].values()), 1)

    def test_interior_does_not_restore_recall_duplicates_below_ten(self):
        context = self.context("interior")
        first = self.row("recall1", "ダイハツ ムーヴ10091台をリコール",
                         "ダイハツはムーヴ10091台のリコールを届け出た。内装材が燃焼基準に適合しないおそれがある。")
        second = self.row("recall2", "ムーヴの内装材に不具合、ダイハツがリコール",
                          "ダイハツのムーヴ10091台がリコール対象となった。内装材の燃焼基準を満たさないおそれがある。")
        selected = self.select(context, [first, second])
        self.assertEqual(len(selected), 1)
        self.assertEqual(collector.SHEET2_RESULT["duplicate_count"], 1)

    def test_same_vehicle_independent_reviews_are_retained(self):
        context = self.context("interior")
        rows = [self.row("review1", "MG Hector Tomahawk EVを試乗、後席の快適性を評価",
                         "MG Hector Tomahawk EVは後席と荷室が広い。試乗ではシートの座り心地を確認した。"),
                self.row("review2", "MG Hector Tomahawk EVレビュー、操作性と乗り心地を検証",
                         "MG Hector Tomahawk EVを試乗した。乗り心地は良いが画面操作には課題が残った。")]
        selected = self.select(context, rows)
        self.assertEqual(len(selected), 2)
        self.assertEqual(collector.SHEET2_RESULT["duplicate_count"], 0)

    def test_interior_uses_relevance_over_whole_period_without_daily_quota(self):
        context = self.context("interior")
        older = [self.row(f"old{i}", day="2026-09-18", score=95) for i in range(10)]
        newer = [self.row(f"new{i}", day="2026-09-20", score=65) for i in range(10)]
        selected = self.select(context, newer + older, dates=("2026-09-18", "2026-09-19", "2026-09-20"))
        self.assertEqual(len(selected), 10)
        self.assertEqual(set(selected["日付"]), {"2026-09-18"})

    def test_exterior_global_representative_prefers_newer_day(self):
        context = self.context("exterior")
        older = self.kicks("older", country="米国", day="2026-09-19", score=99)
        newer = self.kicks("newer", country="欧州", score=70)
        selected = self.select(context, [older, newer])
        self.assertEqual(selected["URL"].tolist(), [newer["URL"]])
        self.assertEqual(json.loads(selected.iloc[0]["関連URL"]), [older["URL"]])

    def test_retry_preserves_reviewed_representative_and_does_not_revive_alias(self):
        for edition in ("interior", "exterior"):
            with self.subTest(edition=edition):
                context = self.context(edition)
                row = self.kicks("representative")
                representative = {"id": "jp1", "country": "jp", "date": "2026-09-20", "url": row["URL"],
                                  "title": "校正済みの日産キックス英国生産計画", "desc": row["内容"],
                                  "img": row["画像URL"], "exteriorScore": 80, "interiorScore": 80}
                alias = dict(representative, id="jp2", url="https://example.com/alias", duplicateOf="jp1")
                alias_row = self.kicks("alias", score=100)
                retry_row = dict(row, URL=row["URL"] + "?source=rss")
                selected = self.select(context, [row, retry_row, alias_row], [representative, alias])
                self.assertEqual(selected["URL"].tolist(), [representative["url"]])
                self.assertEqual(selected.iloc[0]["タイトル（日本語）"], representative["title"])
                self.assertIn(alias["url"], json.loads(selected.iloc[0]["関連URL"]))
                self.assertEqual(collector.SHEET2_RESULT["selected_count"], 1)
                if edition == "exterior":
                    self.assertEqual(collector.SHEET2_RESULT["selection_outcomes"]["selected"], 1)

    def test_recent_published_story_with_different_url_is_not_repeated(self):
        context = self.context("interior")
        row = self.kicks("new")
        history = [{"id": "jp1", "country": "jp", "date": "2026-09-19", "url": "https://old.example/kicks",
                    "title": row["タイトル"], "desc": row["内容"]}]
        selected = self.select(context, [row], history)
        self.assertTrue(selected.empty)
        self.assertEqual(collector.SHEET2_RESULT["selected_count"], 0)
        self.assertEqual(collector.SHEET2_RESULT["duplicate_decisions"][0]["kind"], "history")
        receipt = json.loads((context.runtime_dir / "summary_quarantine.json").read_text(encoding="utf-8"))
        self.assertEqual(receipt["selected_count"], 0)

    def test_urls_that_converged_during_resolution_are_deduplicated(self):
        context = self.context("interior")
        first, second = self.row("one"), self.row("two", country="米国")
        second["URL"] = first["URL"] + "?utm_campaign=second-search"
        selected = self.select(context, [first, second])
        self.assertEqual(selected["URL"].tolist(), [first["URL"]])
        self.assertEqual(collector.SHEET2_RESULT["duplicate_count"], 1)


if __name__ == "__main__":
    unittest.main()
