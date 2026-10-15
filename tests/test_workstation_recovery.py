"""Recovery must skip current publications and bound retries without sending mail."""
import datetime as dt
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('recovery', ROOT/'deployment/workstation/recovery.py')
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)
TODAY = dt.date(2026,10,15)


class RecoveryTests(unittest.TestCase):
    def test_empty_windows_process_output_does_not_block_recovery(self):
        for output, expected in (('[null]', []), ('[]', []), ('[124,456]', [124,456])):
            with self.subTest(output=output), patch.object(
                    recovery.subprocess, 'run', return_value=Mock(stdout=output)):
                self.assertEqual(recovery.running_pipeline_pids(ROOT), expected)

    def test_malformed_process_output_cannot_start_duplicate_work(self):
        for output in ('null', '"124"', '["124"]', '[0]', '[true]'):
            with self.subTest(output=output), patch.object(
                    recovery.subprocess, 'run', return_value=Mock(stdout=output)):
                with self.assertRaises(ValueError):
                    recovery.running_pipeline_pids(ROOT)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.responses = {}
        for edition in ('interior','exterior'):
            work = self.root/'ニュース収集' if edition=='interior' else self.root/'runtime/exterior'
            content = self.root if edition=='interior' else self.root/'content/exterior'
            (work/'logs').mkdir(parents=True)
            content.mkdir(parents=True,exist_ok=True)
            (work/'logs/latest_run_status.json').write_text(json.dumps({'edition_id':edition,'status':'success','published_news_date':'2026-10-14','release':'old-ui'}))
            base = 'http://IEWEB01/' + ('exterior/' if edition=='exterior' else '')
            self.responses[base+'health'] = json.dumps({'status':'ok','release':'new-ui'}).encode()
            self.responses[base+'publication_status.json'] = json.dumps({'edition_id':edition,'processed_through':'2026-10-14'}).encode()
            for name in ('news_data.js','insights_data.js'):
                data = (edition+name).encode()
                (content/name).write_bytes(data)
                self.responses[base+name] = data

    def pending(self, today=TODAY):
        return recovery.pending_editions(self.root,['interior','exterior'],today,self.responses.__getitem__)

    def test_current_publications_survive_ui_only_release_changes(self):
        self.assertEqual(self.pending(), [])

    def test_only_failed_or_stale_edition_recovers(self):
        status = self.root/'runtime/exterior/logs/latest_run_status.json'
        status.write_text(json.dumps({'edition_id':'exterior','status':'running','published_news_date':'2026-10-13'}))
        self.assertEqual(self.pending(), ['exterior'])

    def test_incomplete_or_mismatched_publication_does_not_count_as_complete(self):
        self.responses['http://IEWEB01/insights_data.js'] = b'older insights'
        self.assertEqual(self.pending(), ['interior'])
        self.responses['http://IEWEB01/exterior/publication_status.json'] = b'{"edition_id":"exterior","processed_through":"2026-10-13"}'
        self.assertEqual(self.pending(), ['interior','exterior'])

    def test_weekend_and_network_failure(self):
        self.assertEqual(self.pending(dt.date(2026,10,17)), [])
        def unavailable(url):raise OSError('network unavailable')
        self.assertEqual(recovery.pending_editions(self.root,['interior'],TODAY,unavailable), ['interior'])

    def test_two_attempts_per_edition_per_jst_day(self):
        path = self.root/'attempts.json'
        self.assertEqual(recovery.reserve_attempt(path,[],TODAY), [])
        self.assertFalse(path.exists())
        self.assertEqual(recovery.reserve_attempt(path,['interior','exterior'],TODAY), ['interior','exterior'])
        self.assertEqual(recovery.reserve_attempt(path,['exterior'],TODAY), ['exterior'])
        self.assertEqual(recovery.reserve_attempt(path,['interior','exterior'],TODAY), ['interior'])
        self.assertEqual(recovery.reserve_attempt(path,['interior','exterior'],TODAY), [])
        self.assertEqual(recovery.reserve_attempt(path,['exterior'],TODAY+dt.timedelta(days=1)), ['exterior'])


if __name__ == '__main__':unittest.main()
