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
- `DailyNews_ResumeAfterSignIn` checks two minutes after sign-in and every 30
  minutes while signed in. It uses `run.py --recover-if-needed`, the same process
  lock, weekday/holiday policy and saved model settings. It skips an active run
  and verifies published article/insight data before skipping completed editions.
  Recovery is limited to two attempts per edition/JST day; it never directly
  sends mail or opens a sign-in dialog. Install with `install-recovery.ps1`.
  A surviving collector/updater child also blocks recovery. The recovery task
  allows 12 hours. The installer tries to extend the nightly task's 7-hour limit
  too; if that protected task denies the change, it is left intact and a warning
  is logged. Recovery never treats a surviving child as a failed, stopped run.
  A reboot still requires Windows sign-in, and expired exaBase authentication
  may require the user's identity verification. No password is saved for auto-login.
- Overlapping invocations are rejected by Task Scheduler and a process lock.
- `processing_host.json` selects the sole active processing host. The scheduled
  runner checks this before log/status writes, network requests or subprocesses.
  On other hosts it exits without collecting, publishing or touching mail status.
  Missing/malformed policy fails closed. `run_search_and_update.py
  --check-processing-host` prints the decision and exits without running a pipeline.
- Model comes from the private `llmModel` setting; context 8192, parallel 1.
  Optional `gpuOffload` controls the GPU layer ratio (for example `0.7`),
  leaving room for context and vision on a 16 GiB GPU. No value means automatic.
  The launcher starts LM Studio's
  daemon; the collector prepares the requested model without overlapping loads.
- No post-run sleep. Sleep is inhibited during the process only.
- Gemini image generation remains Standard 512px / 1:1.
- OneDrive starts in Owner's session. Existing Power Automate weekday 08:00
  success/failure delivery and mailing-list management stay unchanged.
- `DailyNews_ExaBaseSessionMaintenance` checks and refreshes exaBase authentication
  at :10 and :40 while the user is signed in and the workstation is awake. It skips
  while the news pipeline holds `run.lock` and does not generate images or send mail.
  See [exaBase authentication maintenance](exabase/README.md#30分ごとの認証確認).

## Private configuration

For a one-time model comparison, use `run.py --llm-model MODEL` and optionally
`--gpu-offload RATIO`. These apply only to that process and its two edition
children; `workstation.json` and the next scheduled run remain unchanged.
An explicit model also overrides the department idea-generation/review model
through `DAILYNEWS_IDEA_MODEL`, avoiding a second model being loaded mid-run.

`%LOCALAPPDATA%\DailyNewsRuntime\workstation.json` contains `hostname`,
`repository`, `oneDriveAccount`, boolean `enabled`, optional `llmModel` and
`gpuOffload`. Without a model override the fallback remains Qwen3.5 9B.
Qwen3.8-27B also needs its matching mmproj GGUF for image input; validate both
text and vision after any model change. The configuration contains no API key.
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
its processing again. Change `processing_host.json` to the OLD hostname on both
copies only after NEW is stopped. The OLD task may still be enabled in Windows
when its protected task settings cannot be edited; the host policy then makes
it a no-op. Do not describe this as a disabled Windows task. Keep the original machine and
migration archives until the first scheduled production run has been verified.

Do not run `google_search_script.py --help` for inspection: it has historical
top-level collection side effects. Use AST-based tests instead.
