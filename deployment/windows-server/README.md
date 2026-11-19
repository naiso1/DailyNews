# DailyNews Windows Server deployment

This deployment serves an explicit release package instead of exposing the
repository root. Collection scripts, logs, API keys, and Git metadata are never
reachable from the web server. A same-origin SQLite API stores accounts,
persistent sessions, favorites, likes, article reads, comments, comment likes,
user feedback, and mail subscriptions. Passwords are stored as scrypt hashes; plaintext passwords
are never stored.

## Server layout

```text
C:\Users\Administrator\Desktop\DailyNews
  app
  incoming
  releases
  data
  logs
  active-release.txt
```

The Node.js server listens on `202.15.67.132:8082`. The canonical internal URL
is `http://IEWEB01/`. IIS also retains the existing HTTPS binding as an optional
fallback and the personal Copilot sign-in screen uses it. The application and DailyNews
firewall rules allow the internal networks `172.29.0.0/16` and
`202.15.67.0/24`.

Interaction data is stored in `data\dailynews.sqlite`. The
`DailyNewsBackup` task creates a consistent backup every day at 04:30 and
retains 35 days under `data\backups`.

User sessions use an HttpOnly, SameSite cookie and remain valid for up to 180
days. The site is intentionally operated over HTTP to match the existing
internal web environment. Users must not reuse their Windows or other corporate
passwords for this site. Email
addresses are login identifiers and are not displayed with comments; comments
use the user-selected display name.

## Deployment

### Personal Copilot questions (2026-11-19)

The companion UI is the default on the normal interior and exterior URLs.
It uses the same authenticated production question API and the caller's existing
personal Copilot session. The earlier `?copilot=companion` trial links still work;
`?copilot=classic` explicitly selects the previous dialog as a fallback.
Both flags survive news-filter navigation and do not affect the default NEW range.
`dailynews_copilot_companion.js` / `.css` and the shared mascot PNG are explicitly
included in both release packages. Deploy and verify each edition separately.

The companion retains draft text and job IDs in member/edition-scoped
sessionStorage. Answers are loaded from owner-checked jobs, never cached there.
Account changes clear private UI and the previous tab state. Article citations
open an independent preview without modifying the news filters or page scroll.
Follow-up is explicit: the chosen prior question/answer excerpt is added to the
new question within the existing 1000-character limit. It is not a claim to reuse
the provider's conversation session. Source selection and answer bounds remain
server-side. The UI submits once and polls read-only; uncertain POST responses
are recorded before submission and block repeating the same question. No
reconnect, resend, public comment, or email is triggered on page load.

`dailynews_copilot.js` adds a question button to article comments. The API takes
only an article ID and comment ID; the authenticated server supplies their current
published text and the caller's identity. Replies are private and do not modify
comments, likes or rankings. The same member connection serves both editions.

An article comment containing `@Copilot` now triggers that question after the
comment POST succeeds. The POST returns the exact `createdCommentId`; the client
never guesses from the latest comment. The question is a normal public comment
and counts as one; the AI answer stays private. Reading somebody else's mention
does not trigger their account or an automatic question. Existing question buttons
remain available for reconnecting/retrying without posting another comment.

The header's news-question dialog uses POST `/api/copilot/questions` with only
`scope` (`new`, `all`, or `article`), `question` (1–1000 characters) and, only for
`article`, `itemId`. `copilot-context.js` resolves published, visible articles on
the server; clients cannot supply sources or identity. Interior NEW uses the
active release's NEW range and supplements; exterior uses its publication IDs.
Hidden/duplicate articles are excluded. All-news retrieval searches the archive
by question words and topic synonyms, then sends at most 30 matching summaries.
NEW keeps the whole issue instead of requiring question keywords in the articles;
topic scores only prioritize it within the existing 80-summary / 24,000-character
source budget. Analysis requests such as "今日のニュースの考察教えて" therefore reach
Copilot even when no headline contains "考察". Archive search ignores generic
analysis instructions while retaining topic filtering. Generic
personalized requests supply the available NEW news to the member's own Copilot;
no duty/interest questionnaire is required. The model is told not to invent
personal knowledge. Coverage and source links are displayed, and cross-news
answers are capped at 400 characters (article comments remain at 200).
This is a bounded summary search, not an exhaustive market analysis or a full
article crawler. An empty NEW issue or an archive search with no matching topic
does not send a provider request.

