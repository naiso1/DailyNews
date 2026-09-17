"""Refresh exaBase authentication without generating images or publishing content."""
from contextlib import contextmanager
import datetime as dt
import json
import msvcrt
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[3]
RUNTIME = Path(os.environ.get('LOCALAPPDATA', '')) / 'DailyNewsRuntime'
sys.path.insert(0, str(ROOT))
from ニュース収集.processing_host import processing_host_status

SAFE_CODES = {'AUTH_REQUIRED', 'BUSY', 'ENGINE_CHANGED', 'EDGE_MISSING', 'RUNTIME_MISSING',
              'WINDOWS_REQUIRED', 'SESSION_UNAVAILABLE', 'EXABASE_UNAVAILABLE'}


def eligible(root, runtime):
    """Fail closed before network access or status writes on a retired workstation."""
    config = json.loads((runtime / 'workstation.json').read_text(encoding='utf-8-sig'))
    return (config.get('enabled') is True
            and isinstance(config.get('hostname'), str) and bool(config['hostname'].strip())
            and isinstance(config.get('repository'), str) and bool(config['repository'].strip())
            and str(config.get('hostname', '')).casefold() == os.environ.get('COMPUTERNAME', '').casefold()
            and Path(config.get('repository', '')).resolve() == root.resolve()
            and processing_host_status(root)['allowed']
            and (runtime / 'exabase' / 'installation.json').is_file())


@contextmanager
def processing_slot(runtime):
    with (runtime / 'run.lock').open('a+b') as handle:
        handle.seek(0, 2)
        if not handle.tell():
            handle.write(b'0'); handle.flush()
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            yield False
            return
        try:
            yield True
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def stop_worker(process):
    """Bounded recovery for this child only; report unconfirmed tree cleanup."""
    tree_stopped = False
    try:
        result = subprocess.run(['taskkill.exe', '/PID', str(process.pid), '/T', '/F'],
                                capture_output=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
        tree_stopped = result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        pass
    finally:
        if process.poll() is None:
            try:
                process.kill()
            except OSError:
                pass
        try:
            process.communicate(timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            tree_stopped = False
    return tree_stopped and process.poll() is not None


def refresh(root):
    node = shutil.which('node')
    if not node:
        return 'error', 'RUNTIME_MISSING'
    process = subprocess.Popen(
        [node, str(root / 'deployment/workstation/exabase/worker.js'), '--check-session'],
        cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding='utf-8', errors='replace', creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        output, _ = process.communicate(timeout=180)
    except subprocess.TimeoutExpired:
        # This PID belongs to the worker created above, never an unrelated browser.
        cleaned = stop_worker(process)
        return 'error', 'CHECK_TIMEOUT' if cleaned else 'CHECK_CLEANUP_FAILED'
    last = {}
    for line in output.splitlines():
        try:
            value = json.loads(line)
            if isinstance(value, dict) and 'status' in value:
                last = value
        except (ValueError, TypeError):
            pass
    if process.returncode == 0 and last.get('status') == 'AUTHENTICATED':
        return 'authenticated', ''
    code = last.get('code')
    code = code if code in SAFE_CODES else 'EXABASE_UNAVAILABLE'
    return ('action_required' if code == 'AUTH_REQUIRED' else 'skipped' if code == 'BUSY' else 'error'), code


def record(runtime, status, code):
    target = runtime / 'exabase/session-health.json'
    previous = {}
    try:
        previous = json.loads(target.read_text(encoding='utf-8'))
        if not isinstance(previous, dict):
            previous = {}
    except (OSError, ValueError):
        pass
    now = dt.datetime.now().astimezone().isoformat(timespec='seconds')
    last_success = previous.get('last_success_at')
    try:
        if last_success:
            dt.datetime.fromisoformat(last_success)
    except (ValueError, TypeError):
        last_success = None
    result = {'schema_version': 1, 'status': status, 'code': code, 'last_checked_at': now,
              'last_success_at': now if status == 'authenticated' else last_success,
              'interval_minutes': 30}
    temporary = target.with_name('.session-health.' + uuid.uuid4().hex + '.tmp')
    try:
        temporary.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def main(root=ROOT, runtime=RUNTIME, validate_only=False):
    try:
        allowed = eligible(root, runtime)
    except Exception:
        return 2
    if not allowed:
        return 2 if validate_only else 0
    if validate_only:
        return 0
    try:
        with processing_slot(runtime) as available:
            if not available:
                record(runtime, 'skipped', 'PROCESSING_BUSY')
                return 0
            try:
                status, code = refresh(root)
            except Exception:
                # Browser/provider error text may include sensitive values.
                status, code = 'error', 'CHECK_UNAVAILABLE'
            record(runtime, status, code)
            return 0 if status in {'authenticated', 'skipped'} else 1
    except Exception:
        return 1


if __name__ == '__main__':
    if sys.argv[1:] not in ([], ['--validate-only']):
        raise SystemExit(2)
    raise SystemExit(main(validate_only='--validate-only' in sys.argv))
