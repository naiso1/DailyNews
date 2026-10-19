"""Private roster snapshots, edition-aware usage reports and a guarded mail packet.

Named reports are private to administrators. SSH extraction returns hashed emails.
The previous complete week is frozen once; later roster updates cannot alter it.
"""
from __future__ import annotations
import argparse, base64, csv, hashlib, html, json, os, re, subprocess, unicodedata, uuid
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from room_reports import build_rooms, email_html, chart
from identity_matching import load_aliases, match_source
from delivery import TEST_TO, recipient_to

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / 'runtime' / 'weekly-report'
MASTER_ROOT = Path(r'\\tgfs1\ＩＥ開発部\90_その他\フロアー改革\電子掲示板')
JST = timezone(timedelta(hours=9))
LABELS = {'interior': '内装版', 'exterior': '外装版', 'combined': '両版合計'}

def normalized(value): return unicodedata.normalize('NFKC', value).strip().lower()
def identity(value): return hashlib.sha256(normalized(value).encode()).hexdigest()
def atomic_json(file, value):
    file.parent.mkdir(parents=True, exist_ok=True)
    temp = file.with_name(file.name + '.' + uuid.uuid4().hex + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf8')
    os.replace(temp, file)

def select_master(root, effective):
    candidates = []
    for file in root.glob('*/社員マスタ_*.csv'):
        match = re.fullmatch(r'社員マスタ_(\d{8})\.csv', file.name)
        if match:
            stamp = datetime.strptime(match[1], '%Y%m%d').date()
            if stamp <= effective: candidates.append((stamp, file))
    if not candidates: raise ValueError('対象日以前の社員マスタがありません。')
    stamp = max(row[0] for row in candidates)
    newest = [file for day, file in candidates if day == stamp]
    if len({hashlib.sha256(file.read_bytes()).hexdigest() for file in newest}) != 1:
        raise ValueError('同じ日付の社員マスタの内容が異なります。')
    file = sorted(newest)[0]
    with file.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        if not {'社員コード','メールアドレス','見出し名'}.issubset(reader.fieldnames or []): raise ValueError('社員マスタの必須列がありません。')
        rows = list(reader)
    members, codes = {}, set()
    for row in rows:
        email, code = normalized(row['メールアドレス']), row['社員コード'].strip()
        group = ' '.join(unicodedata.normalize('NFKC', row['見出し名']).split())
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email) or not code or not group: raise ValueError('名簿の必須値が不正です。')
        key = identity(email)
        if key in members or code in codes: raise ValueError('名簿に重複があります。')
        room = '内装開発室' if group.startswith('内装開発室') else '外装開発室' if group.startswith('外装開発室') else 'IE開発部（室外）'
        members[key] = {'group': group, 'room': room, 'name': ' '.join(row.get('氏名','').split())}; codes.add(code)
    if not members: raise ValueError('社員マスタが空です。')
    return {'masterDate': stamp.isoformat(), 'masterName': file.name,
            'masterHash': hashlib.sha256(file.read_bytes()).hexdigest(), 'members': members}

def week_start(day): return day - timedelta(days=day.weekday())

def named_roster(roster, root):
    if all(m.get('name') for m in roster['members'].values()): return roster
    # Existing snapshots kept hashes/affiliations only. Resolve names exclusively
    # from that same master, so later transfers never change historical membership.
    original = select_master(root, date.fromisoformat(roster['masterDate']))
    if original['masterHash'] != roster['masterHash'] or set(original['members']) != set(roster['members']):
        raise ValueError('保存済み名簿と同一の社員マスタを確認できません。氏名の推測は行いません。')
    if any(not m.get('name') for m in original['members'].values()):
        raise ValueError('社員マスタに氏名がありません。')
    if any(original['members'][k]['group'] != m['group'] for k,m in roster['members'].items()):
        raise ValueError('保存済み名簿の所属と一致しません。')
    return original
def validate_roster_change(roster, previous):
    if previous:
        before, after = len(previous['members']), len(roster['members'])
        if abs(after-before) > max(5,before*0.2):
            raise ValueError('名簿人数が前回より大幅に変わっています。前回のレポートを保持しました。新名簿の対象範囲を確認してください。')
def stamp_day(stamp):
    if not stamp: return None
    return (datetime.fromisoformat(stamp.replace('Z', '+00:00')).replace(tzinfo=timezone.utc).astimezone(JST)).date().isoformat()