Question/edition/issue fingerprints and member-owned durable jobs deduplicate
double clicks and uncertain responses. Changing the issue permits a fresh answer.
The UI saves only a last-job ID in member/edition-scoped sessionStorage; the server
and worker recheck ownership. Updating `copilot-service.js` or the workstation
worker requires a graceful restart of the personal worker when idle. Do not
interrupt a sign-in or question already holding the shared browser lock.

The SYSTEM web process does not run a browser or hold Microsoft sessions.
`copilot-client.js` passes jobs in memory to an authenticated HTTPS worker at
`deployment/workstation/copilot-personal-worker.cjs`. The worker runs
as the signed-in workstation user. `%LOCALAPPDATA%/DailyNewsRuntime/copilot-personal`
holds member-hashed directories, DPAPI CurrentUser-encrypted sessions, account
revisions and durable question records. It never falls back to the image account.
The private `data/copilot-worker.json` contains only the bridge key. The worker
validates IEWEB01 TLS against the shipped certificate and long-polls both editions.
Request/action payloads exist only in memory; result acknowledgements can be
retried but browser actions cannot. Existing SSH forwarding restrictions stay intact.
Do not publish it or put Microsoft authentication material on IEWEB01.

Initial connection uses the page's live Microsoft sign-in view. Credentials
are forwarded only to that member's isolated browser, never saved in files/logs.
Only Microsoft top-level hosts are allowed. The actual Copilot account email must
match DailyNews. The 10-minute view is owner-bound and closes on cancellation.
Saved sessions can still require MFA again.

On 2026-11-17 the user explicitly requested intranet HTTP initial sign-in after
being informed that sign-in inputs/screens would not be encrypted between the
member PC and IEWEB01. This is an application-specific opt-in, not a browser
certificate bypass. With shared identity, the private interior
`data/copilot-connection.json` holds `{ "allowIntranetHttpSignIn": true }` for
both editions. Absent/invalid/false keeps the HTTPS-only default. Restart both
web processes after changing the flag. HTTP sign-in remains restricted to the
existing office networks `202.15.67.0/24`, `172.29.0.0/16` and loopback, even if
the broader site allowlist changes. The HTTP check uses the rightmost client
address appended by the trusted IIS proxy. Same-origin JSON writes, login,
per-member ownership and exact Microsoft account matching remain required.
The `/api/copilot-worker/*` broker still requires HTTPS and its bridge key; the
worker still validates the pinned server certificate. Provider traffic remains
HTTPS. Passwords are not persisted, but DPAPI encryption of stored sessions does
not encrypt the member-to-IEWEB01 HTTP hop. The UI states this distinction.

`/setup/copilot-connection.html` now explains the in-page sign-in steps. No client
EXE, extension, local certificate or Windows trust change is needed in intranet
HTTP mode. The certificate and old installer remain available for optional HTTPS
use; never bypass a certificate warning. To roll back, set the private policy
to false and restart both web tasks. The UI then returns to HTTPS-only connection;
provide the certificate instructions or a trusted certificate before onboarding.

The worker shares the image worker lock. Questions wait up to five minutes;
submitted questions are marked before the click and never auto-resubmitted when
their outcome is unknown. The workstation must remain signed in and awake.
The account manager must close before preparing the composer. Draft text is
checked after the UI settles, ignoring Copilot's zero-width editor markers.
The Lexical composer is explicitly clicked and receives keyboard text insertion;
direct `fill()` could leave its model empty. Pre-send focus failures retry within
the bounded preparation loop, without pressing Enter or clicking Send.
Before focusing the composer, move the pointer off the profile/sidebar area and
press Escape to close the responsive sidebar backdrop. It can reopen after the
account manager closes and intercept all pointer events. Do not force-click
through the backdrop or remove DOM elements.
At most three draft fills are permitted before the first Send click; a lost
draft is not a question resend. `SEND_NOT_READY` has zero send attempts and can
be retried; uncertain clicks remain `needs_review`. `test_copilot_preparation.js`
covers draft reset, marker normalization and a single actual Send.
For `needs_review`, the member can choose "確認して再試行" and confirm one resend.
POST `/api/copilot/jobs/:id/retry` takes the prior `createdAt` as a generation
token. The worker archives the old record under `attempt-history`, validates
member/edition and the current source fingerprint, then starts one new attempt.
Duplicate confirmations with that token return the same attempt; polling and
ordinary submissions never retry an unknown send. A changed issue/comment must
be submitted as a new question. No test comments are posted to the public site.
If it is unavailable the site reports that condition; it does not use another
person's session. Existing private replies can be retrieved when it reconnects.

