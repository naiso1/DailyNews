"""One-run overrides must reach idea review without changing scheduled defaults."""
import argparse
import ast
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]


class RunModelOverrideTests(unittest.TestCase):
    def test_explicit_model_is_process_only_and_default_clears_stale_override(self):
        tree = ast.parse((ROOT/'deployment/workstation/run.py').read_text(encoding='utf-8-sig'))
        main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True):
            runtime = Path(tmp)
            original = json.dumps({'enabled': True, 'llmModel': 'scheduled-model', 'gpuOffload': '0.7'})
            (runtime/'workstation.json').write_text(original)
            def prepare(config, editions):
                os.environ['LLM_MODEL'] = config['llmModel']
                os.environ['LLM_GPU_OFFLOAD'] = config['gpuOffload']
                return {}
            def check(config, proxies, editions):
                return {'model': os.environ['LLM_MODEL'], 'idea': os.environ.get('DAILYNEWS_IDEA_MODEL'),
                        'gpu': os.environ['LLM_GPU_OFFLOAD']}
            env = dict(argparse=argparse, json=json, os=os, RUNTIME=runtime, prepare=prepare, check=check,
                       msvcrt=SimpleNamespace(locking=Mock(), LK_NBLCK=1, LK_UNLCK=2),
                       ctypes=SimpleNamespace(windll=SimpleNamespace(kernel32=SimpleNamespace(SetThreadExecutionState=Mock()))))
            exec(compile(ast.Module(body=[main], type_ignores=[]), 'run.py', 'exec'), env)
            with patch.object(sys, 'argv', ['run.py', '--check-only', '--llm-model', 'trial-model', '--gpu-offload', '0.5']):
                self.assertEqual(env['main'](), 0)
            self.assertEqual(json.loads((runtime/'preflight-result.json').read_text()), {'model': 'trial-model', 'idea': 'trial-model', 'gpu': '0.5'})
            self.assertEqual((runtime/'workstation.json').read_text(), original)
            with patch.object(sys, 'argv', ['run.py', '--check-only']):
                self.assertEqual(env['main'](), 0)
            self.assertEqual(json.loads((runtime/'preflight-result.json').read_text()), {'model': 'scheduled-model', 'idea': None, 'gpu': '0.7'})

    def test_idea_generation_and_review_receive_the_override(self):
        tree = ast.parse((ROOT/'auto_update_daily_news.py').read_text(encoding='utf-8-sig'))
        call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and isinstance(n.func.value, ast.Name) and n.func.value.id == 'idea_quality' and n.func.attr == 'generate_country')
        callback = next(n for n in call.args if isinstance(n, ast.Lambda))
        for override, expected in [('trial-model', 'trial-model'), ('', 'department-model')]:
            with self.subTest(override=override):
                llm = Mock(return_value='answer')
                env = dict(args=SimpleNamespace(idea_model=override, llm_model='base-model', llm_endpoint='local'),
                           EDITION=SimpleNamespace(config={'idea_generation': {'model': 'department-model'}}), call_llm=llm)
                fn = eval(compile(ast.Expression(callback), 'updater.py', 'eval'), env)
                self.assertEqual(fn('review prompt'), 'answer')
                llm.assert_called_once_with('local', expected, 'review prompt', max_tokens=2600, temperature=0.2)


if __name__ == '__main__':
    unittest.main()
