"""Offline memory-state checks; never import or run the scheduled collector."""
import ast
import io
import json
import importlib.util
import sys
from pathlib import Path
import types
import unittest
from unittest.mock import Mock, patch


class LoadedModelTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        script = next(root.glob("*/run_search_and_update.py"))
        spec = importlib.util.spec_from_file_location("lm_state_test", script.with_name("lm_studio_state.py"))
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        tree = ast.parse(script.read_text(encoding="utf-8-sig"))
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                 and n.name in {"_loaded_model_ids", "ensure_lm_studio"}]
        self.urlopen = Mock()
        self.env = {"json": json, "urllib": types.SimpleNamespace(
            request=types.SimpleNamespace(urlopen=self.urlopen)), "log": Mock()}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "lm-state", "exec"), self.env)
        self.read = lambda host: self.module.loaded_model_ids(host, opener=self.urlopen)

    def response(self, value):
        return io.BytesIO(json.dumps(value).encode())

    def test_downloaded_models_are_not_loaded(self):
        self.urlopen.return_value = self.response({"models": [
            {"key": "qwen/qwen3.5-9b", "loaded_instances": []},
            {"key": "other", "loaded_instances": []}]})
        self.assertEqual(self.read("http://localhost:1234"), set())
        self.assertEqual(self.urlopen.call_count, 1)

    def test_loaded_instance_ids_include_multiple_instances(self):
        self.urlopen.return_value = self.response({"models": [
            {"key": "qwen", "loaded_instances": [{"id": "qwen"}, {"id": "qwen:2"}]},
            {"key": "embedding", "loaded_instances": [{"id": "embedding"}]}]})
        self.assertEqual(self.read("http://localhost:1234"), {"qwen", "qwen:2", "embedding"})

    def test_legacy_state_is_supported(self):
        self.urlopen.side_effect = [OSError("v1 unavailable"), self.response({"data": [
            {"id": "qwen", "state": "loaded"}, {"id": "other", "state": "not-loaded"}]})]
        self.assertEqual(self.read("http://localhost:1234"), {"qwen"})

    def test_unknown_state_fails_closed_without_openai_list_fallback(self):
        self.urlopen.side_effect = [self.response({"models": [{"key": "qwen"}]}),
                                   self.response({"data": [{"id": "qwen"}]})]
        with self.assertRaises(RuntimeError):
            self.read("http://localhost:1234")
        self.assertEqual(self.urlopen.call_count, 2)
        self.assertTrue(all("/api/" in call.args[0] for call in self.urlopen.call_args_list))

    def test_connection_failure_prevents_loading(self):
        self.env["_ensure_lm_studio"] = Mock(side_effect=RuntimeError("unknown state"))
        self.assertFalse(self.env["ensure_lm_studio"]())
        self.env["log"].assert_called_once()

    def test_startup_and_collector_share_the_same_native_state_reader(self):
        reader = Mock(return_value={"qwen"})
        module = types.SimpleNamespace(loaded_model_ids=reader)
        root = Path(__file__).resolve().parents[1]
        script = next(root.glob("*/google_search_script.py"))
        tree = ast.parse(script.read_text(encoding="utf-8-sig"))
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                 and n.name == "_loaded_llm_model_ids"]
        env = {"LLM_ENDPOINT": "http://127.0.0.1:1234/v1/chat/completions"}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "collector-state", "exec"), env)
        with patch.dict(sys.modules, {"lm_studio_state": module}):
            self.assertEqual(env["_loaded_llm_model_ids"](), {"qwen"})
            self.assertEqual(self.env["_loaded_model_ids"]("http://127.0.0.1:1234"), {"qwen"})
            self.assertEqual(reader.call_count, 2)
            self.assertEqual(reader.call_args.args, ("http://127.0.0.1:1234",))


if __name__ == "__main__":
    unittest.main()
