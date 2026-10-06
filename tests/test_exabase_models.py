"""Model-specific provenance/cache checks without browser or paid API calls."""
import json
import unittest
from pathlib import Path
from unittest.mock import Mock
import test_exabase
from dailynews import exabase


class ExaBaseModelTests(unittest.TestCase):
    setUp = test_exabase.ExaBaseTests.setUp
    worker = test_exabase.ExaBaseTests.worker

    def configure_models(self, priority=None):
        config = {"enabled": True, "provider": "exabase", "max_images": 2,
                  "model_priority": priority or ["gpt-image", "nano-banana"]}
        self.edition.collection_settings_path.write_text(json.dumps({"exterior": {"image_generation": config}}), encoding="utf-8")

    def model_worker(self, root, request, timeout, selected="gpt-image"):
        self.worker(root, request, timeout)
        directory = Path(request["outputDir"])
        receipt = exabase.read_json(directory / "result.json")
        receipt.update(imageModel=exabase.IMAGE_MODELS[selected], modelSelection={
            "version": exabase.MODEL_SELECTOR_VERSION, "priority": request["imageModels"],
            "verified": True, "selected": selected,
            "states": {key: key == selected for key in exabase.IMAGE_MODELS}})
        exabase.atomic_json(directory / "result.json", receipt)

    def test_named_model_has_separate_cache_from_legacy_and_changed_priority(self):
        prompt = exabase.image_prompt(self.idea, self.sources, self.edition.id)
        keys = [exabase.job_key(self.edition.id, self.idea, prompt, image_models=priority)
                for priority in (None, ["gpt-image", "nano-banana"], ["nano-banana", "gpt-image"])]
        self.assertEqual(len(set(keys)), 3)

    def test_actual_selected_model_is_published_and_cached_without_new_request(self):
        for selected in exabase.IMAGE_MODELS:
            with self.subTest(selected=selected):
                self.configure_models([selected])
                self.insights.write_text(self.text, encoding="utf-8")
                worker = Mock(side_effect=lambda root, request, timeout: self.model_worker(root, request, timeout, selected))
                report = exabase.generate_for_edition(self.edition, pilot_idea_id=5, worker=worker)
                self.assertEqual(report["generated"], 1)
                self.assertEqual(worker.call_args.args[1]["imageModels"], [selected])
                self.assertEqual(report["images"][0]["imageModel"], exabase.IMAGE_MODELS[selected])
                published = exabase.select_ideas(self.insights.read_text(encoding="utf-8"), idea_id=5)[0]
                self.assertEqual(published.image_model, exabase.IMAGE_MODELS[selected])
                image, key, cached = exabase.generate_one(self.edition, self.idea, self.sources, worker=worker)
                self.assertTrue(cached)
                worker.assert_called_once()

    def test_missing_model_proof_cannot_publish_or_be_reused(self):
        self.configure_models()
        worker = Mock(side_effect=self.worker)
        for _ in range(2):
            report = exabase.generate_for_edition(self.edition, pilot_idea_id=5, worker=worker)
            self.assertEqual(report["errors"], [{"idea_id": 5, "code": "IMAGE_MODEL_MISMATCH"}])
            self.assertEqual(self.insights.read_text(encoding="utf-8"), self.text)
        worker.assert_called_once()

    def test_fallback_receipt_keeps_nano_name_even_if_final_worker_reply_is_lost(self):
        self.configure_models()
        def worker(root, request, timeout):
            self.model_worker(root, request, timeout, selected="nano-banana")
            raise exabase.ImageJobError("WORKER_TIMEOUT")
        report = exabase.generate_for_edition(self.edition, pilot_idea_id=5, worker=worker)
        self.assertEqual(report["cached"], 1)
        self.assertEqual(report["images"][0]["imageModel"], "Nano Banana")
        self.assertEqual(report["errors"], [])

    def test_two_active_models_reject_receipt(self):
        self.configure_models()
        def worker(root, request, timeout):
            self.model_worker(root, request, timeout)
            file = Path(request["outputDir"]) / "result.json"
            receipt = exabase.read_json(file)
            receipt["modelSelection"]["states"]["nano-banana"] = True
            exabase.atomic_json(file, receipt)
        report = exabase.generate_for_edition(self.edition, pilot_idea_id=5, worker=worker)
        self.assertEqual(report["errors"][0]["code"], "IMAGE_MODEL_MISMATCH")
        self.assertEqual(self.insights.read_text(encoding="utf-8"), self.text)

    def test_completed_old_images_are_kept_after_switching_models(self):
        exabase.generate_for_edition(self.edition, pilot_idea_id=5, worker=self.worker)
        before = self.insights.read_text(encoding="utf-8")
        self.configure_models()
        worker = Mock(side_effect=AssertionError("Existing image must stay"))
        report = exabase.generate_for_edition(self.edition, pilot_idea_id=5, worker=worker)
        self.assertEqual(report["generated"], 0)
        self.assertEqual(self.insights.read_text(encoding="utf-8"), before)
        worker.assert_not_called()

    def test_invalid_model_settings_fail_before_provider(self):
        for value in ([], "gpt-image", ["unknown"], ["gpt-image", "gpt-image"], [[]]):
            with self.subTest(value=value), self.assertRaisesRegex(exabase.ImageJobError, "INVALID_MODEL_CONFIG"):
                exabase.model_priority({"model_priority": value})
