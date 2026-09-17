"""The Windows session task must never become a second news or image job."""
from contextlib import contextmanager
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
if os.name == 'nt':
    spec = importlib.util.spec_from_file_location('session_maintenance', ROOT / 'deployment/workstation/exabase/maintain-session.py')
    maintenance = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(maintenance)


@contextmanager
def slot(available):
    yield available


@unittest.skipUnless(os.name == 'nt', 'Windows scheduled-task runner')
class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.runtime = Path(self.temp.name)
        (self.runtime / 'exabase').mkdir()
        self.state = self.runtime / 'exabase/session-health.json'
        (self.runtime / 'exabase/auth.bin').write_bytes(b'encrypted-fixture')
        (self.runtime / 'exabase/installation.json').write_text('{}')

    def run_main(self, result, available=True):
        with patch.object(maintenance, 'eligible', return_value=True), \
             patch.object(maintenance, 'processing_slot', return_value=slot(available)), \
             patch.object(maintenance, 'refresh', return_value=result) as refresh:
            code = maintenance.main(ROOT, self.runtime)
        return code, refresh

    def test_inactive_host_or_disabled_configuration_does_not_touch_status_or_browser(self):
        for enabled, hostname, repository, allowed in ((False, 'TESTPC', str(ROOT), True),
                (True, 'OTHERPC', str(ROOT), True), (True, 'TESTPC', 'C:/other', True),
                (True, 'TESTPC', str(ROOT), False), (True, '', str(ROOT), True)):
            with self.subTest(enabled=enabled, hostname=hostname, repository=repository, allowed=allowed):
                (self.runtime / 'workstation.json').write_text(json.dumps({'enabled': enabled, 'hostname': hostname, 'repository': repository}))
                with patch.dict(os.environ, {'COMPUTERNAME': 'TESTPC'}), \
                     patch.object(maintenance, 'processing_host_status', return_value={'allowed': allowed}), \
                     patch.object(maintenance, 'refresh') as refresh:
                    self.assertEqual(maintenance.main(ROOT, self.runtime), 0)
                refresh.assert_not_called()
                self.assertFalse(self.state.exists())

    def test_malformed_configuration_fails_before_network_or_state_writes(self):
        (self.runtime / 'workstation.json').write_text('{bad json')
        with patch.object(maintenance, 'refresh') as refresh:
            self.assertEqual(maintenance.main(ROOT, self.runtime), 2)
        refresh.assert_not_called()
        self.assertFalse(self.state.exists())

    def test_daily_pipeline_lock_skips_network_without_losing_last_success(self):
        previous = '2026-09-17T09:00:00+09:00'
        self.state.write_text(json.dumps({'last_success_at': previous}))
        code, refresh = self.run_main(('authenticated', ''), available=False)
        self.assertEqual(code, 0)
        refresh.assert_not_called()
        data = json.loads(self.state.read_text())
        self.assertEqual(data['code'], 'PROCESSING_BUSY')
        self.assertEqual(data['last_success_at'], previous)

    def test_success_and_expiry_keep_only_safe_state_and_never_modify_auth_file(self):
        self.state.write_text(json.dumps({'cookie': 'secret-fixture'}))
        self.assertEqual(self.run_main(('authenticated', ''))[0], 0)
        success = json.loads(self.state.read_text())['last_success_at']
        self.assertEqual(self.run_main(('action_required', 'AUTH_REQUIRED'))[0], 1)
        data = json.loads(self.state.read_text())
        self.assertEqual(data['status'], 'action_required')
        self.assertEqual(data['last_success_at'], success)
        self.assertNotIn('secret-fixture', self.state.read_text())
        self.assertEqual((self.runtime / 'exabase/auth.bin').read_bytes(), b'encrypted-fixture')

    def test_worker_is_check_only_and_raw_output_is_never_saved(self):
        process = Mock(returncode=0)
        process.communicate.return_value = ('not-json secret\n{"status":"AUTHENTICATED","cookie":"secret"}\n', 'raw secret')
        with patch.object(maintenance.shutil, 'which', return_value='node.exe'), \
             patch.object(maintenance.subprocess, 'Popen', return_value=process) as popen:
            self.assertEqual(maintenance.refresh(ROOT), ('authenticated', ''))
        command = popen.call_args.args[0]
        self.assertEqual(command[-1], '--check-session')
        self.assertNotIn('--generate', command)

    def test_unrecognized_provider_diagnostics_are_replaced_by_safe_code(self):
        process = Mock(returncode=1)
        process.communicate.return_value = ('{"status":"ERROR","code":"secret token"}', '')
        with patch.object(maintenance.shutil, 'which', return_value='node.exe'), \
             patch.object(maintenance.subprocess, 'Popen', return_value=process):
            self.assertEqual(maintenance.refresh(ROOT), ('error', 'EXABASE_UNAVAILABLE'))

    def test_timeout_stops_only_its_own_child_tree(self):
        process = Mock(pid=765432, returncode=1)
        process.poll.return_value = 1
        process.communicate.side_effect = [subprocess.TimeoutExpired('worker', 180), ('', '')]
        with patch.object(maintenance.shutil, 'which', return_value='node.exe'), \
             patch.object(maintenance.subprocess, 'Popen', return_value=process), \
             patch.object(maintenance.subprocess, 'run', return_value=Mock(returncode=0)) as stop:
            self.assertEqual(maintenance.refresh(ROOT), ('error', 'CHECK_TIMEOUT'))
        self.assertEqual(stop.call_args.args[0], ['taskkill.exe', '/PID', '765432', '/T', '/F'])

    def test_failed_tree_stop_still_reaps_worker_and_reports_unconfirmed_cleanup(self):
        process = Mock(pid=765432)
        process.poll.side_effect = [None, 1]
        process.communicate.side_effect = [subprocess.TimeoutExpired('worker', 180), ('', '')]
        with patch.object(maintenance.shutil, 'which', return_value='node.exe'), \
             patch.object(maintenance.subprocess, 'Popen', return_value=process), \
             patch.object(maintenance.subprocess, 'run', side_effect=subprocess.TimeoutExpired('taskkill', 15)):
            self.assertEqual(maintenance.refresh(ROOT), ('error', 'CHECK_CLEANUP_FAILED'))
        process.kill.assert_called_once()
        self.assertEqual(process.communicate.call_count, 2)

    def test_worker_busy_is_skipped_not_a_false_authentication_failure(self):
        process = Mock(returncode=1)
        process.communicate.return_value = ('{"status":"ERROR","code":"BUSY"}', '')
        with patch.object(maintenance.shutil, 'which', return_value='node.exe'), \
             patch.object(maintenance.subprocess, 'Popen', return_value=process):
            self.assertEqual(maintenance.refresh(ROOT), ('skipped', 'BUSY'))


if __name__ == '__main__':
    unittest.main()
