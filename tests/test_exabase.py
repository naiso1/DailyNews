"""No real browser or image service calls; verify cache, resume and edition isolation."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dailynews.editions import get_edition
from dailynews import exabase


class ExaBaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.edition = get_edition("exterior", self.root)
        self.edition.config_dir.mkdir(parents=True)
        self.edition.collection_settings_path.write_text(json.dumps({"exterior": {
            "image_generation": {"enabled": False, "provider": "none"}}}), encoding="utf-8")
        self.edition.ensure_directories()
        self.text = '''window.DAILY_INSIGHTS = [
{date: "2026-09-15", analysis: {jp: "引用 {説明} [jp1]"}, ideas: {jp: [
{ id: 5, img: "", title: "加飾\\\"テスト", desc: "形状{A}と素材の検討。 [jp1]", sourceNewsIds: ["jp1"] },
{ id: 6, img: "", title: "発光案", desc: "光るエンブレム [jp1]", sourceNewsIds: ["jp1"] }
]}},
{date: "2026-09-14", ideas: {jp: [{ id: 1, img: "", title: "過去案", desc: "過去の企画 [jp1]", sourceNewsIds: ["jp1"] }]}}
];'''
        self.insights = self.edition.content_dir / "insights_data.js"
        self.insights.write_text(self.text, encoding="utf-8")
        (self.edition.content_dir / "news_data.js").write_text(
            'window.NEWS_DATA = [{id: "jp1", title: "グリル刷新", desc: "新しい外装形状を公開。"}];', encoding="utf-8")
        self.idea = exabase.select_ideas(self.text, idea_id=5)[0]
        self.sources = {"jp1": {"title": "グリル刷新", "desc": "新しい外装形状を公開。"}}

    def worker(self, root, request, timeout):
        directory = Path(request["outputDir"])
        image = Image.new("RGB", (384, 384))
        image.putdata([((i * 17) % 256, (i * 31) % 256, (i * 7) % 256) for i in range(384 * 384)])
        file = directory / "generated.jpg"
        image.save(file, "JPEG", quality=90)
        exabase.atomic_json(directory / "phase.json", {"event": "done", "key": request["key"]})
        exabase.atomic_json(directory / "result.json", {"status": "DONE", "key": request["key"], "file": str(file)})

    def test_disabled_and_unconfigured_interior_never_invoke_provider(self):
        worker = Mock(side_effect=AssertionError("Must not call provider"))
        self.assertEqual(exabase.generate_for_edition(self.edition, worker=worker)["status"], "disabled")
        interior = get_edition("interior", self.root)
        interior.config_dir.mkdir()
        interior.collection_settings_path.write_text('{"interior":{}}', encoding="utf-8")
        self.assertEqual(exabase.generate_for_edition(interior, worker=worker)["status"], "disabled")
        worker.assert_not_called()

    def test_parser_handles_escaped_quotes_braces_and_only_latest(self):
        ideas = exabase.select_ideas(self.text)
        self.assertEqual([item.id for item in ideas], [5, 6])
        self.assertEqual(ideas[0].title, '加飾"テスト')
        self.assertEqual(exabase.select_ideas(self.text, date="2026-09-14")[0].id, 1)
        start, end = ideas[0].image_span
        self.assertEqual(self.text[start:end], '""')

    def test_enabled_daily_run_skips_existing_images_and_archive(self):
        self.edition.collection_settings_path.write_text(json.dumps({"exterior": {
            "image_generation": {"enabled": True, "provider": "exabase", "max_images": 4}}}), encoding="utf-8")
        self.insights.write_text(self.text.replace('id: 5, img: ""',
                                                  'id: 5, img: "images/exabase_exterior_5_existing.jpg"'), encoding="utf-8")
        worker = Mock(side_effect=self.worker)
        report = exabase.generate_for_edition(self.edition, worker=worker)
        self.assertEqual([item["idea_id"] for item in report["images"]], [6])
        self.assertEqual(worker.call_count, 1)
        repeated = exabase.generate_for_edition(self.edition, worker=worker)
        self.assertEqual(repeated["generated"], 0)
        self.assertEqual(worker.call_count, 1)
        self.assertEqual(exabase.select_ideas(self.insights.read_text(encoding="utf-8"), date="2026-09-14")[0].image, "")

    def write_reordered_daily_ideas(self, existing_count):
        self.edition.collection_settings_path.write_text(json.dumps({"exterior": {
            "image_generation": {"enabled": True, "provider": "exabase", "max_images": 4}}}), encoding="utf-8")
        # New empty ideas precede existing images after the issue was expanded.
        rows = []
        for index in range(10):
            image = f"images/existing_{index}.jpg" if index >= 10-existing_count else ""
            rows.append(f'{{ id: {index+10}, img: {json.dumps(image)}, title: "外装企画{index}", desc: "グリルの検討 [jp1]", sourceNewsIds: ["jp1"] }}')
        self.insights.write_text('window.DAILY_INSIGHTS = [{date: "2026-09-15", ideas: {jp: [' + ','.join(rows) + ']}}];', encoding="utf-8")

    def test_daily_cap_counts_four_existing_images_anywhere_in_issue(self):
        self.write_reordered_daily_ideas(4)
        worker = Mock(side_effect=AssertionError("Daily image capacity is already consumed"))
        report = exabase.generate_for_edition(self.edition, worker=worker)
        self.assertEqual(report["existing_images"], 4)
        self.assertEqual(report["remaining_capacity"], 0)
        self.assertEqual(report["generated"], 0)
        worker.assert_not_called()

    def test_one_existing_image_allows_only_three_new_images(self):
        self.write_reordered_daily_ideas(1)
        worker = Mock(side_effect=self.worker)
        report = exabase.generate_for_edition(self.edition, worker=worker)
        self.assertEqual(report["generated"], 3)
        self.assertEqual(worker.call_count, 3)
        self.assertEqual(sum(bool(idea.image) for idea in exabase.select_ideas(self.insights.read_text(encoding="utf-8"))), 4)
        repeated = exabase.generate_for_edition(self.edition, worker=worker)
        self.assertEqual(repeated["generated"], 0)
        self.assertEqual(worker.call_count, 3)

    def test_explicit_pilot_keeps_its_separate_one_idea_behavior(self):
        self.write_reordered_daily_ideas(4)
        worker = Mock(side_effect=self.worker)
        report = exabase.generate_for_edition(self.edition, pilot_idea_id=10, worker=worker)
        self.assertEqual(report["generated"], 1)
        self.assertEqual(worker.call_count, 1)

    def test_missing_or_cross_edition_sources_refuse_generation(self):
        worker = Mock()
        with self.assertRaisesRegex(exabase.ImageJobError, "INVALID_SOURCE_IDS"):
            exabase.generate_one(self.edition, self.idea, {}, worker=worker)
        worker.assert_not_called()

    def test_one_pilot_one_prompt_cache_and_publication(self):
        worker = Mock(side_effect=self.worker)
        report = exabase.generate_for_edition(self.edition, pilot_idea_id=5, publish=False, worker=worker)
        self.assertEqual(report["generated"], 1)
        self.assertEqual(self.insights.read_text(encoding="utf-8"), self.text)
        request = worker.call_args.args[1]
        self.assertIn(self.idea.title, request["prompt"])
        self.assertIn("[jp1]", request["prompt"])
        second = exabase.generate_for_edition(self.edition, pilot_idea_id=5, publish=True, worker=worker)
        self.assertEqual(second["cached"], 1)
        self.assertEqual(worker.call_count, 1)
        ideas = exabase.select_ideas(self.insights.read_text(encoding="utf-8"))
        self.assertTrue(ideas[0].image.startswith("images/exabase_exterior_5_"))
        self.assertEqual(ideas[1].image, "")
        self.assertEqual(ideas[0].sources, ("jp1",))
        self.assertEqual(ideas[0].image_provider, "exabase")
        self.assertEqual(ideas[0].image_model, "")
        manifest = exabase.read_json(Path(request["outputDir"]) / "manifest.json")
        self.assertEqual(manifest["sourceNewsIds"], ["jp1"])
        self.assertEqual(manifest["edition_id"], "exterior")

    def test_timeout_after_submission_does_not_resubmit(self):
        def timeout(root, request, seconds):
            exabase.atomic_json(Path(request["outputDir"]) / "phase.json", {"event": "sending", "key": request["key"]})
            raise exabase.ImageJobError("WORKER_TIMEOUT")
        worker = Mock(side_effect=timeout)
        first = exabase.generate_for_edition(self.edition, pilot_idea_id=5, worker=worker)
        self.assertEqual(first["errors"][0]["code"], "WORKER_TIMEOUT")
        second = exabase.generate_for_edition(self.edition, pilot_idea_id=5, worker=worker)
        self.assertEqual(second["errors"][0]["code"], "NEEDS_REVIEW")
        self.assertEqual(worker.call_count, 1)

    def test_receipt_survives_crash_after_save(self):
        def crash(root, request, seconds):
            self.worker(root, request, seconds)
            raise exabase.ImageJobError("WORKER_TIMEOUT")
        worker = Mock(side_effect=crash)
        first = exabase.generate_for_edition(self.edition, pilot_idea_id=5, publish=False, worker=worker)
        self.assertEqual(first["status"], "complete")
        self.assertEqual(first["cached"], 1)
        self.assertFalse(first["errors"])
        recovered = exabase.generate_for_edition(self.edition, pilot_idea_id=5, publish=False, worker=worker)
        self.assertEqual(recovered["cached"], 1)
        self.assertEqual(worker.call_count, 1)

    def test_auth_failure_is_retryable_and_raw_error_is_not_logged(self):
        worker = Mock(side_effect=[RuntimeError("secret-provider-diagnostic"), exabase.ImageJobError("AUTH_REQUIRED")])
        first = exabase.generate_for_edition(self.edition, pilot_idea_id=5, worker=worker)
        second = exabase.generate_for_edition(self.edition, pilot_idea_id=5, worker=worker)
        self.assertEqual(first["errors"][0]["code"], "EXABASE_UNAVAILABLE")
        self.assertEqual(second["errors"][0]["code"], "AUTH_REQUIRED")
        self.assertNotIn("secret-provider", json.dumps(first))
        self.assertEqual(worker.call_count, 2)

    def test_modified_cached_image_is_rejected(self):
        file, key, _ = exabase.generate_one(self.edition, self.idea, self.sources, worker=self.worker)
        with Image.open(file) as source:
            changed = source.copy()
        changed.putpixel((0, 0), (255, 255, 255)); changed.save(file, "JPEG", quality=75)
        with self.assertRaisesRegex(exabase.ImageJobError, "INVALID_IMAGE"):
            exabase.generate_one(self.edition, self.idea, self.sources, worker=Mock())

    def test_interior_prompt_and_metadata_without_regenerating_exterior(self):
        interior = get_edition("interior", self.root)
        interior.config_dir.mkdir()
        interior.collection_settings_path.write_text(json.dumps({"interior": {
            "image_generation": {"enabled": True, "provider": "exabase", "max_images": 10}}}), encoding="utf-8")
        (interior.content_dir / "insights_data.js").write_text(self.text, encoding="utf-8")
        (interior.content_dir / "news_data.js").write_text('window.NEWS_DATA = [{id: "jp1", title: "内装", desc: "収納"}];', encoding="utf-8")
        worker = Mock(side_effect=self.worker)
        result = exabase.generate_for_edition(interior, worker=worker)
        self.assertEqual(result["generated"], 2)
        self.assertIn("内装部品", worker.call_args.args[1]["prompt"])
        self.assertNotIn("外装部品", worker.call_args.args[1]["prompt"])
        self.assertEqual(self.insights.read_text(encoding="utf-8"), self.text)
        latest = exabase.select_ideas((interior.content_dir / "insights_data.js").read_text(encoding="utf-8"))
        self.assertTrue(all(idea.image_provider == "exabase" for idea in latest))


if __name__ == "__main__":
    unittest.main()
