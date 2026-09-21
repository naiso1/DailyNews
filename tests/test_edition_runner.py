"""Offline checks for edition boundaries and publication retries (no collector import)."""
import argparse
import ast
from concurrent.futures import ThreadPoolExecutor
import datetime
import json
import os
from pathlib import Path
import re
import tempfile
import sys
import threading
import time
from types import SimpleNamespace
import unittest
import uuid
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "ニュース収集/run_search_and_update.py"


def function(name, env):
    tree = ast.parse(SOURCE.read_text(encoding="utf-8-sig"))
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), "exec"), env)
    return env[name]


class EditionRunnerTests(unittest.TestCase):
    def test_concurrent_json_writers_use_independent_temp_files(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mailing_list.json"
            barrier = threading.Barrier(2)
            temporary_paths = []
            lock = threading.Lock()

            def concurrent_replace(source, destination):
                with lock:
                    first_attempt = source not in temporary_paths
                    temporary_paths.append(source)
                # Both writers have finished writing before either replaces.
                if first_attempt:
                    barrier.wait(timeout=5)
                os.replace(source, destination)

            env = dict(Path=Path, json=json, uuid=uuid, time=time, os=SimpleNamespace(replace=concurrent_replace))
            write = function("_write_json_atomic", env)
            payloads = [{"edition_id": "exterior", "writer": value, "to": f"test{value}@example.com"} for value in (1, 2)]
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(write, path, payload) for payload in payloads]
                for future in futures:
                    future.result(timeout=10)
            self.assertEqual(len(set(temporary_paths)), 2)
            self.assertTrue(all(temporary.parent == path.parent for temporary in temporary_paths))
            self.assertIn(json.loads(path.read_text(encoding="utf-8")), payloads)
            self.assertEqual(set(path.parent.iterdir()), {path})

    def test_json_writer_retries_only_temporary_permission_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mailing_list.json"
            attempts = []

            def briefly_locked(source, destination):
                attempts.append(source)
                if len(attempts) < 3:
                    raise PermissionError("simulated sharing contention")
                os.replace(source, destination)

            sleep = Mock()
            env = dict(Path=Path, json=json, uuid=uuid, time=SimpleNamespace(sleep=sleep),
                       os=SimpleNamespace(replace=briefly_locked))
            function("_write_json_atomic", env)(path, {"complete": True})
            self.assertEqual(len(attempts), 3)
            self.assertEqual(len(set(attempts)), 1)
            self.assertEqual([call.args[0] for call in sleep.call_args_list], [0.05, 0.1])
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"complete": True})

    def test_failed_json_writer_cleans_only_its_own_temp_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mailing_list.json"
            path.write_text('{"previous": true}', encoding="utf-8")
            other_temp = path.with_name(".mailing_list.json.other-writer.tmp")
            other_temp.write_text("other writer owns this", encoding="utf-8")
            replace = Mock(side_effect=OSError("simulated replace failure"))
            env = dict(Path=Path, json=json, uuid=uuid, time=time, os=SimpleNamespace(replace=replace))
            write = function("_write_json_atomic", env)
            with self.assertRaisesRegex(OSError, "simulated replace failure"):
                write(path, {"new": True})
            own_temp = replace.call_args.args[0]
            self.assertFalse(own_temp.exists())
            self.assertEqual(other_temp.read_text(encoding="utf-8"), "other writer owns this")
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"previous": True})

    def test_exterior_partial_first_build_cannot_advance_publication_date(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            news = folder / "news_data.js"
            news.write_text('window.LOADED_NEWS_DATA = [{date: "2026-09-14"}];', encoding="utf-8")
            marker = folder / "publication_status.json"
            env = dict(EDITION=SimpleNamespace(id="exterior"), CONTENT_DIR=folder, NEWS_JS=news,
                       json=json, re=re, datetime=datetime)
            latest = function("latest_news_date", env)
            self.assertIsNone(latest())
            invalid = [
                {"edition_id": "exterior", "status": "building", "processed_through": ""},
                {"edition_id": "exterior", "status": "failed", "processed_through": "2026-09-14"},
                {"edition_id": "interior", "status": "published", "processed_through": "2026-09-14"},
                {"edition_id": "exterior", "status": "published", "processed_through": "2026-02-30"},
                {"edition_id": "exterior", "status": "published", "processed_through": None},
            ]
            for payload in invalid:
                marker.write_text(json.dumps(payload), encoding="utf-8")
                self.assertIsNone(latest(), payload)
            marker.write_text('{"edition_id":', encoding="utf-8")
            self.assertIsNone(latest())
            for status in ("published", "no_matching_news"):
                marker.write_text(json.dumps({"edition_id": "exterior", "status": status, "processed_through": "2026-09-13"}), encoding="utf-8")
                self.assertEqual(latest(), "2026-09-13")
            # Interior's established archive-based resume behavior is retained.
            env["EDITION"] = SimpleNamespace(id="interior")
            self.assertEqual(latest(), "2026-09-14")

    def main_env(self):
        yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
        env = dict(argparse=argparse, datetime=datetime, EDITION=SimpleNamespace(id="exterior"),
                   LOG_FILE=Path("unused.log"), SITE_URL="http://example.test/exterior/",
                   log=Mock(), active_schedule_pause=Mock(return_value=None), refresh_editorial_settings=Mock(),
                   latest_news_date=Mock(return_value=yesterday), resume_floor_after_pauses=Mock(return_value=None),
                   write_run_status=Mock(return_value={}), run_git_sync=Mock(),
                   run_server_deploy=Mock(return_value="a" * 40), sync_power_automate_mailing_list=Mock(return_value=1),
                   publish_automation_status_feed=Mock(), sleep_computer=Mock())
        return env

    def test_built_content_still_gets_deployed_before_success(self):
        env = self.main_env()
        main = function("main", env)
        with patch("sys.argv", ["runner", "--edition", "exterior"]):
            self.assertEqual(main(), 0)
        env["run_server_deploy"].assert_called_once()
        states = env["write_run_status"].call_args_list
        self.assertEqual(states[-1].args[0], "success")
        self.assertEqual(states[-1].kwargs["release"], "a" * 40)

    def test_deploy_failure_cannot_be_reported_as_success(self):
        env = self.main_env()
        env["run_server_deploy"].side_effect = RuntimeError("unavailable")
        main = function("main", env)
        with patch("sys.argv", ["runner", "--edition", "exterior"]):
            self.assertEqual(main(), 1)
        self.assertEqual(env["write_run_status"].call_args.args[0], "failed")
        env["sync_power_automate_mailing_list"].assert_not_called()

    def test_build_only_never_updates_notification_state_even_when_paused(self):
        for paused in (None, {"name": "holiday", "start": "2026-01-01", "end": "2026-01-02"}):
            env = self.main_env()
            env["active_schedule_pause"].return_value = paused
            main = function("main", env)
            with patch("sys.argv", ["runner", "--edition", "exterior", "--build-only"]):
                self.assertEqual(main(), 0)
            for name in ("write_run_status", "run_git_sync", "run_server_deploy", "sync_power_automate_mailing_list", "publish_automation_status_feed"):
                env[name].assert_not_called()

    def test_status_json_writes_only_selected_edition(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            interior = folder / "interior.json"
            exterior = folder / "exterior.json"
            interior.write_text('{"status":"keep"}', encoding="utf-8")
            env = dict(datetime=datetime, EDITION=SimpleNamespace(id="exterior"), RUN_ID="test-run",
                       LOG_FILE=folder / "run.log", RUN_STATUS_PATH=exterior,
                       _power_automate_status_path=lambda: None, log=Mock(),
                       _write_json_atomic=lambda path, payload: path.write_text(json.dumps(payload), encoding="utf-8"))
            payload = function("write_run_status", env)("running")
            self.assertEqual(payload["edition_id"], "exterior")
            self.assertEqual(json.loads(exterior.read_text())["run_id"], "test-run")
            self.assertEqual(json.loads(interior.read_text()), {"status": "keep"})

    def test_exterior_build_never_calls_gemini_even_with_available_key(self):
        for policy in ({"enabled": False, "provider": "none"}, {"enabled": True, "provider": "exabase"}):
            env = self.main_env()
            env.update(EDITION=SimpleNamespace(id="exterior", image_generation=policy),
                       os=os, sys=sys, ROOT=ROOT, WORK_DIR=Path("unused-exterior"),
                       DEFAULT_LLM_MODEL="local-test-model", CalledProcessError=RuntimeError,
                       get_google_search_entrypoint=Mock(return_value=Path("collector.py")),
                       ensure_lm_studio=Mock(return_value=True), count_sheet_targets=Mock(return_value=1),
                       run_cmd=Mock(), generate_source_list_data=Mock())
            env["latest_news_date"].return_value = None
            main = function("main", env)
            with patch("sys.argv", ["runner", "--edition", "exterior", "--build-only"]), patch.dict(os.environ, {"GEMINI_API_KEY": "test-not-a-real-key"}):
                self.assertEqual(main(), 0)
            calls = " ".join(str(call) for call in env["run_cmd"].call_args_list)
            self.assertIn("collector.py", calls)
            self.assertIn("auto_update_daily_news.py", calls)
            self.assertNotIn("generate_idea_images_gemini", calls)
            self.assertNotIn("update_exchange_rates.py", calls)


if __name__ == "__main__":
    unittest.main()
