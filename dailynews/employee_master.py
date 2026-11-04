"""Read the private employee master once for reporting and mail enrollment."""
import csv
from datetime import datetime
import hashlib
import io
from pathlib import Path
import re
import unicodedata

MASTER_ROOT = Path(r'\\tgfs1\ＩＥ開発部\90_その他\フロアー改革\電子掲示板')


def normalized(value):
    return unicodedata.normalize('NFKC', value).strip().lower()


def identity(value):
    return hashlib.sha256(normalized(value).encode()).hexdigest()


def select_master(root, effective, *, include_emails=False):
    candidates = []
    for file in Path(root).glob('*/社員マスタ_*.csv'):
        match = re.fullmatch(r'社員マスタ_(\d{8})\.csv', file.name)
        if match:
            stamp = datetime.strptime(match[1], '%Y%m%d').date()
            if stamp <= effective:
                candidates.append((stamp, file))
    if not candidates:
        raise ValueError('対象日以前の社員マスタがありません。')
    stamp = max(day for day, _ in candidates)
    newest = sorted(file for day, file in candidates if day == stamp)
    contents = [file.read_bytes() for file in newest]
    hashes = {hashlib.sha256(data).hexdigest() for data in contents}
    if len(hashes) != 1:
        raise ValueError('同じ日付の社員マスタの内容が異なります。')
    reader = csv.DictReader(io.StringIO(contents[0].decode('utf-8-sig'), newline=''))
    if not {'社員コード', 'メールアドレス', '見出し名'}.issubset(reader.fieldnames or []):
        raise ValueError('社員マスタの必須列がありません。')
    members, codes = {}, set()
    for row in reader:
        email = normalized(row.get('メールアドレス') or '')
        code = (row.get('社員コード') or '').strip()
        group = ' '.join(unicodedata.normalize('NFKC', row.get('見出し名') or '').split())
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email) or not code or not group:
            raise ValueError('名簿の必須値が不正です。')
        key = identity(email)
        if key in members or code in codes:
            raise ValueError('名簿に重複があります。')
        room = ('内装開発室' if group.startswith('内装開発室') else
                '外装開発室' if group.startswith('外装開発室') else 'IE開発部（室外）')
        member = {'group': group, 'room': room, 'name': ' '.join((row.get('氏名') or '').split())}
        if include_emails:
            member['email'] = email
        members[key] = member
        codes.add(code)
    if not members:
        raise ValueError('社員マスタが空です。')
    return {'masterDate': stamp.isoformat(), 'masterName': newest[0].name,
            'masterHash': next(iter(hashes)), 'members': members}


def mailing_payload(edition, effective, root=MASTER_ROOT):
    rooms = {'interior': '内装開発室', 'exterior': '外装開発室'}
    if edition not in rooms:
        raise ValueError('Unknown edition')
    roster = select_master(root, effective, include_emails=True)
    recipients = []
    for member in roster['members'].values():
        if member['room'] != rooms[edition]:
            continue
        domain = member['email'].partition('@')[2]
        if domain != 'toyoda-gosei.co.jp' and not domain.endswith('.toyoda-gosei.co.jp'):
            raise ValueError('社員マスタに会社外のメールアドレスがあります。')
        recipients.append({'email': member['email'], 'displayName': member['name'], 'room': member['room']})
    return {'schema': 1, 'edition': edition, 'masterDate': roster['masterDate'],
            'masterHash': roster['masterHash'], 'memberCount': len(roster['members']),
            'recipients': recipients}
