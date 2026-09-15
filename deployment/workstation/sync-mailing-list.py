"""Refresh the exterior opt-in list without running news or sending mail."""
import datetime as dt
import importlib.util
import json
import msvcrt
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = Path(os.environ["LOCALAPPDATA"]) / "DailyNewsRuntime"


def main():
    config = json.loads((RUNTIME / "workstation.json").read_text(encoding="utf-8-sig"))
    if not config.get("enabled") or "exterior" not in config.get("editions", []):
        return 0
    collection = ROOT / "ニュース収集"
    sys.path.insert(0, str(collection))
    from processing_host import enforce_processing_host
    enforce_processing_host(ROOT)
    if os.environ.get("COMPUTERNAME", "").casefold() != config["hostname"].casefold():
        raise RuntimeError("Unexpected processing host")
    os.environ["DAILYNEWS_EDITION"] = "exterior"
    os.environ["DEPARTMENT"] = "exterior"
    for key in ("DAILYNEWS_POWER_AUTOMATE_STATUS", "DAILYNEWS_POWER_AUTOMATE_MAILING_LIST"):
        os.environ.pop(key, None)
    lock = (RUNTIME / "mailing-list.lock").open("a+b")
    lock.seek(0, 2)
    if not lock.tell():
        lock.write(b"0")
        lock.flush()
    lock.seek(0)
    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    try:
        # Importing the runner does not execute its main pipeline.
        spec = importlib.util.spec_from_file_location("mailing_list_runner", collection / "run_search_and_update.py")
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        count = runner.sync_power_automate_mailing_list()
        (RUNTIME / "mailing-list-sync.json").write_text(json.dumps({
            "edition_id": "exterior", "status": "success", "recipient_count": count,
            "updated_at": dt.datetime.now().astimezone().isoformat(),
        }), encoding="utf-8")
        return 0
    finally:
        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        lock.close()


if __name__ == "__main__":
    raise SystemExit(main())
