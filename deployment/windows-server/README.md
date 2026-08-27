# DailyNews Windows Server deployment

This deployment serves an explicit release package instead of exposing the
repository root. Collection scripts, logs, API keys, and Git metadata are never
reachable from the web server. A same-origin SQLite API stores accounts,
persistent sessions, favorites, likes, article reads, comments, comment likes,
and user feedback. Passwords are stored as scrypt hashes; plaintext passwords
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

The Node.js server listens on `202.15.67.132:8082`. IIS publishes both
`http://IEWEB01/` and `https://IEWEB01/`. The application and DailyNews
firewall rules allow the internal networks `172.29.0.0/16` and
`202.15.67.0/24`.

Interaction data is stored in `data\dailynews.sqlite`. The
`DailyNewsBackup` task creates a consistent backup every day at 04:30 and
retains 35 days under `data\backups`.

User sessions use an HttpOnly, SameSite cookie and remain valid for up to 180
days. Use the IIS HTTPS endpoint whenever credentials are entered. Email
addresses are login identifiers and are not displayed with comments; comments
use the user-selected display name.

## Deployment

Run from the repository root on the DailyNews workstation:

```powershell
powershell -ExecutionPolicy Bypass -File .\deployment\windows-server\deploy.ps1
```

The script packages only:

- `内装製品デイリーニュース.html`
- `news_data.js`
- `insights_data.js`
- `dailynews_client.js`
- `dailynews_account.js`
- `images/`
- `page_images/`

Each package is stored by Git commit ID and activated through
`active-release.txt`.
