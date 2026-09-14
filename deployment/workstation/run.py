"""Launch the migrated collector in the signed-in workstation user's session."""
import argparse
import ctypes
import datetime as dt
import json
import msvcrt
import os
from pathlib import Path
import subprocess
import sys
import urllib.request
import winreg


ROOT = Path(__file__).resolve().parents[2]
RUNTIME = Path(os.environ["LOCALAPPDATA"]) / "DailyNewsRuntime"


def command(args, timeout=60):
    result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=timeout,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        # Do not copy credential/provider responses into public status feeds.
        raise RuntimeError(f"{Path(str(args[0])).name} failed (exit {result.returncode})")
    return result.stdout


def prepare(config):
    if os.environ.get("COMPUTERNAME", "").casefold() != config["hostname"].casefold():
        raise RuntimeError("This workstation is not the configured processing host")
    if ROOT != Path(config["repository"]).resolve():
        raise RuntimeError("Unexpected repository location")
    # Task Scheduler can inherit an environment older than the User settings.
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
        for name in ("GEMINI_API_KEY", "NEWSAPI_KEY", "LM_API_TOKEN"):
            try:
                os.environ[name] = str(winreg.QueryValueEx(key, name)[0])
            except FileNotFoundError:
                pass
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        os.environ.pop(name, None)
    proxies = {k: v for k, v in urllib.request.getproxies_registry().items() if k in ("http", "https")}
    for name, value in proxies.items():
        os.environ[name.upper() + "_PROXY"] = value
    os.environ.update(
        NO_PROXY="localhost,127.0.0.1,::1,IEWEB01,ieweb01,202.15.67.132",
        no_proxy="localhost,127.0.0.1,::1,IEWEB01,ieweb01,202.15.67.132",
        LLM_ENDPOINT="http://127.0.0.1:1234/v1/chat/completions",
        LLM_MODEL="qwen/qwen3.5-9b", LLM_CONTEXT_LENGTH="8192", LLM_PARALLEL="1",
        LLM_TTL_SECONDS="900", LLM_REASONING_EFFORT="none", USE_LLM="1",
        GEMINI_IMAGE_MODEL="gemini-3.1-flash-image-preview", GEMINI_IMAGE_SIZE="512px",
        GEMINI_IMAGE_ASPECT_RATIO="1:1", GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="Never",
        PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1",
        PLAYWRIGHT_BROWSERS_PATH=str(RUNTIME / "browsers"), AUTO_GIT_SYNC="1", AUTO_SERVER_DEPLOY="1")
    for name in ("TARGET_DATES", "ONLY_PAPERS_RSS", "DAILYNEWS_POWER_AUTOMATE_STATUS",
                 "DAILYNEWS_POWER_AUTOMATE_MAILING_LIST"):
        os.environ.pop(name, None)
    os.environ["PATH"] = str(RUNTIME / "venv/Scripts") + os.pathsep + os.environ["PATH"]
    if not os.environ.get("GEMINI_API_KEY", "").strip():
        raise RuntimeError("GEMINI_API_KEY is missing for this Windows user")
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\OneDrive\Accounts\Business1") as key:
        account = str(winreg.QueryValueEx(key, "UserEmail")[0]).casefold()
        folder = Path(winreg.QueryValueEx(key, "UserFolder")[0])
    if account != config["oneDriveAccount"].casefold() or not folder.is_dir():
        raise RuntimeError("The expected business OneDrive account is unavailable")
    ps = r"""
$ErrorActionPreference = 'Stop'
if (!(Get-Process -Name OneDrive -ErrorAction SilentlyContinue)) {
    $exe = @("$env:LOCALAPPDATA\Microsoft\OneDrive\OneDrive.exe", "$env:ProgramFiles\Microsoft OneDrive\OneDrive.exe") |
        Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if (!$exe) { throw 'OneDrive executable is missing' }
    Start-Process -FilePath $exe -ArgumentList '/background' -WindowStyle Hidden
}
"""
    command(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps])
    return proxies


def check(config, proxies):
    identity = Path.home() / ".ssh/dailynews_ieweb01"
    if not identity.is_file():
        raise RuntimeError("Web-server deployment key is missing")
    ssh = ["ssh", "-i", str(identity), "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
           "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=15", "Administrator@IEWEB01"]
    host = command(ssh + ["hostname"]).strip()
    if host.upper() != "IEWEB01":
        raise RuntimeError("Unexpected deployment server")
    recipients = json.loads(command(ssh + [
        'node "C:/Users/Administrator/Desktop/DailyNews/app/manage-mailing-list.js" export-json']))
    count = int(recipients.get("recipientCount", 0))
    if count <= 0 or not recipients.get("to"):
        raise RuntimeError("No mail recipients exported by the server")
    command(["git", "-c", "credential.interactive=false", "-c",
             "http.proxy=" + proxies.get("https", proxies.get("http", "")), "push", "--dry-run",
             "https://github.com/naiso1/DailyNews.git", "HEAD:refs/heads/main"])
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open("http://IEWEB01:8082/health", timeout=10) as response:
        health = json.load(response)
    if health.get("status") != "ok":
        raise RuntimeError("Production server health check failed")
    command([str(Path.home() / ".lmstudio/bin/lms.exe"), "daemon", "up"], timeout=90)
    collection = next(ROOT.glob("*/run_search_and_update.py")).parent
    sys.path.insert(0, str(collection))
    from lm_studio_state import loaded_model_ids
    loaded = loaded_model_ids("http://127.0.0.1:1234")
    return {"hostname": host, "mailRecipientCount": count, "release": health.get("release"),
            "loadedModels": sorted(loaded), "githubPushDryRun": "passed",
            "checkedAt": dt.datetime.now().astimezone().isoformat(), "productionFilesChanged": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    config = json.loads((RUNTIME / "workstation.json").read_text(encoding="utf-8-sig"))
    if not args.check_only and not config.get("enabled"):
        raise RuntimeError("Migration has not been activated")
    lock = (RUNTIME / "run.lock").open("a+b")
    lock.seek(0, 2)
    if lock.tell() == 0:
        lock.write(b"0")
        lock.flush()
    lock.seek(0)
    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    try:
        proxies = prepare(config)
        if args.check_only:
            result = check(config, proxies)
            (RUNTIME / "preflight-result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
            print(json.dumps(result), flush=True)
            return 0
        # Prevent sleep for this run only; leave system-wide power policy alone.
        if not ctypes.windll.kernel32.SetThreadExecutionState(0x80000001):
            raise RuntimeError("Could not prevent sleep during the scheduled run")
        lms = Path.home() / ".lmstudio/bin/lms.exe"
        if not lms.exists():
            raise RuntimeError("LM Studio CLI is missing")
        command([str(lms), "daemon", "up"], timeout=90)
        script = next(ROOT.glob("*/run_search_and_update.py"))
        result = subprocess.run([sys.executable.replace("pythonw.exe", "python.exe"), "-B", "-u", str(script)],
                                cwd=script.parent, stdout=sys.stdout, stderr=sys.stderr,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        return result.returncode
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        lock.close()


if __name__ == "__main__":
    logs = RUNTIME / "logs"
    logs.mkdir(exist_ok=True)
    log = (logs / ("launcher_" + dt.date.today().isoformat() + ".log")).open("a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = log
    print("START", dt.datetime.now().astimezone().isoformat(), flush=True)
    try:
        code = main()
    except Exception:
        import traceback
        traceback.print_exc()
        code = 1
    print("END exit=" + str(code), flush=True)
    log.close()
    raise SystemExit(code)
