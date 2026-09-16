"""Provider selection and provenance checks, entirely offline with test images."""
import io
import base64
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dailynews import exabase, idea_images
from dailynews.editions import get_edition


class ImageProviderTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.edition = get_edition("interior", self.root)
        self.edition.config_dir.mkdir()
        self.config = {"enabled": True, "provider": "exabase", "fallback_provider": "gemini",
                       "max_images": 10, "start_after_date": "2026-09-15"}
        self.write_config()
        self.text = '''window.DAILY_INSIGHTS = [
{date: "2026-09-16", analysis: {jp: "内装 [jp1]"}, ideas: {jp: [
{id: 5, img: "", title: "トレイ", desc: "収納 [jp1]", imagePrompt: "cabin tray", sourceNewsIds: ["jp1"]},
{id: 6, img: "images/idea_dummy.svg", title: "発光パネル", desc: "照明 [jp1]", sourceNewsIds: ["jp1"]}
]}},
{date: "2026-09-15", ideas: {jp: [{id: 1, img: "", title: "過去", desc: "過去 [jp1]", sourceNewsIds: ["jp1"]}]}}
];'''
        self.path = self.edition.content_dir / "insights_data.js"
        self.path.write_text(self.text, encoding="utf-8")
        (self.edition.content_dir / "news_data.js").write_text(
            'window.NEWS_DATA = [{id: "jp1", title: "収納", desc: "新型トレイ"}];', encoding="utf-8")
        image = Image.new("RGB", (384, 384))
        image.putdata([((i * 17) % 256, (i * 31) % 256, (i * 7) % 256) for i in range(384 * 384)])
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=90)
        self.bytes = buffer.getvalue()

    def write_config(self):
        self.edition.collection_settings_path.write_text(
            json.dumps({self.edition.id: {"image_generation": self.config}}), encoding="utf-8")

    def publish_primary(self, edition, *, date):
        text = self.path.read_text(encoding="utf-8")
        idea = exabase.select_ideas(text, date=date)[0]
        test_image = self.root / "test.jpg"
        test_image.write_bytes(self.bytes)
        location = exabase.publish_image(edition, text, idea, test_image, "primary-key")
        return {"status": "partial", "generated": 1, "images": [{"idea_id": idea.id, "image": location}],
                "errors": [{"idea_id": 6, "code": "AUTH_REQUIRED"}]}

    def test_partial_primary_only_calls_api_for_missing_current_idea(self):
        api = Mock(return_value=self.bytes)
        with patch.dict(os.environ, {"GEMINI_IMAGE_MODEL": "test-existing-model"}):
            report = idea_images.optional_images(self.edition, issue_date="2026-09-16",
                                                 exabase_runner=self.publish_primary, api_generator=api)
        self.assertEqual(report["status"], "complete")
        self.assertEqual(report["providers"], {"exabase": 1, "api": 1})
        self.assertEqual(report["generated"], 2)
        api.assert_called_once()
        self.assertEqual(api.call_args.args[1].id, 6)
        self.assertEqual(api.call_args.args[2], "test-existing-model")
        ideas = exabase.select_ideas(self.path.read_text(encoding="utf-8"))
        self.assertEqual(ideas[0].image_provider, "exabase")
        self.assertEqual(ideas[1].image_provider, "api")
        self.assertEqual(ideas[1].image_model, "test-existing-model")
        self.assertEqual(ideas[0].image_prompt, "cabin tray")
        self.assertEqual(exabase.select_ideas(self.path.read_text(encoding="utf-8"), date="2026-09-15")[0].image, "")
        self.assertTrue((self.edition.runtime_dir / "image-generation-last-result.json").is_file())
        repeated = idea_images.optional_images(self.edition, exabase_runner=Mock(return_value={}), api_generator=api)
        self.assertEqual(repeated["generated"], 0)
        api.assert_called_once()

    def test_auth_failure_uses_api_and_raw_provider_error_is_not_reported(self):
        primary = Mock(side_effect=RuntimeError("secret-response-value"))
        api = Mock(return_value=self.bytes)
        report = idea_images.optional_images(self.edition, exabase_runner=primary, api_generator=api)
        self.assertEqual(report["status"], "complete")
        self.assertEqual(report["providers"], {"api": 2})
        self.assertEqual(api.call_count, 2)
        self.assertNotIn("secret-response-value", json.dumps(report))

    def test_exterior_never_calls_api_even_with_fallback_setting(self):
        exterior = get_edition("exterior", self.root)
        exterior.config_dir.mkdir(parents=True)
        exterior.collection_settings_path.write_text(json.dumps({"exterior": {"image_generation": self.config}}), encoding="utf-8")
        exterior.ensure_directories()
        (exterior.content_dir / "insights_data.js").write_text(self.text, encoding="utf-8")
        api = Mock(side_effect=AssertionError("Paid API prohibited for exterior"))
        report = idea_images.optional_images(exterior, exabase_runner=Mock(return_value={"status": "unavailable"}), api_generator=api)
        api.assert_not_called()
        self.assertEqual(report["status"], "unavailable")

    def test_previous_issue_and_wrong_target_never_generate(self):
        primary, api = Mock(), Mock()
        wrong = idea_images.optional_images(self.edition, issue_date="2026-09-17", exabase_runner=primary, api_generator=api)
        self.assertEqual(wrong["status"], "no_current_ideas")
        self.path.write_text(self.text.replace("2026-09-16", "2026-09-15"), encoding="utf-8")
        old = idea_images.optional_images(self.edition, exabase_runner=primary, api_generator=api)
        self.assertEqual(old["status"], "before_start_date")
        primary.assert_not_called()
        api.assert_not_called()

    def test_uncertain_api_failure_is_not_automatically_retried(self):
        api = Mock(side_effect=TimeoutError("secret-api-response"))
        primary = Mock(return_value={"status": "unavailable"})
        first = idea_images.optional_images(self.edition, exabase_runner=primary, api_generator=api)
        second = idea_images.optional_images(self.edition, exabase_runner=primary, api_generator=api)
        self.assertEqual(api.call_count, 2)
        self.assertTrue(all(error["code"] == "API_NEEDS_REVIEW" for error in second["errors"]))
        self.assertNotIn("secret-api-response", json.dumps(first))
        self.assertEqual(self.path.read_text(encoding="utf-8"), self.text)

    def test_budget_counts_existing_images_before_fallback(self):
        self.config["max_images"] = 1
        self.write_config()
        api = Mock(side_effect=AssertionError("Budget exhausted"))
        report = idea_images.optional_images(self.edition, exabase_runner=self.publish_primary, api_generator=api)
        self.assertEqual(report["providers"], {"exabase": 1})
        self.assertEqual(report["missing"], [6])
        api.assert_not_called()

    def test_api_uses_existing_settings_and_source_reference_functions(self):
        import generate_idea_images_gemini as gemini
        idea = exabase.select_ideas(self.text)[0]
        response = Mock(status_code=200)
        response.json.return_value = {"candidates": [{"content": {"parts": [
            {"inlineData": {"data": base64.b64encode(self.bytes).decode()}}
        ]}}]}
        settings = {"GEMINI_API_KEY": "unit-test-key", "GEMINI_IMAGE_SIZE": "1K",
                    "GEMINI_IMAGE_ASPECT_RATIO": "16:9", "GEMINI_API_VERSION": "v1beta"}
        with patch.dict(os.environ, settings), patch.object(gemini, "configure_external_proxy") as proxy, \
                patch.object(gemini, "build_reference_parts", return_value=[]) as references, \
                patch.object(gemini.requests, "post", return_value=response) as post:
            raw = idea_images.generate_api_bytes(self.edition, idea, "configured-model")
        self.assertEqual(raw, self.bytes)
        proxy.assert_called_once()
        self.assertEqual(references.call_args.args[0]["sourceNewsIds"], ("jp1",))
        self.assertIn("configured-model:generateContent", post.call_args.args[0])
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["generationConfig"]["imageConfig"], {"aspectRatio": "16:9", "imageSize": "1K"})
        self.assertIn("cabin tray", payload["contents"][0]["parts"][0]["text"])

    def test_api_saved_before_publication_can_resume_without_second_request(self):
        idea = exabase.select_ideas(self.text)[0]
        api = Mock(return_value=self.bytes)
        first, first_key, cached = idea_images.api_image(self.edition, idea, "test-model", api)
        second, second_key, cached_again = idea_images.api_image(self.edition, idea, "test-model", api)
        self.assertEqual((first, first_key), (second, second_key))
        self.assertFalse(cached)
        self.assertTrue(cached_again)
        api.assert_called_once()

    def test_changed_visual_brief_does_not_attach_an_old_image(self):
        def changed(edition, idea, model):
            self.path.write_text(self.path.read_text(encoding="utf-8").replace("cabin tray", "changed brief"), encoding="utf-8")
            return self.bytes
        self.config["max_images"] = 1
        self.write_config()
        report = idea_images.optional_images(self.edition, exabase_runner=Mock(return_value={}), api_generator=changed)
        self.assertEqual(report["errors"][0]["code"], "CONTENT_CHANGED")
        self.assertEqual(exabase.select_ideas(self.path.read_text(encoding="utf-8"))[0].image, "")

    def test_primary_busy_defers_paid_fallback(self):
        for primary in (Mock(side_effect=exabase.ImageJobError("BUSY")),
                        Mock(return_value={"status": "unavailable", "errors": [{"idea_id": 5, "code": "BUSY"}]})):
            api = Mock(side_effect=AssertionError("Must not race an active browser generation"))
            report = idea_images.optional_images(self.edition, exabase_runner=primary, api_generator=api)
            self.assertEqual(report["fallback_deferred"], "BUSY")
            api.assert_not_called()

    def test_saved_primary_result_prevents_api_after_worker_crash(self):
        def crash(root, request, seconds):
            directory = Path(request["outputDir"])
            image = directory / "generated.jpg"
            image.write_bytes(self.bytes)
            exabase.atomic_json(directory / "phase.json", {"event": "done", "key": request["key"]})
            exabase.atomic_json(directory / "result.json", {"status": "DONE", "key": request["key"], "file": str(image)})
            raise exabase.ImageJobError("WORKER_TIMEOUT")
        def primary(edition, *, date):
            return exabase.generate_for_edition(edition, date=date, worker=crash)
        api = Mock(side_effect=AssertionError("Existing exaBase result must be recovered first"))
        report = idea_images.optional_images(self.edition, exabase_runner=primary, api_generator=api)
        self.assertEqual(report["status"], "complete")
        self.assertEqual(report["providers"], {"exabase": 2})
        self.assertEqual(report["cached"], 2)
        api.assert_not_called()

    def test_api_server_error_is_uncertain_but_explicit_rejection_can_retry(self):
        import generate_idea_images_gemini as gemini
        idea = exabase.select_ideas(self.text)[0]
        for status, expected_code, expected_calls in ((503, "API_NEEDS_REVIEW", 1),
                                                      (408, "API_NEEDS_REVIEW", 1),
                                                      (429, "API_HTTP_REJECTED", 2)):
            response = Mock(status_code=status)
            with patch.dict(os.environ, {"GEMINI_API_KEY": "unit-test-key"}), \
                    patch.object(gemini, "configure_external_proxy"), \
                    patch.object(gemini, "build_reference_parts", return_value=[]), \
                    patch.object(gemini.requests, "post", return_value=response) as post:
                with self.assertRaises(exabase.ImageJobError):
                    idea_images.api_image(self.edition, idea, f"test-{status}", idea_images.generate_api_bytes)
                with self.assertRaisesRegex(exabase.ImageJobError, expected_code):
                    idea_images.api_image(self.edition, idea, f"test-{status}", idea_images.generate_api_bytes)
                self.assertEqual(post.call_count, expected_calls)

    def test_api_fallback_excludes_manual_exabase_generation(self):
        worker = Mock(side_effect=AssertionError("A parallel exaBase job must not start"))
        def api(edition, idea, model):
            with self.assertRaisesRegex(exabase.ImageJobError, "BUSY"):
                exabase.generate_for_edition(edition, pilot_idea_id=idea.id, worker=worker)
            return self.bytes
        report = idea_images.optional_images(self.edition, exabase_runner=Mock(return_value={}), api_generator=api)
        self.assertEqual(report["status"], "complete")
        worker.assert_not_called()

    def test_manual_job_starting_between_providers_defers_api(self):
        lock = exabase.edition_lock(self.edition.runtime_dir / "exabase.lock")
        def primary(edition, *, date):
            lock.__enter__()
            return {"status": "unavailable"}
        api = Mock(side_effect=AssertionError("A manual job acquired the provider lock"))
        try:
            report = idea_images.optional_images(self.edition, exabase_runner=primary, api_generator=api)
        finally:
            lock.__exit__(None, None, None)
        self.assertEqual(report["fallback_deferred"], "BUSY")
        api.assert_not_called()

    def test_metadata_does_not_truncate_country_history(self):
        import auto_update_daily_news as updater
        original = updater.extract_recent_ideas_by_country(self.text, "jp")
        for country in ("jp", "us", "eu", "cn", "in"):
            text = self.text.replace('jp: [', country + ': [')
            for idea in exabase.select_ideas(text):
                current = exabase.select_ideas(text, idea_id=idea.id)[0]
                text = exabase.image_fields(text, current, imageProvider="api", imageModel="test-model")
            parsed = updater.extract_recent_ideas_by_country(text, country)
            self.assertEqual(parsed, original)
            self.assertEqual(len(parsed), 3)
            self.assertEqual(len(updater.extract_recent_ideas_by_country(text, country, limit=2)), 2)

    def test_standalone_api_parser_preserves_metadata_compatibility(self):
        import generate_idea_images_gemini as gemini
        text = gemini.update_image_path(self.text, 5, "images/api_fixture.jpg", provider="api", model="fixture-model")
        parsed = gemini.extract_ideas(gemini.extract_latest_block(text))
        self.assertEqual([idea["id"] for idea in parsed], [5, 6])
        self.assertEqual(parsed[0]["sourceNewsIds"], ["jp1"])
        self.assertEqual(parsed[0]["imagePrompt"], "cabin tray")
        current = exabase.select_ideas(text)[0]
        self.assertEqual((current.image_provider, current.image_model), ("api", "fixture-model"))
        cached_unknown = gemini.update_image_path(text, 5, "images/old_unverified.png")
        self.assertEqual(exabase.select_ideas(cached_unknown)[0].image_provider, "")


if __name__ == "__main__":
    unittest.main()
