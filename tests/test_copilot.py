"""Offline integration checks for priority, fallback, and no duplicate sends."""
import json
from dataclasses import replace
from pathlib import Path
import time
import unittest
from unittest.mock import Mock

import test_idea_images as fixtures
import test_exabase as exabase_fixtures
from dailynews import copilot, exabase, idea_images


class CopilotTests(unittest.TestCase):
    write_config = fixtures.ImageProviderTests.write_config

    def setUp(self):
        fixtures.ImageProviderTests.setUp(self)
        self.config.update(provider='copilot', fallback_provider='exabase', copilot_timeout_seconds=180, batch_seconds=1800)
        self.write_config()
        self.sources = exabase.source_articles((self.root / 'news_data.js').read_text(encoding='utf-8'))
        self.idea = exabase.select_ideas(self.text)[0]
        self.api = Mock(side_effect=AssertionError('Paid API must never run'))

    def worker(self, root, request, timeout):
        directory = Path(request['outputDir'])
        image = directory / 'image.jpg'
        image.write_bytes(self.bytes)
        exabase.atomic_json(directory / 'phase.json', {'event': 'done', 'key': request['key']})
        exabase.atomic_json(directory / 'result.json', {'status': 'DONE', 'key': request['key'], 'provider': 'copilot', 'file': str(image)})

    def primary(self, edition, **kwargs):
        return copilot.generate_for_edition(edition, worker=self.worker, **kwargs)

    def fallback(self, edition, **kwargs):
        return exabase.generate_for_edition(edition, worker=lambda *args: exabase_fixtures.ExaBaseTests.worker(self, *args), **kwargs)

    def test_success_preserves_archive_and_does_not_invoke_fallback(self):
        fallback = Mock(side_effect=AssertionError('No fallback needed'))
        report = idea_images.optional_images(self.edition, copilot_runner=self.primary, exabase_runner=fallback, api_generator=self.api)
        self.assertEqual(report['providers'], {'copilot': 2})
        self.assertEqual(report['status'], 'complete')
        fallback.assert_not_called()
        self.api.assert_not_called()
        ideas = exabase.select_ideas(self.path.read_text(encoding='utf-8'))
        self.assertTrue(all(i.image.startswith('images/copilot_interior_') and i.image_model == '' for i in ideas))
        self.assertEqual(exabase.select_ideas(self.path.read_text(encoding='utf-8'), date='2026-09-15')[0].image, '')
        again = idea_images.optional_images(self.edition, copilot_runner=self.primary, exabase_runner=fallback, api_generator=self.api)
        self.assertEqual(again['generated'], 0)

    def test_missing_copilot_auth_falls_back_to_exabase_only(self):
        primary = Mock(side_effect=exabase.ImageJobError('AUTH_REQUIRED'))
        report = idea_images.optional_images(self.edition, copilot_runner=primary, exabase_runner=self.fallback, api_generator=self.api)
        self.assertEqual(report['providers'], {'exabase': 2})
        self.assertEqual(report['status'], 'complete')
        self.api.assert_not_called()

    def test_unknown_sent_job_blocks_only_that_idea_and_survives_prompt_change(self):
        def uncertain(root, request, timeout):
            exabase.atomic_json(Path(request['outputDir']) / 'phase.json', {'event': 'sending', 'key': request['key']})
            raise exabase.ImageJobError('WORKER_TIMEOUT')
        worker = Mock(side_effect=uncertain)
        primary = lambda edition, **kwargs: copilot.generate_for_edition(edition, worker=worker, **kwargs)
        report = idea_images.optional_images(self.edition, copilot_runner=primary, exabase_runner=self.fallback, api_generator=self.api)
        self.assertEqual(report['missing'], [5])
        self.assertEqual(report['fallback_excluded_ideas'], [5])
        self.assertEqual(report['providers'], {'exabase': 1})
        self.path.write_text(self.path.read_text(encoding='utf-8').replace('cabin tray', 'different prompt'), encoding='utf-8')
        report = idea_images.optional_images(self.edition, copilot_runner=primary, exabase_runner=self.fallback, api_generator=self.api)
        worker.assert_called_once()
        self.assertEqual(report['missing'], [5])
        self.api.assert_not_called()

    def test_completed_download_recovers_after_process_error_without_resubmission(self):
        def crash(*args):
            self.worker(*args)
            raise exabase.ImageJobError('WORKER_TIMEOUT')
        worker = Mock(side_effect=crash)
        first = copilot.generate_one(self.edition, self.idea, self.sources, worker=worker)
        second = copilot.generate_one(self.edition, self.idea, self.sources, worker=worker)
        self.assertEqual(first[:2], second[:2])
        self.assertTrue(first[2] and second[2])
        worker.assert_called_once()

    def test_auth_before_send_is_retryable_and_private_diagnostics_do_not_escape(self):
        failing = Mock(side_effect=exabase.ImageJobError('AUTH_REQUIRED'))
        with self.assertRaisesRegex(exabase.ImageJobError, 'AUTH_REQUIRED'):
            copilot.generate_one(self.edition, self.idea, self.sources, worker=failing)
        self.assertFalse(copilot.unresolved(self.edition, self.idea))
        copilot.generate_one(self.edition, self.idea, self.sources, worker=self.worker)
        fallback = Mock()
        report = idea_images.optional_images(self.edition, copilot_runner=Mock(side_effect=RuntimeError('secret token')), exabase_runner=fallback, api_generator=self.api)
        self.assertEqual(report['fallback_deferred'], 'NEEDS_REVIEW')
        self.assertNotIn('secret token', json.dumps(report))
        fallback.assert_not_called()

    def test_busy_never_starts_a_second_provider(self):
        fallback = Mock()
        report = idea_images.optional_images(self.edition, copilot_runner=Mock(side_effect=exabase.ImageJobError('BUSY')), exabase_runner=fallback)
        self.assertEqual(report['fallback_deferred'], 'BUSY')
        fallback.assert_not_called()

    def test_copilot_mode_never_uses_paid_api_even_when_config_is_mistyped(self):
        self.config['fallback_provider'] = 'gemini'
        self.write_config()
        report = idea_images.optional_images(self.edition, copilot_runner=Mock(side_effect=exabase.ImageJobError('AUTH_REQUIRED')), api_generator=self.api)
        self.api.assert_not_called()
        self.assertEqual(report['missing'], [5, 6])

    def test_shared_deadline_and_manual_provider_lock(self):
        worker = Mock()
        report = copilot.generate_for_edition(self.edition, worker=worker, deadline=time.monotonic() - 1)
        worker.assert_not_called()
        self.assertEqual(report['errors'][0]['code'], 'BATCH_TIME_BUDGET')
        with exabase.edition_lock(self.edition.runtime_dir / 'exabase.lock'):
            with self.assertRaisesRegex(exabase.ImageJobError, 'BUSY'):
                copilot.generate_for_edition(self.edition, worker=worker)

    def test_edited_content_cannot_receive_the_old_image(self):
        def edit(*args):
            self.worker(*args)
            self.path.write_text(self.path.read_text(encoding='utf-8').replace('収納 [jp1]', '変更 [jp1]'), encoding='utf-8')
        report = copilot.generate_for_edition(self.edition, worker=edit)
        self.assertEqual(report['errors'][0]['code'], 'CONTENT_CHANGED')
        self.assertFalse(exabase.has_image(exabase.select_ideas(self.path.read_text(encoding='utf-8'))[0]))

    def test_prompt_keeps_design_change_and_rejects_missing_sources(self):
        idea = replace(self.idea, desc='三菱のロゴがある。開発案として、プレートを磁石で着脱する。[jp1]')
        prompt = copilot.image_prompt(idea, self.sources, 'interior')
        self.assertNotIn('三菱', prompt)
        self.assertIn('プレートを磁石で着脱', prompt)
        self.assertIn('無地', prompt)
        self.assertIn('1:1', prompt)
        with self.assertRaisesRegex(exabase.ImageJobError, 'INVALID_SOURCE_IDS'):
            copilot.image_prompt(idea, {}, 'interior')


if __name__ == '__main__':
    unittest.main()
