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
- `news_data.js`
- `insights_data.js`
- `dailynews_client.js`
- `dailynews_account.js`
- `release_history.js`
- `setup/` (IEWEB01 certificate and per-user trust installer)
- `images/`
- `page_images/`

Each package is stored by Git commit ID and activated through
`active-release.txt`.

Functional UI changes should also add a short entry to `release_history.js`
so users can see what changed from the header's update-history button.

The administrator account list is configured with the
`DAILYNEWS_ADMIN_EMAILS` environment variable (comma-separated). If it is not
set, `yuki.nakamura@toyoda-gosei.co.jp` is treated as the administrator.
The administrator panel manages the 08:00 mail recipients. Registered users are
subscribed automatically; manual recipients can be added, disabled, or removed.
The recipient list remains in SQLite and is exported to the signed-in business
OneDrive by `ニュース収集/run_search_and_update.py`; it is never published with
the public release.
