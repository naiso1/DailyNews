# DailyNews Windows Server deployment

This deployment serves an explicit release package instead of exposing the
repository root. Collection scripts, logs, API keys, and Git metadata are never
reachable from the web server.

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

The Node.js server listens on `202.15.67.132:8082`. Initially, both the
application and Windows Firewall only allow the DailyNews workstation at
`172.29.41.49`.

## Deployment

Run from the repository root on the DailyNews workstation:

```powershell
powershell -ExecutionPolicy Bypass -File .\deployment\windows-server\deploy.ps1
```

The script packages only:

- `内装製品デイリーニュース.html`
- `news_data.js`
- `insights_data.js`
- `images/`
- `page_images/`

Each package is stored by Git commit ID and activated through
`active-release.txt`.
