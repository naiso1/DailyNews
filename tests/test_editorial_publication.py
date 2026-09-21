import ast
import copy
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import auto_update_daily_news as publisher


class EditorialPublicationTests(unittest.TestCase):
    def setUp(self):
        self.good = dict(country="jp", url="https://example.test/material", llmDecision="対象",
                         title="ドアトリムに低VOC表皮材", desc="ドアトリムに低VOC表皮材を採用し、清掃性と触感を両立する。",
                         evidence=dict(target_component="ドアトリム表皮材", new_information="低VOC表皮材で清掃性と触感を両立",
                                       development_reference="ドアトリムの触感と清掃性を両立する材料選定の比較候補にする。",
                                       source_quote="ドアトリムに低VOC表皮材を採用"))
        self.snapshot = dict(rules=[], excluded_urls=[])

    def validate(self, items, existing=(), edition="interior"):
        return publisher.validate_editorial_publication(items, set(existing), self.snapshot, edition)

    def test_grounded_material_stores_flat_rationale(self):
        item = self.validate([self.good])[0]
        self.assertEqual(item["selectionTargetComponent"], "ドアトリム表皮材")
        self.assertIn("selectionPolicyVersion", item)

    def test_new_rejected_or_unsubstantiated_rows_abort_before_publication(self):
        for changes in (dict(llmDecision="非対象"), dict(evidence={}),
                        dict(title="10のバイクアップグレード", desc="motorcycle seats")):
            with self.subTest(changes=changes), self.assertRaises(RuntimeError):
                self.validate([{**self.good, **changes}])

    def test_legacy_existing_article_does_not_require_new_csv_fields(self):
        legacy = dict(url=self.good["url"], country="jp", title="旧記事")
        self.assertEqual(self.validate([legacy], [legacy["url"]]), [legacy])
        self.assertEqual(self.validate([dict(legacy, country="paper")]), [dict(legacy, country="paper")])

    def test_hidden_source_overrides_existing_without_hiding_unhidden_representative(self):
        self.snapshot["excluded_urls"] = [self.good["url"]]
        self.assertEqual(self.validate([self.good], [self.good["url"]]), [])
        alias = dict(self.good, url="https://example.test/alias", relatedUrls=[self.good["url"]])
        self.assertEqual(self.validate([alias], [alias["url"]]), [alias])
        self.snapshot["excluded_urls"].append(alias["url"])
        self.assertEqual(self.validate([alias]), [])

    def test_exterior_keeps_its_own_policy(self):
        item = dict(country="eu", url="https://example.test/grille", title="発光グリル")
        self.assertEqual(self.validate([item], edition="exterior"), [item])

    def test_exterior_common_scope_switch_only_applies_after_approval(self):
        item = dict(country="in", url="https://example.test/motorcycle", title="Royal Enfield バイク用品")
        self.assertEqual(self.validate([item], edition="exterior"), [item])
        self.snapshot["rules"] = [dict(key="exclude_non_passenger_vehicles", enabled=True, review_status="approved", version=1)]
        with self.assertRaises(RuntimeError):
            self.validate([item], edition="exterior")

    def test_illumination_tag_requires_cabin_context(self):
        with patch.object(publisher, "EDITION", publisher.get_edition("interior")):
            self.assertNotIn("イルミ", publisher.generate_tags("発光グリルと外装照明、ヘッドライト"))
            self.assertIn("イルミ", publisher.generate_tags("車内のアンビエント照明とドアトリム"))

    def test_runner_build_only_uses_cache_and_failure_preserves_cache(self):
        source = Path(__file__).parents[1] / "ニュース収集/run_search_and_update.py"
        tree = ast.parse(source.read_text(encoding="utf-8-sig"))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "refresh_editorial_settings")
        namespace = {"log": Mock()}
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), "exec"), namespace)
        refresh = namespace["refresh_editorial_settings"]
        with patch("dailynews.feedback_snapshot.sync_feedback_snapshot", side_effect=OSError("offline")) as sync, \
                patch("dailynews.feedback_snapshot.load_feedback_snapshot", return_value={"status": "fresh"}) as load:
            refresh(publisher.get_edition("interior"), offline=True)
            sync.assert_not_called()
            self.assertEqual(refresh(publisher.get_edition("interior")), {"status": "fresh"})
            self.assertEqual(sync.call_count, 1)
            self.assertEqual(load.call_count, 2)


if __name__ == "__main__":
    unittest.main()
