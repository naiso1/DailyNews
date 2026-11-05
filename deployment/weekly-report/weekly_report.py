"""Private roster snapshots, edition-aware usage reports and a guarded mail packet.

Named reports are private to administrators. SSH extraction returns hashed emails.
The previous complete week is frozen once; later roster updates cannot alter it.
"""
from __future__ import annotations
import argparse, base64, html, json, os, subprocess, sys, uuid
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from room_reports import build_rooms, email_html, chart
from identity_matching import load_aliases, match_source
from report_exclusions import load_exclusions, keys_for_week, validate_keys, prepare_inputs
from delivery import TEST_TO, recipient_to

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dailynews.employee_master import MASTER_ROOT, normalized, identity, select_master

STATE = ROOT / 'runtime' / 'weekly-report'
JST = timezone(timedelta(hours=9))
LABELS = {'interior': '内装版', 'exterior': '外装版', 'combined': '両版合計'}

def atomic_json(file, value):
    file.parent.mkdir(parents=True, exist_ok=True)
    temp = file.with_name(file.name + '.' + uuid.uuid4().hex + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf8')
    os.replace(temp, file)

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

def weekly_roster(path, root, effective, *, refresh, previous=None):
    stored = json.loads(path.read_text(encoding='utf8')) if path.exists() else None
    if stored and not refresh:
        return named_roster(stored, root)
    latest = select_master(root, effective)
    if stored and latest['masterDate'] < stored['masterDate']:
        raise ValueError('社員マスタが保存済みの名簿より古いため、取り込みを保留しました。')
    validate_roster_change(latest, stored or previous)
    if not stored or (latest['masterDate'], latest['masterHash']) != (stored['masterDate'], stored['masterHash']):
        if stored:
            # Keep a private rollback copy before replacing an in-progress week's roster.
            archive = path.parent/'history'/path.stem/(stored['masterDate']+'_'+stored['masterHash']+'.json')
            if not archive.exists(): atomic_json(archive, stored)
        atomic_json(path, latest)
    return latest
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
        **({'population': roster['population']} if 'population' in roster else {}),
        'notes': ['利用率＝期間内の利用人数÷集計対象人数。設定された集計除外者は分母・分子・個人別一覧・フォロー対象から除きます。管理者も対象に含みます。',
          '閲覧＝「記事を読む」のクリック。同じ人・同じ記事・同じ日は1回（両版は別記事扱い）。ログインした利用者が対象です。',
          'いいね・コメントは対象週に作成され、集計時点で残っている件数。取消・削除済みは含みません。',
          '進行中の週は最新の社員マスタで所属を更新します。確定済みの過去週は、その週の保存済み名簿を保持します。',
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
        exclusions=load_exclusions(STATE/'report-exclusions.json')
        source=extract_usage(); reports=[]
        inputs={}
        for offset in range(8):
            start=current-timedelta(weeks=offset); end=start+timedelta(days=6)
            if end < date(2026,10,1): continue
            target=STATE/'snapshots'/(start.isoformat()+'.json')
            if target.exists() and start < current:
                report=json.loads(target.read_text(encoding='utf8'))
                if report['complete']: reports.append(report); continue
            roster_path=STATE/'rosters'/(start.isoformat()+'.json')
            older=sorted(file for file in (STATE/'rosters').glob('*.json') if file.stem<start.isoformat())
            previous_roster=json.loads(older[-1].read_text(encoding='utf8')) if older else None
            roster=weekly_roster(roster_path,Path(args.master_root),min(today,end),
                                 refresh=start == current,previous=previous_roster)
            exclusion_path=STATE/'exclusions-by-week'/(start.isoformat()+'.json')
            if start < current and exclusion_path.exists():
                saved=json.loads(exclusion_path.read_text(encoding='utf8'))
                if saved.get('schema') != 1 or saved.get('week') != start.isoformat():
                    raise ValueError('保存済みの集計除外設定が不正です。')
                keys=validate_keys(saved.get('keys'))
            else:
                keys=keys_for_week(exclusions,start.isoformat())
            eligible,matched=prepare_inputs(roster,source,aliases,keys)
            inputs[start.isoformat()]=(eligible,matched)
            report=build_report(start,end,eligible,matched,now)
            atomic_json(exclusion_path,{'schema':1,'week':start.isoformat(),'keys':keys})
            atomic_json(target,report); reports.append(report)
        for report in reports:
            detail_path=STATE/'room-details'/(report['week']+'.json')
            if detail_path.exists() and report['complete']:
                details=json.loads(detail_path.read_text(encoding='utf8'))
            else:
                if report['week'] in inputs:
                    eligible,matched=inputs[report['week']]
                else:
                    roster=json.loads((STATE/'rosters'/(report['week']+'.json')).read_text(encoding='utf8'))
                    roster=named_roster(roster,Path(args.master_root))
                    exclusion_path=STATE/'exclusions-by-week'/(report['week']+'.json')
                    keys=validate_keys(json.loads(exclusion_path.read_text(encoding='utf8')).get('keys')) if exclusion_path.exists() else []
                    eligible,matched=prepare_inputs(roster,source,aliases,keys)
                details={'rooms':build_rooms(report,eligible,matched),'generatedAt':now.isoformat()}
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