def build_report(start, end, roster, source, now):
    members = roster['members']
    # Registration is owned by the shared interior identity DB, not lazy exterior accounts.
    registered = {row['key'] for row in source['interior']['accounts'] if stamp_day(row['createdAt']) <= end.isoformat()}
    rows = []
    scopes = [('all', 'IE開発部 全体', set(members))]
    for room in sorted({m['room'] for m in members.values()}): scopes.append(('room', room, {k for k,m in members.items() if m['room']==room}))
    for group in sorted({m['group'] for m in members.values()}): scopes.append(('group', group, {k for k,m in members.items() if m['group']==group}))
    def in_week(r): return start.isoformat() <= r['date_key'] <= end.isoformat()
    by_edition = {}
    for edition, data in source.items():
        by_edition[edition] = {metric: [r for r in data[metric] if in_week(r)] for metric in ('usage','reads','likes','comments')}
    by_edition['combined'] = {metric: sum((by_edition[e][metric] for e in ('interior','exterior')), []) for metric in ('usage','reads','likes','comments')}
    def metrics(data, keys):
        active = {r['key'] for metric in data.values() for r in metric if r['key'] in keys}
        result = {'active': len(active)}
        for metric in ('reads','likes','comments'):
            matched = [r for r in data[metric] if r['key'] in keys]
            result[metric] = sum(r['count'] for r in matched)
            result[metric+'Users'] = len({r['key'] for r in matched})
        return result
    for level, name, keys in scopes:
        row = {'level':level,'name':name,'headcount':len(keys),'registered':len(keys & registered),'editions':{}}
        for edition,data in by_edition.items(): row['editions'][edition] = metrics(data, keys)
        rows.append(row)
    unmatched = {}
    for edition, data in by_edition.items():
        outside = {r['key'] for metric in data.values() for r in metric if r['key'] and r['key'] not in members}
        unmatched[edition] = metrics(data, outside)
        unmatched[edition]['unattributedComments'] = sum(r['count'] for r in data['comments'] if not r['key'])
    coverage = {}
    for edition,data in source.items():
        first = stamp_day(data['readsStarted'])
        coverage[edition] = {'readsStarted': first, 'readsComplete': bool(first and first < start.isoformat()),
                             'usageStarted': stamp_day(data['usageStarted']),
                             'browserVisits':sum(r['visit_count'] for r in data['access'] if in_week(r))}
    return {'week':start.isoformat(), 'end':end.isoformat(), 'generatedAt':now.isoformat(),
        'complete':end < now.date(), 'masterDate':roster['masterDate'], 'masterName':roster['masterName'],
        'rows':rows,'unmatched':unmatched,'coverage':coverage,
        'notes': ['利用率＝期間内の利用人数÷名簿人数。両版の利用人数は同じ人を1人として集計。管理者も含みます。',
          '閲覧＝「記事を読む」のクリック。同じ人・同じ記事・同じ日は1回（両版は別記事扱い）。ログインした利用者が対象です。',
          'いいね・コメントは対象週に作成され、集計時点で残っている件数。取消・削除済みは含みません。',
          '所属は週の名簿スナップショット。初回作成時点で参照できる対象週末以前の最新名簿を使用します。',
          '名簿にない利用者は別枠。未ログインのアクセスはグループ・人数へ割り当てません。']}

