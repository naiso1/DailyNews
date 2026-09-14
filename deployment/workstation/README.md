# Processing workstation

The production web server stays on IEWEB01. Only collection/AI/publishing move
to DESKTOP-97FRPLP, under the Owner account.

## Runtime and schedule

- Repository: `C:\Users\Owner\Desktop\DailyNews`
- Python: `%LOCALAPPDATA%\DailyNewsRuntime\venv\Scripts\pythonw.exe`
- Action: `-B C:\Users\Owner\Desktop\DailyNews\deployment\workstation\run.py`
- Weekdays at 00:00 JST. Task: `DailyNews_RunSearchAndUpdate`.
- Owner must remain signed in. Locking the screen is OK; signing out is not.
  After a reboot, sign in as Owner. This is not a logged-off service.
- Overlapping invocations are rejected by Task Scheduler and a process lock.
- Keep Qwen3.5 9B, context 8192, parallel 1. The launcher starts LM Studio's
  daemon; the collector prepares the requested model without overlapping loads.
- No post-run sleep. Sleep is inhibited during the process only.
- Gemini image generation remains Standard 512px / 1:1.
- OneDrive starts in Owner's session. Existing Power Automate weekday 08:00
  success/failure delivery and mailing-list management stay unchanged.

## Private configuration

`%LOCALAPPDATA%\DailyNewsRuntime\workstation.json` contains `hostname`,
`repository`, `oneDriveAccount`, and boolean `enabled`. It contains no API key.
The Gemini API key comes from Owner's User environment. Proxy settings apply
only to the launcher and its children; other applications are not reconfigured.

`run.py --check-only` verifies SSH, a read-only recipient export, server health,
native LM Studio model state and a GitHub push dry run. It does NOT collect,
generate images, publish content/status, change the mailing list or send mail.
It records `%LOCALAPPDATA%\DailyNewsRuntime\preflight-result.json`.

Logs: `%LOCALAPPDATA%\DailyNewsRuntime\logs` plus the repository's collection
`logs` folder. Check the dated status as well as exit codes. One passed smoke
test does not guarantee every future article will translate successfully.

## Rollback

Disable the NEW task first and wait for any running pipeline to stop safely.
Set the new private configuration's `enabled` to false. Bring the OLD
repository up to date (including generated content and status) before enabling
its task again. Never enable both schedules. Keep the original machine and
migration archives until the first scheduled production run has been verified.

Do not run `google_search_script.py --help` for inspection: it has historical
top-level collection side effects. Use AST-based tests instead.
