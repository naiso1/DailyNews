# DailyNews Windows Server deployment

This deployment serves an explicit release package instead of exposing the
repository root. Collection scripts, logs, API keys, and Git metadata are never
reachable from the web server. A same-origin SQLite API stores access counts,
likes, article reads, and comments.

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

The Node.js server listens on `202.15.67.132:8082`. IIS publishes
`https://IEWEB01/` and redirects port 80 to HTTPS. The application and
DailyNews firewall rules allow `172.29.41.0/24` and `202.15.67.0/24`.

Interaction data is stored in `data\dailynews.sqlite`. The
`DailyNewsBackup` task creates a consistent backup every day at 04:30 and
retains 35 days under `data\backups`.

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
- `images/`
- `page_images/`

Each package is stored by Git commit ID and activated through
`active-release.txt`.