def ssh(script):
    encoded = base64.b64encode(script.encode('utf-16le')).decode()
    result = subprocess.run(['ssh','-i',str(Path.home()/'.ssh/dailynews_ieweb01'),'-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','Administrator@IEWEB01','powershell.exe -NoProfile -NonInteractive -EncodedCommand '+encoded], capture_output=True,text=True,encoding='utf8',errors='replace',timeout=75,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode: raise RuntimeError('サーバー処理に失敗しました: '+result.stderr[-800:])
    return result.stdout.lstrip('\ufeff')

def upload(file, name):
    result=subprocess.run(['scp','-i',str(Path.home()/'.ssh/dailynews_ieweb01'),'-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',str(file),'Administrator@IEWEB01:C:/Users/Administrator/Desktop/DailyNews/incoming/'+name],capture_output=True,timeout=75,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode: raise RuntimeError('集計ファイルの転送に失敗しました。')

def extract_usage():
    upload(Path(__file__).with_name('export-usage.cjs'),'weekly-export.cjs')
    return json.loads(ssh("$ErrorActionPreference='Stop';[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false); & 'C:/Program Files/nodejs/node.exe' 'C:/Users/Administrator/Desktop/DailyNews/incoming/weekly-export.cjs';if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}"))

def read_label(report, edition, value):
    editions = ('interior','exterior') if edition == 'combined' else (edition,)
    coverage = [report['coverage'][e] for e in editions]
    if all(not x['readsStarted'] or x['readsStarted'] > report['end'] for x in coverage): return '計測前'
    return str(value) + ('' if all(x['readsComplete'] for x in coverage) else '（計測開始後）')

def group_label(row):
    return row['name'] + ('（グループ記載なし）' if row['level']=='group' and row['name'] in ('内装開発室','外装開発室','IE開発部') else '')

def publish(reports):
    file=STATE/'reports.json';atomic_json(file,{'reports':reports});upload(file,'weekly-reports.json')
    script="$ErrorActionPreference='Stop';$bytes=[IO.File]::ReadAllBytes('C:/Users/Administrator/Desktop/DailyNews/incoming/weekly-reports.json');foreach($folder in @('DailyNews','DailyNewsExterior')){$target='C:/Users/Administrator/Desktop/'+$folder+'/data/weekly-reports.json';$temp=$target+'.tmp';[IO.File]::WriteAllBytes($temp,$bytes);Move-Item -LiteralPath $temp -Destination $target -Force};'published'"
    ssh(script)

def onedrive_folder():
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\OneDrive\Accounts\Business1') as key:
        return Path(winreg.QueryValueEx(key,'UserFolder')[0])/'DailyNewsAutomation'/'weekly-report'

def run(args):
    weekly_to = recipient_to()
    now=datetime.now(JST); today=now.date(); current=week_start(today)
    STATE.mkdir(parents=True,exist_ok=True)
    # Single local producer; do not overlap startup and daily scheduled tasks.
    import msvcrt
    with (STATE/'producer.lock').open('a+b') as lock:
        lock.seek(0); lock.write(b'0'); lock.flush(); lock.seek(0)
        try: msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError: raise RuntimeError('レポートの作成処理が既に実行中です。')
        aliases=load_aliases(STATE/'identity-aliases.json')
        source=extract_usage(); reports=[]
        for offset in range(8):
            start=current-timedelta(weeks=offset); end=start+timedelta(days=6)
            if end < date(2026,10,1): continue
            target=STATE/'snapshots'/(start.isoformat()+'.json')
            if target.exists() and start < current:
                report=json.loads(target.read_text(encoding='utf8'))
                if report['complete']: reports.append(report); continue
            roster_path=STATE/'rosters'/(start.isoformat()+'.json')
            if roster_path.exists(): roster=json.loads(roster_path.read_text(encoding='utf8'))
            else:
                roster=select_master(Path(args.master_root),min(today,end))
                older=sorted(file for file in (STATE/'rosters').glob('*.json') if file.stem<start.isoformat())
                previous_roster=json.loads(older[-1].read_text(encoding='utf8')) if older else None
                validate_roster_change(roster,previous_roster)
                atomic_json(roster_path,roster)
            roster=named_roster(roster,Path(args.master_root))
            report=build_report(start,end,roster,match_source(roster,source,aliases),now)
            atomic_json(target,report); reports.append(report)
        for report in reports:
            detail_path=STATE/'room-details'/(report['week']+'.json')
            if detail_path.exists() and report['complete']:
                details=json.loads(detail_path.read_text(encoding='utf8'))
            else:
                roster=json.loads((STATE/'rosters'/(report['week']+'.json')).read_text(encoding='utf8'))
                roster=named_roster(roster,Path(args.master_root))
                details={'rooms':build_rooms(report,roster,match_source(roster,source,aliases)),'generatedAt':now.isoformat()}
                atomic_json(detail_path,details)
            report['rooms']=details['rooms']
            report['roomDetailsGeneratedAt']=details['generatedAt']
        previous=next(r for r in reports if r['week']==(current-timedelta(days=7)).isoformat())
        if args.publish: publish(reports)
        packet_dir=STATE/'packets'/previous['week']; packet_dir.mkdir(parents=True,exist_ok=True)
        png=packet_dir/'weekly-usage.png'; chart(previous,png)
        for sample in (False, True):
            body=email_html(previous,sample); name='sample' if sample else 'weekly'
            (packet_dir/(name+'.html')).write_text(body,encoding='utf8')
            packet={'schema':1,'reportKey':previous['week'],'dueDate':current.isoformat(), 'generatedAt':now.isoformat(),
                'to':TEST_TO if sample else weekly_to,'subject':f'{"【サンプル】" if sample else ""}【室別・氏名付き】デイリーニュース 週次利用レポート（{previous["week"]}〜{previous["end"]}）',
                'body':body,'attachmentName':'weekly-usage-'+previous['week']+'.png','attachmentBase64':base64.b64encode(png.read_bytes()).decode()}
            atomic_json(packet_dir/(name+'.json'),packet)
            if args.onedrive: atomic_json(onedrive_folder()/(name+'.json'),packet)
        print(json.dumps({'reports':len(reports),'week':previous['week'],'headcount':previous['rows'][0]['headcount'],'packet':str(packet_dir),'published':args.publish,'oneDrivePrepared':args.onedrive},ensure_ascii=False))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--master-root',default=str(MASTER_ROOT));parser.add_argument('--publish',action='store_true');parser.add_argument('--onedrive',action='store_true')
    run(parser.parse_args())
