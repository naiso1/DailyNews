"""Offline recovery tests: no browser, API, Git writes or production deployment."""
import datetime as dt
import importlib.util
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dailynews import exabase
from dailynews.editions import get_edition

spec = importlib.util.spec_from_file_location('image_recovery', ROOT / 'deployment/workstation/image_recovery.py')
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)


class ImageRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.runtime = self.root / 'private'
        self.today = dt.date(2026, 11, 2)
        self.edition = get_edition('exterior', self.root)
        self.edition.config_dir.mkdir(parents=True)
        self.set_config()
        self.edition.ensure_directories()
        (self.edition.runtime_dir / 'logs').mkdir()
        self.status = self.edition.runtime_dir / 'logs/latest_run_status.json'
        self.status.write_text(json.dumps({'edition_id': 'exterior', 'status': 'success',
            'run_date': '2026-11-02', 'published_news_date': '2026-11-01'}))
        self.path = self.edition.content_dir / 'insights_data.js'
        self.original = '''window.DAILY_INSIGHTS = [
{date: "2026-11-01", ideas: {jp: [
{id: 1, img: "", title: "新しい構造", desc: "企画の説明 [jp1]", sourceNewsIds: ["jp1"]},
{id: 2, img: "images/existing.png", title: "掲載済み", desc: "維持 [jp1]", sourceNewsIds: ["jp1"]}
]}}, {date: "2026-10-31", ideas: {jp: [
{id: 3, img: "", title: "過去案", desc: "過去 [jp1]", sourceNewsIds: ["jp1"]}]}}];'''
        self.path.write_text(self.original, encoding='utf-8')
        (self.edition.content_dir / 'news_data.js').write_text('news fixture')
        self.remote = self.hashes()
        self.auth = Mock(return_value=('authenticated', ''))
        self.generate = Mock(side_effect=self.add_image)
        self.publish = Mock(side_effect=lambda edition, images: self.remote.update(self.hashes()))

    def set_config(self, **overrides):
        self.edition.collection_settings_path.write_text(json.dumps({'exterior': {'image_generation': {
            'enabled': True, 'provider': 'exabase', 'fallback_provider': 'none', **overrides}}}))

    def hashes(self):
        return {n: recovery.digest(self.edition.content_dir / n) for n in ('news_data.js', 'insights_data.js')}

    def state(self):
        return json.loads((self.runtime / 'image-recovery/exterior/state.json').read_text(encoding='utf-8'))

    def add_image(self, edition, issue_date):
        self.assertEqual(issue_date, '2026-11-01')
        source = self.root / 'test-image.png'
        # A decodable, sufficiently sized fixture, independent of any provider.
        image = Image.new('RGB', (384, 384))
        image.putdata([((i * 13) % 256, (i * 29) % 256, (i * 7) % 256) for i in range(384 * 384)])
        image.save(source)
        text = self.path.read_text(encoding='utf-8')
        exabase.publish_image(edition, text, exabase.select_ideas(text)[0], source, 'a' * 64, model='GPT-image')
        return {'generated': 1, 'errors': []}

    def run_recovery(self):
        return recovery.recover_latest_images(self.root, self.runtime, ['exterior'], today=self.today,
            auth=self.auth, generate=self.generate, publisher=self.publish,
            publication_reader=lambda name: dict(self.remote))

    def test_restored_auth_adds_only_missing_current_image_then_publishes_once(self):
        self.assertEqual(self.run_recovery(), {'exterior'})
        self.assertEqual(self.state()['status'], 'complete')
        self.assertEqual(self.run_recovery(), set())
        self.generate.assert_called_once()
        self.publish.assert_called_once()
        after = self.path.read_text(encoding='utf-8')
        self.assertEqual(exabase.select_ideas(after)[1].image, 'images/existing.png')
        self.assertEqual(exabase.select_ideas(after, date='2026-10-31')[0].image, '')
        self.assertEqual(self.remote, self.hashes())

    def test_auth_and_setup_wait_without_spending_generation_attempts(self):
        for code in ('AUTH_REQUIRED', 'SETUP_REQUIRED'):
            self.auth.return_value = ('action_required', code)
            self.run_recovery()
            self.assertEqual(self.state()['attempts'], 0)
            self.assertEqual(self.state()['code'], code)
        self.generate.assert_not_called()
        self.publish.assert_not_called()
        self.auth.return_value = ('authenticated', '')
        self.run_recovery()
        self.assertEqual(self.state()['status'], 'complete')

    def test_failed_publication_retries_without_auth_or_generation(self):
        self.publish.side_effect = RuntimeError('IMAGE_PUBLICATION_FAILED')
        self.assertEqual(self.run_recovery(), {'exterior'})
        self.assertEqual(self.state()['code'], 'IMAGE_PUBLICATION_FAILED')
        self.auth.side_effect = AssertionError('Publication must not require sign-in')
        self.publish.side_effect = lambda edition, images: self.remote.update(self.hashes())
        self.assertEqual(self.run_recovery(), {'exterior'})
        self.generate.assert_called_once()
        self.assertEqual(self.state()['status'], 'complete')

    def test_unrelated_unpublished_content_is_not_owned(self):
        self.remote['insights_data.js'] = '0' * 64
        self.assertEqual(self.run_recovery(), set())
        self.auth.assert_not_called()

    def test_prose_or_existing_image_changes_reject_publication(self):
        self.auth.return_value = ('action_required', 'AUTH_REQUIRED')
        self.run_recovery()
        self.path.write_text(self.original.replace('掲載済み', '変更された説明'), encoding='utf-8')
        self.assertEqual(self.run_recovery(), {'exterior'})
        self.publish.assert_not_called()
        self.assertEqual(self.state()['code'], 'CONTENT_CHANGED')

    def test_changed_news_during_a_repair_does_not_fall_through_to_full_collection(self):
        self.auth.return_value = ('action_required', 'AUTH_REQUIRED')
        self.run_recovery()
        (self.edition.content_dir / 'news_data.js').write_text('intervening editorial change')
        self.assertEqual(self.run_recovery(), {'exterior'})
        self.generate.assert_not_called()
        self.publish.assert_not_called()
        self.assertEqual(self.state()['code'], 'CONTENT_CHANGED')

    def test_two_generation_attempts_per_day_but_never_uncertain_retry(self):
        self.generate.side_effect = None
        self.generate.return_value = {'errors': [{'code': 'NEEDS_REVIEW'}]}
        for _ in range(4):
            self.run_recovery()
        self.assertEqual(self.generate.call_count, 2)
        self.assertEqual(self.state()['attempts'], 2)
        self.assertEqual(set(self.generate.call_args.kwargs), {'issue_date'})

    def test_expiry_during_generation_does_not_exhaust_recovery(self):
        self.generate.side_effect = None
        self.generate.return_value = {'errors': [{'code': 'AUTH_REQUIRED'}]}
        self.run_recovery()
        self.assertEqual(self.state()['attempts'], 0)

    def test_api_configuration_stale_issue_and_weekend_are_skipped(self):
        self.set_config(fallback_provider='gemini')
        self.assertEqual(self.run_recovery(), set())
        self.set_config()
        self.today = dt.date(2026, 11, 3)
        self.assertEqual(self.run_recovery(), set())
        self.today = dt.date(2026, 11, 1)
        self.assertEqual(self.run_recovery(), set())
        self.auth.assert_not_called()
        self.generate.assert_not_called()

    def test_publisher_refuses_other_staged_work(self):
        with patch.object(recovery, 'command', return_value='other-file.js') as command:
            with self.assertRaisesRegex(RuntimeError, 'OTHER_STAGED_CHANGES'):
                recovery.publish(self.edition, [])
        self.assertEqual(command.call_count, 1)

    def test_publication_timeout_reaps_only_its_command_tree(self):
        process = Mock(pid=987654, returncode=1)
        process.communicate.side_effect = [subprocess.TimeoutExpired('fixture', 10), ('', '')]
        process.poll.return_value = 1
        with patch.object(recovery.subprocess, 'Popen', return_value=process), \
             patch.object(recovery.subprocess, 'run', return_value=Mock(returncode=0)) as stop:
            with self.assertRaisesRegex(RuntimeError, 'IMAGE_PUBLICATION_FAILED'):
                recovery.command(self.root, ['fixture'], 10)
        if recovery.os.name == 'nt':
            self.assertEqual(stop.call_args.args[0], ['taskkill.exe', '/PID', '987654', '/T', '/F'])
        self.assertEqual(process.communicate.call_count, 2)

    def test_uncommitted_public_ui_is_not_published_with_image_repair(self):
        def result(root, args, *rest):
            return ' M release_history.js' if args[:2] == ['git', 'status'] else ''
        with patch.object(recovery, 'command', side_effect=result) as command:
            with self.assertRaisesRegex(RuntimeError, 'OTHER_PUBLIC_CHANGES'):
                recovery.publish(self.edition, [])
        self.assertFalse(any('push' in call.args[1] for call in command.call_args_list))


if __name__ == '__main__':
    unittest.main()
