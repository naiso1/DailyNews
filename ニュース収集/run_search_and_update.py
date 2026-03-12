import argparse
import datetime
import json
import os
import re
import subprocess
import time
import urllib.request
from pathlib import Path
from subprocess import Popen, CalledProcessError, CREATE_NEW_PROCESS_GROUP, PIPE, STDOUT
import signal
import sys
import py_compile

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


LMS_EXE = Path.home() / ".lmstudio" / "bin" / "lms.exe"


def _llm_host():
    endpoint = os.environ.get("LLM_ENDPOINT", "http://127.0.0.1:1234/v1/chat/completions")
    idx = endpoint.find("/v1/")
    return endpoint[:idx] if idx != -1 else "http://127.0.0.1:1234"


def _server_up(host):
    try:
        with urllib.request.urlopen(f"{host}/v1/models", timeout=5) as r:
            return r.status == 200
    except Exception:
        return False


def _model_loaded(host):
    try:
        with urllib.request.urlopen(f"{host}/v1/models", timeout=5) as r:
            data = json.loads(r.read())
            return len(data.get("data", [])) > 0
    except Exception:
        return False


def ensure_lm_studio():
    """LM Studio サーバーが起動していなければ起動し、モデルをロードする。"""
    host = _llm_host()
    model = os.environ.get("LLM_MODEL", "qwen/qwen3.5-9b")

    if _server_up(host) and _model_loaded(host):
        log("[LM Studio] サーバー起動済み・モデルロード済み。")
        return

    if not _server_up(host):
        if not LMS_EXE.exists():
            log(f"[WARN] lms.exe が見つかりません ({LMS_EXE})。自動起動をスキップします。")
            return
        log("[LM Studio] サーバーを起動します...")
        try:
            Popen(
                [str(LMS_EXE), "server", "start"],
                creationflags=CREATE_NEW_PROCESS_GROUP,
                stdout=PIPE, stderr=STDOUT,
            )
        except Exception as e:
            log(f"[WARN] lms server start 失敗: {e}")
            return
        for i in range(24):  # 最大120秒待機
            time.sleep(5)
            if _server_up(host):
                log(f"[LM Studio] サーバー起動完了 ({(i + 1) * 5}秒)。")
                break
        else:
            log("[WARN] LM Studio サーバーが120秒以内に起動しませんでした。")
            return

    if not _model_loaded(host):
        log(f"[LM Studio] モデルをロードします: {model}")
        try:
            Popen(
                [str(LMS_EXE), "load", model],
                creationflags=CREATE_NEW_PROCESS_GROUP,
                stdout=PIPE, stderr=STDOUT,
            )
        except Exception as e:
            log(f"[WARN] lms load 失敗: {e}")
        for i in range(30):  # 最大300秒待機
            time.sleep(10)
            if _model_loaded(host):
                log(f"[LM Studio] モデルロード完了 ({(i + 1) * 10}秒)。")
                break
        else:
            log("[WARN] モデルが300秒以内にロードされませんでした。")


def sleep_computer():
    """PCをスリープ状態にする（Windows）。"""
    log("[INFO] 処理完了。PCをスリープします...")
    subprocess.run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])


def get_google_search_entrypoint():
    src = SCRIPT_DIR / "google_search_script.py"
    pyc = SCRIPT_DIR / "__pycache__" / f"google_search_script.cpython-{sys.version_info.major}{sys.version_info.minor}.pyc"
    try:
        py_compile.compile(str(src), doraise=True)
        return src
    except Exception as e:
        if pyc.exists():
            log(f"[WARN] google_search_script.py syntax check failed; fallback to pyc: {type(e).__name__}: {e}")
            return pyc
        raise


def latest_news_date():
    if not NEWS_JS.exists():
        return None
    text = NEWS_JS.read_text(encoding="utf-8", errors="ignore")
    dates = re.findall(r"\bdate:\s*\"(\d{4}-\d{2}-\d{2})\"", text)
    return max(dates) if dates else None


def run_cmd(cmd, label, log_file, cwd=None):
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
                cwd=str(cwd) if cwd else None,
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


