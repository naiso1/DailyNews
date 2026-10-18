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
fallback, but the application does not direct users to it. The application and DailyNews
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

The shared title background is `page_images/header_automotive_20261016.png`.
It is a fixed generated asset, packaged for both editions; no scheduled image
generation is involved. See [header rollback](header-rollback.md) to switch
back to the previous header while preserving newer articles and interaction data.

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
