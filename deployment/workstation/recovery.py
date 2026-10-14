"""Read-only completion checks and bounded recovery planning for signed-in users."""
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request

JST = dt.timezone(dt.timedelta(hours=9))


def running_pipeline_pids(root):
    # Task Scheduler can terminate a launcher while a child is still finishing.
    # Check for those children as well as run.lock before recovering anything.
    escaped = str(root).replace("'", "''")
    script = "$ErrorActionPreference='Stop';$p=@(Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^pythonw?\\.exe$' -and $_.CommandLine -like '*" + escaped + "*' -and $_.CommandLine -match '(run_search_and_update|google_search_script|auto_update_daily_news)\\.py' });ConvertTo-Json -Compress -InputObject @($p.ProcessId)"
    result = subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],
                            capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=30,
                            creationflags=subprocess.CREATE_NO_WINDOW,check=True)
    return json.loads(result.stdout)


def pending_editions(root, editions, today=None, fetch=None):
    today = today or dt.datetime.now(JST).date()
    if today.weekday() >= 5:
        return []
    expected = (today - dt.timedelta(days=1)).isoformat()
    if fetch is None:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        def fetch(url):
            with opener.open(url, timeout=15) as response:
                return response.read()
    pending = []
    for edition in editions:
        if edition not in {'interior', 'exterior'}:
            raise ValueError('Unknown edition')
        work = root/'ニュース収集' if edition == 'interior' else root/'runtime/exterior'
        content = root if edition == 'interior' else root/'content/exterior'
        base = 'http://IEWEB01/' + ('exterior/' if edition == 'exterior' else '')
        try:
            status = json.loads((work/'logs/latest_run_status.json').read_text(encoding='utf-8-sig'))
            published = dt.date.fromisoformat(status.get('published_news_date', ''))
            if status.get('edition_id') != edition or status.get('status') != 'success' or published.isoformat() < expected:
                pending.append(edition)
                continue
            health = json.loads(fetch(base+'health'))
            if health.get('status') != 'ok':
                raise ValueError('Unhealthy publication')
            # UI-only releases may change the release ID after a successful run.
            # Compare article/insight data instead, so they do not trigger a rerun.
            for name in ('news_data.js', 'insights_data.js'):
                if hashlib.sha256(fetch(base+name)).digest() != hashlib.sha256((content/name).read_bytes()).digest():
                    raise ValueError('Publication content differs')
            if edition == 'exterior':
                remote = json.loads(fetch(base+'publication_status.json'))
                if remote.get('edition_id') != edition or remote.get('processed_through', '') < expected:
                    raise ValueError('Exterior issue is stale')
        except (OSError, ValueError, TypeError, KeyError):
            pending.append(edition)
    return pending


def reserve_attempt(path, editions, today=None, limit=2):
    """Called only while run.lock is held; never spend a retry on a busy process."""
    day = (today or dt.datetime.now(JST).date()).isoformat()
    try:
        state = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        state = {}
    if state.get('date') != day:
        state = {'date': day, 'attempts': {}}
    attempts = state.setdefault('attempts', {})
    selected = [edition for edition in editions if int(attempts.get(edition, 0)) < limit]
    for edition in selected:
        attempts[edition] = int(attempts.get(edition, 0)) + 1
    if selected:
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(state, indent=2), encoding='utf-8')
        temporary.replace(path)
    return selected