def run_git_sync(log_file):
    # Default ON (set AUTO_GIT_SYNC=0 to disable)
    if os.environ.get("AUTO_GIT_SYNC", "1").strip().lower() in {"0", "false", "no"}:
        log("[INFO] AUTO_GIT_SYNC disabled; skip git commit/push.")
        return

    # Avoid self-dirtying the repo by excluding volatile runtime files.
    pathspecs = [
        ".",
        ":(exclude)ニュース収集/logs/*",
        ":(exclude)ニュース収集/__pycache__/*",
        ":(exclude)**/__pycache__/*",
    ]

    status_cmd = ["git", "status", "--porcelain", "--", *pathspecs]
    log(f"[RUN] git_status: {' '.join(status_cmd)}")
    st = subprocess.run(
        status_cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if st.returncode != 0:
        if st.stdout:
            for line in st.stdout.splitlines():
                if line.strip():
                    log(f"[git_status] {line}")
        if st.stderr:
            for line in st.stderr.splitlines():
                if line.strip():
                    log(f"[git_status] {line}")
        raise CalledProcessError(st.returncode, status_cmd)

    if st.stdout:
        for line in st.stdout.splitlines():
            if line.strip():
                log(f"[git_status] {line}")
    if not st.stdout.strip():
        log("[INFO] No git changes to commit/push.")
        return

    run_cmd(["git", "add", "-A", "--", *pathspecs], "git_add", log_file, cwd=ROOT)

    diff_cmd = ["git", "diff", "--cached", "--quiet"]
    diff_rc = subprocess.run(diff_cmd, cwd=str(ROOT)).returncode
    if diff_rc == 0:
        log("[INFO] No staged changes after filtered git add.")
        return
    if diff_rc not in (0, 1):
        raise CalledProcessError(diff_rc, diff_cmd)

    branch_cmd = ["git", "branch", "--show-current"]
    branch_cp = subprocess.run(
        branch_cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    branch = branch_cp.stdout.strip() or "main"
    msg = f"Auto update daily news ({datetime.date.today().isoformat()})"
    run_cmd(["git", "commit", "-m", msg], "git_commit", log_file, cwd=ROOT)
    run_cmd(["git", "push", "origin", branch], "git_push", log_file, cwd=ROOT)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-sleep", action="store_true", help="処理完了後にスリープしない")
    args = parser.parse_args()

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
            ensure_lm_studio()
            google_search_script = get_google_search_entrypoint()
            run_cmd([sys.executable, "-u", str(google_search_script), "--dates", dates_arg], "google_search_script", LOG_FILE)
            run_cmd([sys.executable, "-u", str(ROOT / "auto_update_daily_news.py")], "auto_update_daily_news", LOG_FILE)
            if os.environ.get("GEMINI_API_KEY"):
                gemini_model = os.environ.get("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image-preview").strip() or "gemini-3.1-flash-image-preview"
                gemini_image_size = os.environ.get("GEMINI_IMAGE_SIZE", "512px").strip() or "512px"
                gemini_aspect_ratio = os.environ.get("GEMINI_IMAGE_ASPECT_RATIO", "1:1").strip() or "1:1"
                run_cmd(
                    [
                        sys.executable,
                        "-u",
                        str(ROOT / "generate_idea_images_gemini.py"),
                        "--only-missing",
                        "--model",
                        gemini_model,
                        "--image-size",
                        gemini_image_size,
                        "--aspect-ratio",
                        gemini_aspect_ratio,
                    ],
                    "generate_idea_images_gemini",
                    LOG_FILE,
                )
            else:
                log("[WARN] GEMINI_API_KEY not set; skip Gemini image generation.")
            run_git_sync(LOG_FILE)
        except KeyboardInterrupt:
            log("[INFO] Interrupted by user.")
            return
        except CalledProcessError as e:
            log(f"[ERROR] Command failed: {e}")
        except Exception as e:
            log(f"[ERROR] Unexpected error: {type(e).__name__}: {e}")

    log(f"[END] {datetime.datetime.now():%Y-%m-%d %H:%M:%S}")
    log("==================================================")
    if not args.no_sleep:
        sleep_computer()

if __name__ == "__main__":
    main()
