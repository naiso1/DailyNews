"""An issue can contain older source dates without recycling its archive."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dailynews.digest import validated_issue_context, selected_news_ids
from dailynews.editions import get_edition
import auto_update_daily_news as updater


class DigestPublicationTests(unittest.TestCase):
    def setUp(self):
        self.items = [dict(country="jp", date="2026-09-15", url="https://example.com/today", newsId="jp1"),
                      dict(country="cn", date="2026-09-09", url="https://example.com/older", newsId="cn2")]
        self.receipt = dict(edition_id="exterior", completed=True, target_dates=["2026-09-15"],
                            issue_date="2026-09-15", lookback_start="2026-09-09", selected_count=2,
                            source_dates=["2026-09-09", "2026-09-15"], source_count=1)

    def test_issue_retains_source_dates_and_ids(self):
        before = copy.deepcopy(self.items)
        context = validated_issue_context(self.receipt, self.items)
        self.assertEqual(context["supplemental_count"], 1)
        self.assertEqual(context["selected_by_country"], {"jp": 1, "cn": 1})
        self.assertEqual(selected_news_ids(self.items), ["jp1", "cn2"])
        self.assertEqual(before, self.items)

    def test_tampered_receipt_is_rejected(self):
        for field, value in [("completed", False), ("selected_count", 3), ("issue_date", "2026-09-14"),
                             ("lookback_start", "2026-09-08"), ("source_dates", ["2026-09-15"])]:
            with self.subTest(field=field):
                receipt = {**self.receipt, field: value}
                with self.assertRaises(ValueError):
                    validated_issue_context(receipt, self.items)

    def test_duplicate_urls_and_ids_rejected(self):
        self.items[1]["url"] = self.items[0]["url"]
        with self.assertRaises(ValueError):
            validated_issue_context(self.receipt, self.items)
        self.items[1]["newsId"] = self.items[0]["newsId"]
        with self.assertRaises(ValueError):
            selected_news_ids(self.items)

    def test_no_country_can_exceed_ten(self):
        items = [dict(country="jp", date="2026-09-15", url=f"https://example.com/{i}") for i in range(11)]
        receipt = {**self.receipt, "selected_count": 11, "source_dates": ["2026-09-15"]}
        with self.assertRaises(ValueError):
            validated_issue_context(receipt, items)

    def test_status_uses_issue_date_when_all_articles_are_older(self):
        items = [self.items[1]]
        receipt = {**self.receipt, "selected_count": 1, "source_dates": ["2026-09-09"]}
        with tempfile.TemporaryDirectory() as folder:
            edition = get_edition("exterior", folder)
            edition.runtime_dir.mkdir(parents=True)
            (edition.runtime_dir / "collection_result.json").write_text(json.dumps(receipt), encoding="utf-8")
            with patch.object(updater, "EDITION", edition), patch.dict(os.environ, TARGET_DATES="2026-09-15"):
                result = updater.write_exterior_publication_status(items, dry_run=True)
                self.assertEqual(result["processed_through"], "2026-09-15")
                self.assertEqual(result["selected_news_ids"], ["cn2"])
                self.assertEqual(result["supplemental_count"], 1)
                with patch.dict(os.environ, TARGET_DATES="2026-09-14"):
                    with self.assertRaises(RuntimeError):
                        updater.write_exterior_publication_status(items, dry_run=True)

    def test_legacy_receipt_remains_supported(self):
        self.assertIsNone(validated_issue_context({"target_dates": ["2026-09-15"]}, self.items))
        with self.assertRaises(ValueError):
            validated_issue_context({"edition_id": "exterior", "completed": False}, self.items)

    def test_existing_partial_insights_do_not_count_as_complete(self):
        text = '''window.DAILY_INSIGHTS = [{ date: "2026-09-15", analysis: { jp: "グリル[jp1]の検討を進める。" },
                  ideas: { jp: [
                    { id: 1, img: "", title: "加飾案", desc: "グリルの加飾案[jp1]", sourceNewsIds: ["jp1"] },
                    { id: 2, img: "", title: "素材案", desc: "グリルの素材案[jp1]", sourceNewsIds: ["jp1"] }
                  ] } }];'''
        self.assertTrue(updater.exterior_existing_insights_complete(text, "2026-09-15", self.items[:1]))
        self.assertFalse(updater.exterior_existing_insights_complete(text, "2026-09-15", self.items))
        self.assertFalse(updater.exterior_existing_insights_complete(text.replace('id: 2, img: ""', 'id: 2, missing: ""'), "2026-09-15", self.items[:1]))


if __name__ == "__main__":
    unittest.main()
