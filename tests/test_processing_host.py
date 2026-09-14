"""Offline host selection and real runner early-exit checks, with no pipeline."""
import importlib.util
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SOURCE = next(ROOT.glob("*/processing_host.py"))
SPEC = importlib.util.spec_from_file_location("processing_host_tested", SOURCE)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ProcessingHostTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.policy = self.root / "deployment/workstation/processing_host.json"
        self.policy.parent.mkdir(parents=True)

    def write_policy(self, active="NEW-PC"):
        self.policy.write_text(json.dumps({"schema_version": 1, "active_host": active}), encoding="utf-8")

    def test_only_selected_host_is_allowed_case_insensitively(self):
        self.write_policy()
        self.assertTrue(MODULE.processing_host_status(self.root, "new-pc")["allowed"])
        self.assertFalse(MODULE.processing_host_status(self.root, "OLD-PC")["allowed"])

    def test_missing_or_invalid_policy_fails_closed(self):
        with self.assertRaises(RuntimeError):
            MODULE.processing_host_status(self.root)
        for text in ("", "null", "{}", "[]", '{"schema_version":true,"active_host":"NEW-PC"}',
                     '{"schema_version":2,"active_host":"NEW-PC"}'):
            self.policy.write_text(text, encoding="utf-8")
            with self.subTest(text=text), self.assertRaises(RuntimeError):
                MODULE.processing_host_status(self.root)
        for host in ("", "*", "NEW-PC ", "NEW-PC; command", None, []):
            self.write_policy(host)
            with self.subTest(host=host), self.assertRaises(RuntimeError):
                MODULE.processing_host_status(self.root)

    def test_allowed_host_continues_without_output(self):
        self.write_policy()
        with patch.object(MODULE.socket, "gethostname", return_value="NEW-PC"), patch("builtins.print") as output:
            MODULE.enforce_processing_host(self.root)
            output.assert_not_called()

    def test_retired_host_exits_successfully_without_writes(self):
        self.write_policy()
        before = self.policy.read_bytes()
        with patch.object(MODULE.socket, "gethostname", return_value="OLD-PC"), patch("builtins.print"):
            with self.assertRaises(SystemExit) as result:
                MODULE.enforce_processing_host(self.root)
        self.assertEqual(result.exception.code, 0)
        self.assertEqual(self.policy.read_bytes(), before)

    def runner(self, check_only=False):
        collection = self.root / "collection"
        collection.mkdir()
        shutil.copy2(SOURCE, collection / SOURCE.name)
        script = collection / "run_search_and_update.py"
        shutil.copy2(SOURCE.with_name(script.name), script)
        args = [sys.executable, "-B", str(script)]
        if check_only:
            args.append("--check-processing-host")
        result = subprocess.run(args, cwd=collection, capture_output=True, text=True, timeout=15)
        self.assertFalse((collection / "logs").exists())
        return result

    def test_actual_retired_runner_exits_before_creating_logs(self):
        self.write_policy("not-this-workstation")
        result = self.runner()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"allowed": false', result.stdout)

    def test_actual_active_runner_diagnostic_exits_without_processing(self):
        self.write_policy(socket.gethostname())
        result = self.runner(check_only=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"allowed": true', result.stdout)

    def test_actual_runner_missing_policy_stops_without_creating_logs(self):
        result = self.runner()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Processing-host policy unavailable or invalid", result.stderr)


if __name__ == "__main__":
    unittest.main()
