"""pythonw entry point: scheduled collection does not open console windows."""
import contextlib, sys, traceback
from pathlib import Path
from weekly_report import STATE, run
from argparse import Namespace

STATE.mkdir(parents=True,exist_ok=True)
with (STATE/'scheduled.log').open('a',encoding='utf8') as log, contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):
    try: run(Namespace(master_root=str(__import__('weekly_report').MASTER_ROOT),publish=True,onedrive=True))
    except Exception:
        traceback.print_exc();sys.exit(1)
