"""Mail opt-outs and independent edition sync; no server or email access."""
import ast
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]


class MailingListSyncTests(unittest.TestCase):
    def test_one_failed_edition_does_not_skip_the_other(self):
        spec = importlib.util.spec_from_file_location("mail_sync_test", ROOT / "deployment/workstation/sync-mailing-list.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        calls = []

        def run(args, **kwargs):
            calls.append(args)
            if args[-1] == "interior":
                raise subprocess.TimeoutExpired(args, 75)
            return SimpleNamespace(returncode=0, stdout='log line\n{"status":"success","recipient_count":1}\n')

        with patch.object(module.subprocess, "run", side_effect=run):
            result = module.refresh_editions(["interior", "exterior"])
        self.assertEqual([call[-1] for call in calls], ["interior", "exterior"])
        self.assertEqual(result["interior"]["status"], "failed")
        self.assertEqual(result["exterior"]["recipient_count"], 1)

    def _export(self, payload, edition="interior"):
        source = ROOT / "ニュース収集/run_search_and_update.py"
        tree = ast.parse(source.read_text(encoding="utf-8-sig"))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "sync_power_automate_mailing_list")
        destination = Path("unused-test-mailing-list.json")
        write = Mock()
        env = dict(Path=Path, os=SimpleNamespace(environ={}), json=json, ROOT=ROOT,
                   REMOTE_FOLDER="UnusedTestRoot", EDITION=SimpleNamespace(id=edition),
                   _power_automate_mailing_list_path=lambda: destination,
                   _write_json_atomic=write, log=Mock(),
                   subprocess=SimpleNamespace(run=Mock(return_value=SimpleNamespace(
                       returncode=0, stdout=json.dumps(payload), stderr=""))))
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), "exec"), env)
        return env["sync_power_automate_mailing_list"], write, destination

    def test_zero_recipients_overwrites_previous_list_for_both_editions(self):
        for edition in ("interior", "exterior"):
            call, write, path = self._export({"recipientCount": 0, "to": "", "recipients": []}, edition)
            self.assertEqual(call(), 0)
            self.assertEqual(write.call_args.args[0], path)
            self.assertEqual(write.call_args.args[1]["edition_id"], edition)

    def test_inconsistent_export_does_not_replace_list(self):
        call, write, _ = self._export({"recipientCount": 0, "to": "someone@example.com", "recipients": []})
        with self.assertRaises(RuntimeError):
            call()
        write.assert_not_called()


if __name__ == "__main__":
    unittest.main()