Validation: `node deployment/windows-server/test_copilot.js` (isolated real
HTTP/SQLite routes and a simulated provider; no real question sends).
`test_copilot_context.js` verifies NEW/supplement/selection matching, retrieval
and prompt bounds. `tests/verify_copilot_questions_ui.py` checks actual UI with
fixture accounts, questions and comments, without production writes.
`test_copilot_http.js` verifies the opt-in on both editions, network bounds,
connection ownership, origin checks and HTTPS-only worker routes with mock sign-in.

Workstation autostart: `deployment/workstation/install-copilot-personal.ps1`
registers `DailyNewsCopilotPersonal` for the current user's interactive logon,
with no stored Windows password and a hidden launcher. The private loopback
worker endpoint accepts only the bridge key, and normal UI cannot call it.
`connection-status.json` reports connectivity without recording credentials.

Run from the repository root on the DailyNews workstation:

```powershell
powershell -ExecutionPolicy Bypass -File .\deployment\windows-server\deploy.ps1
```

The script packages only:

- `内装製品デイリーニュース.html`
- `header-layout-test.html`
- `activity-preview.html`
- `source-list-preview.html`
- `currency-conversion-preview.html`
- `exchange_rates.js` (dated ECB reference rates, refreshed once per collection day)
- `dailynews_annotations.js` (currency conversion and verified source links)
- `dailynews_exterior_tags.js` and `dailynews_event_tags.js` (shared genre/event rules)
- `news_data.js`
- `insights_data.js`
- `dailynews_client.js`
- `dailynews_header.js` / `dailynews_header.css` (shared visual header; classic fallback)
- `dailynews_account.js`
- `dailynews_reports.js` (administrator-only group report UI; no roster data)
- `release_history.js`
- `setup/` (IEWEB01 certificate and per-user trust installer)
- `images/`
- `page_images/`

Each package is stored by Git commit ID and activated through
`active-release.txt`.

Normal deployments restart the existing server task through Task Scheduler COM;
they do not re-register the task or IIS application. This avoids the CIM provider
stall that left the exterior publication status `running` on 2026-10-19 after
content activation. Remote prepare/activate/restart operations run in a bounded
job (180 seconds each); a timeout or child error fails deployment and cannot mark
the notification feed successful. Health must report the expected release.
For a first exterior installation or an intentional infrastructure reconfiguration,
use `deploy-exterior.ps1 -InstallServer`. Ordinary daily publication uses
`deploy.ps1 -Edition exterior`. Do not use installation as a routine update step.

Static HTML, JavaScript, CSS and data use private browser caches with ETag
revalidation on each request. Text assets are gzip-compressed when supported;
compressed representations are held in a bounded 32 MB server cache. API and
account responses remain `no-store`, and authentication is checked before any
protected static response, including 304 responses. Data script URLs stay stable
so unchanged archives are reused. A new release changes ETags immediately.

The shared title background is `page_images/header_automotive_20261016.webp`
(the original PNG remains available for rollback).
It is a fixed generated asset, packaged for both editions; no scheduled image
generation is involved. See [header rollback](header-rollback.md) to switch
back to the previous header while preserving newer articles and interaction data.

The temporary 2026-11-13 update-delay notice is in `dailynews_header.js` and
`dailynews_header.css`. Both packages include the small, transparent generated
illustration `page_images/update_delay_worker_20261113.png`. It disappears on
page load once that edition has published both news and insights for 2026-11-12
or later. A UI-only deployment does not dismiss it. Exterior uses its own
publication status; the notice does not modify or restart the daily pipeline.

