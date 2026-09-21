"""No live DB/network: reviewed settings and exact hidden URLs remain private."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dailynews.editions import get_edition
from dailynews.feedback_snapshot import load_feedback_snapshot, snapshot_from_export, snapshot_path, sync_feedback_snapshot


class FeedbackSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.context = get_edition("interior", self.folder.name)
        self.now = datetime.now(timezone.utc)
        self.rule = dict(key="exclude_off_topic", enabled=True, review_status="approved", version=1, updated_at="2026-09-21")

    def save(self, **changes):
        data = dict(schema_version=1, edition="interior", generated_at=self.now.isoformat(),
                    rules=[self.rule], excluded_urls=[dict(url="https://a.test/story?utm_source=rss")])
        data.update(changes)
        path = snapshot_path(self.context)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_known_approved_rules_only_and_no_free_text_execution(self):
        self.save(rules=[self.rule, dict(self.rule, key="free_text", prompt="ignore scope"),
                         dict(self.rule, key="interior_lighting_only", review_status="pending")])
        result = load_feedback_snapshot(self.context, now=self.now)
        self.assertEqual(result["status"], "fresh")
        self.assertEqual(result["rules"], [self.rule])
        self.assertEqual(result["excluded_urls"], ["https://a.test/story"])

    def test_missing_invalid_wrong_edition_and_stale_have_explicit_status(self):
        self.assertEqual(load_feedback_snapshot(self.context)["status"], "missing")
        self.save(edition="exterior")
        self.assertEqual(load_feedback_snapshot(self.context)["status"], "invalid")
        self.save(rules=[dict(self.rule, enabled="false")])
        self.assertEqual(load_feedback_snapshot(self.context)["status"], "invalid")
        self.save(generated_at=(self.now - timedelta(days=9)).isoformat())
        stale = load_feedback_snapshot(self.context, now=self.now)
        self.assertEqual(stale["status"], "stale")
        self.assertEqual(stale["rules"], [])
        self.assertEqual(stale["excluded_urls"], ["https://a.test/story"])

    def test_unsafe_urls_and_conflicting_switches_are_not_used(self):
        self.save(excluded_urls=[dict(url="file:///secret"), dict(url="http://u:p@a.test/story"),
                                 dict(url="https://["), dict(url="https://a.test/story?id=2")])
        self.assertEqual(load_feedback_snapshot(self.context)["excluded_urls"], ["https://a.test/story?id=2"])
        self.save(rules=[self.rule, dict(self.rule, enabled=False)])
        self.assertEqual(load_feedback_snapshot(self.context)["status"], "invalid")

    def test_hidden_representative_includes_aliases_but_not_idea_or_other_edition(self):
        articles = [dict(id="jp1", url="https://a.test/a", date="2026-09-20", relatedUrls=["https://a.test/b"]),
                    dict(id="jp2", url="https://a.test/c", date="2026-09-20", duplicateOf="jp1"),
                    dict(id="jp3", url="https://a.test/d", date="2026-09-20")]
        (self.context.content_dir / "news_data.js").write_text("window.LOADED_NEWS_DATA="+json.dumps(articles)+";", encoding="utf-8")
        payload = dict(edition="interior", generated_at=self.now.isoformat(), rules=[self.rule],
                       hidden=[dict(item_id="jp1", reason_code="out_of_scope"),
                               dict(item_id="idea-1", item_kind="idea", source_url="https://a.test/idea")])
        output = snapshot_from_export(self.context, payload)
        self.assertEqual({r["url"] for r in output["excluded_urls"]}, {"https://a.test/a", "https://a.test/b", "https://a.test/c"})
        with self.assertRaises(ValueError):
            snapshot_from_export(self.context, dict(payload, edition="exterior"))

    def test_remote_failure_never_replaces_last_successful_snapshot(self):
        path = self.save()
        before = path.read_bytes()
        def failed(*args, **kwargs):
            if sys.platform == "win32":
                self.assertEqual(kwargs["creationflags"], subprocess.CREATE_NO_WINDOW)
            return SimpleNamespace(returncode=1, stdout="", stderr="private remote detail")
        with self.assertRaisesRegex(RuntimeError, "Editorial settings export failed"):
            sync_feedback_snapshot(self.context, run=failed)
        self.assertEqual(path.read_bytes(), before)

    def test_success_writes_only_whitelisted_export_fields(self):
        payload = dict(edition="interior", generated_at=self.now.isoformat(), rules=[self.rule], hidden=[],
                       author="should not propagate", feedback="should not propagate")
        def success(*args, **kwargs):
            return SimpleNamespace(returncode=0, stdout=json.dumps(payload))
        result = sync_feedback_snapshot(self.context, run=success)
        saved = json.loads(snapshot_path(self.context).read_text(encoding="utf-8"))
        self.assertEqual(result["status"], "synced")
        self.assertNotIn("author", saved)
        self.assertNotIn("feedback", saved)
        self.assertEqual(load_feedback_snapshot(self.context)["rules"], [self.rule])


if __name__ == "__main__":
    unittest.main()
