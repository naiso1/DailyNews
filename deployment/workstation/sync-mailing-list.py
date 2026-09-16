"""Refresh each edition's opt-in list without running news or sending mail."""
import argparse
import datetime as dt
import importlib.util
import json
import msvcrt
import os
from pathlib import Path
import sys
import subprocess
import uuid

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = Path(os.environ["LOCALAPPDATA"]) / "DailyNewsRuntime"


def sync_edition(edition):
    os.environ["DAILYNEWS_EDITION"] = edition
    os.environ["DEPARTMENT"] = edition
    for key in ("DAILYNEWS_POWER_AUTOMATE_STATUS", "DAILYNEWS_POWER_AUTOMATE_MAILING_LIST"):
        os.environ.pop(key, None)
    collection = ROOT / "ニュース収集"
    sys.path.insert(0, str(collection))
    spec = importlib.util.spec_from_file_location("mailing_list_runner", collection / "run_search_and_update.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    return runner.sync_power_automate_mailing_list()


def refresh_editions(editions):
    results = {}
    for edition in editions:
        # A separate process prevents imported edition globals from crossing lists.
        try:
            result = subprocess.run(
                [sys.executable, "-B", str(Path(__file__).resolve()), "--edition", edition],
                cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=75, creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if result.returncode:
                raise RuntimeError("Mailing list sync failed")
            results[edition] = json.loads(result.stdout.strip().splitlines()[-1])
        except Exception as exc:
            # Do not persist provider responses, credentials or recipient addresses.
            results[edition] = {"status": "failed", "error_type": type(exc).__name__}
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--edition", choices=["interior", "exterior"])
    args = parser.parse_args()
    config = json.loads((RUNTIME / "workstation.json").read_text(encoding="utf-8-sig"))
    if not config.get("enabled"):
        return 0
    editions = config.get("editions", ["interior"])
    if not isinstance(editions, list) or not editions or len(set(editions)) != len(editions) or any(e not in {"interior", "exterior"} for e in editions):
        raise ValueError("Invalid enabled editions")
    collection = ROOT / "ニュース収集"
    sys.path.insert(0, str(collection))
    from processing_host import enforce_processing_host
    enforce_processing_host(ROOT)
    if os.environ.get("COMPUTERNAME", "").casefold() != config["hostname"].casefold():
        raise RuntimeError("Unexpected processing host")
    if args.edition:
        if args.edition not in editions:
            raise ValueError("Edition is not enabled")
        count = sync_edition(args.edition)
        print(json.dumps({"status": "success", "recipient_count": count}))
        return 0
    lock = (RUNTIME / "mailing-list.lock").open("a+b")
    lock.seek(0, 2)
    if not lock.tell():
        lock.write(b"0")
        lock.flush()
    lock.seek(0)
    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    try:
        results = refresh_editions(editions)
        success = all(value.get("status") == "success" for value in results.values())
        payload = {
            "status": "success" if success else "failed", "editions": results,
            "updated_at": dt.datetime.now().astimezone().isoformat(),
        }
        temporary = RUNTIME / f".mailing-list-sync.{uuid.uuid4().hex}.tmp"
        try:
            temporary.write_text(json.dumps(payload), encoding="utf-8")
            os.replace(temporary, RUNTIME / "mailing-list-sync.json")
        finally:
            temporary.unlink(missing_ok=True)
        return 0 if success else 1
    finally:
        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        lock.close()


if __name__ == "__main__":
    raise SystemExit(main())