News image sizing is display-only and shared by both editions. For verified
Hearst (`hips.hearstapps.com/hmg-prod/images/`), TopSpeed/CarBuzz (`static0.*images.com/wordpress/wp-content/uploads/`),
and PR TIMES (`prcdn.freetls.fastly.net/release_image/`) raster URLs, the client
requests a publisher-hosted variant up to 980 pixels wide, retaining crop and
aspect ratio settings. Smaller variants, signed URLs, unknown hosts and local
generated images are kept intact. Stored article/override URLs are never
rewritten. Image bytes are fetched by the browser from the publisher; this sizing
does not download or cache images on the DailyNews server. Each image retries its
original URL once if the display variant fails, before the normal missing-image
handling. Existing Autocar/Auto Express RSS thumbnail rules remain in use.

Article image overrides support 1–5 ordered HTTP/HTTPS URLs. The legacy
`image_url` column and `imageUrlOverride` response keep the first image for
compatibility; `image_urls` and `imageUrlsOverride` store the gallery.
Authenticated users can PUT/DELETE `/api/items/:id/image` to edit/reset images;
the prior `/api/admin/items/:id/image` remains administrator-only for cached
clients. URL validation, same-origin checks and the last editor's user ID apply
to both routes. Anonymous writes are rejected.
Multi-image cards use in-image dot controls. Mouse hover rotates every 3 seconds;
leaving the card, text input, inactive windows/tabs and reduced-motion preference
stop rotation. Touch and keyboard controls select images manually. Card rebuilds
dispose timers/listeners and retain the selected image when it still exists.
`user_article_reads` records authenticated article clicks once per user/article/JST
day. Historical anonymous read counters are not reassigned to users.
The private `data/weekly-reports.json` is served only through the administrator
API. See [weekly report operations](../weekly-report/README.md) for roster
snapshots, collection tasks, scheduling and duplicate-send protection.

User-facing changes must add a short Japanese entry to `release_history.js`
in the same change (see the root `AGENTS.md`). Include changes to selection,
generation and publication behavior as well as UI changes. This list is manually
maintained; commits and successful deployments do not populate it automatically.
After deployment, open the header's update-history button and verify the latest
date and text at desktop and mobile widths. Routine daily article additions do
not require a feature-history entry and must not be blocked by its date.

System notices dated 2026-10-07 or later open automatically only when unread.
Closing the dialog acknowledges the displayed entries. Each entry uses a content
fingerprint, so a second update or correction on the same date is detected.
The manual header button still shows the full archive.

`GET/PUT /api/me/release-history` stores acknowledged entry keys in
`release_history_seen`, attached to the authenticated account. With shared
identity the interior identity database owns this state for both editions;
article reads, likes and usage remain edition-specific. The PUT request includes
the expected identity ID to reject acknowledgements from a stale account tab.
Browser localStorage provides an account-specific offline cache and a separate
guest record. Guest records are never imported into a signed-in account.
Automatic notices wait for authentication, other dialogs and unfinished input.

The administrator account list is configured with the
`DAILYNEWS_ADMIN_EMAILS` environment variable (comma-separated). If it is not
set, `yuki.nakamura@toyoda-gosei.co.jp` is treated as the administrator.
Additional administrators can be listed as a JSON array of exact email addresses
in each server's private `data/admin-emails.json`. This file adds to the existing
administrator list and survives deployments. With shared identity, keep the same
list in both edition roots and restart both servers, starting with interior.
Existing accounts are promoted at startup; unregistered addresses become
administrators when they register. Existing administrator flags are retained;
removing an address from this file alone does not revoke an existing account's
administrator flag. This configuration must never be committed or included in a
public release, and changing it does not change mail subscriptions.
The administrator panel manages the 08:00 mail recipients. Registered users are
subscribed automatically; manual recipients can be added, disabled, or removed.
The recipient list remains in SQLite and is exported to the signed-in business
OneDrive by `ニュース収集/run_search_and_update.py`; it is never published with
the public release.

Since 2026-11-04, `roster-mailing-list.js` adds missing recipients from the latest
validated employee master to their room's edition before export. Existing disabled
choices are preserved. The private `roster_mail_enrollment` ledger prevents
re-adding a recipient deleted after import; `roster_mail_state` guards against
older or substantially changed masters. Neither table is served by the web API.
This does not create accounts, administrator permissions, or weekly report recipients.
