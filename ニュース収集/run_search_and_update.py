import datetime
import os
import re
from pathlib import Path
from subprocess import Popen, CalledProcessError, CREATE_NEW_PROCESS_GROUP, PIPE, STDOUT
import signal
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
NEWS_JS = ROOT / "news_data.js"
WORKFLOW = ROOT / "image_flux2_klein_text_to_image (1).json"
LOG_DIR = Path(__file__).resolve().parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / f"run_search_and_update_{datetime.date.today().strftime('%Y%m%d')}.log"


def log(msg):
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(msg + "\n")


def latest_news_date():
    if not NEWS_JS.exists():
        return None
    text = NEWS_JS.read_text(encoding="utf-8", errors="ignore")
    dates = re.findall(r"\bdate:\s*\"(\d{4}-\d{2}-\d{2})\"", text)
    return max(dates) if dates else None


def run_cmd(cmd, label, log_file):
    log(f"[RUN] {label}: {' '.join(cmd)}")
    proc = None
    try:
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        try:
            proc = Popen(
                cmd,
                creationflags=CREATE_NEW_PROCESS_GROUP,
                stdout=PIPE,
                stderr=STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=env,
            )
        except Exception as e:
            log(f"[ERROR] {label} failed to start: {type(e).__name__}: {e}")
            raise
        log(f"[PID] {label}: {proc.pid}")
        if proc.stdout:
            for line in proc.stdout:
                line = line.rstrip("\r\n")
                if line:
                    log(f"[{label}] {line}")
                    print(f"[{label}] {line}", flush=True)
        proc.wait()
        log(f"[EXIT] {label}: code={proc.returncode}")
        if proc.returncode != 0:
            raise CalledProcessError(proc.returncode, cmd)
    except KeyboardInterrupt:
        log(f"[INTERRUPT] {label} interrupted by user.")
        try:
            if proc and proc.poll() is None:
                if hasattr(signal, "CTRL_BREAK_EVENT"):
                    proc.send_signal(signal.CTRL_BREAK_EVENT)
                proc.terminate()
        except Exception:
            pass
        raise


def main():
    log("==================================================")
    log(f"[START] {datetime.datetime.now():%Y-%m-%d %H:%M:%S}")

    latest = latest_news_date()
    if latest:
        start = datetime.datetime.strptime(latest, "%Y-%m-%d").date() + datetime.timedelta(days=1)
    else:
        start = datetime.date.today() - datetime.timedelta(days=1)
    end = datetime.date.today() - datetime.timedelta(days=1)

    log(f"[INFO] Target range: {start} to {end}")

    if start > end:
        log("[INFO] No new dates to process.")
    else:
        dates = []
        cur = start
        while cur <= end:
            dates.append(cur.strftime("%Y-%m-%d"))
            cur += datetime.timedelta(days=1)
        dates_arg = ",".join(dates)
        try:
            run_cmd([sys.executable, "-u", str(SCRIPT_DIR / "google_search_script.py"), "--dates", dates_arg], "google_search_script", LOG_FILE)
            run_cmd([sys.executable, "-u", str(ROOT / "auto_update_daily_news.py")], "auto_update_daily_news", LOG_FILE)
            if os.environ.get("OPENAI_API_KEY"):
                image_quality = os.environ.get("OPENAI_IMAGE_QUALITY", "high").strip().lower() or "high"
                if image_quality not in {"low", "medium", "high"}:
                    image_quality = "high"
                run_cmd(
                    [
                        sys.executable,
                        "-u",
                        str(ROOT / "generate_idea_images_openai.py"),
                        "--only-missing",
                        "--quality",
                        image_quality,
                    ],
                    "generate_idea_images_openai",
                    LOG_FILE,
                )
            else:
                log("[WARN] OPENAI_API_KEY not set; skip OpenAI image generation.")
        except KeyboardInterrupt:
            log("[INFO] Interrupted by user.")
            return
        except CalledProcessError as e:
            log(f"[ERROR] Command failed: {e}")
        except Exception as e:
            log(f"[ERROR] Unexpected error: {type(e).__name__}: {e}")

    log(f"[END] {datetime.datetime.now():%Y-%m-%d %H:%M:%S}")
    log("==================================================")

if __name__ == "__main__":
    main()
