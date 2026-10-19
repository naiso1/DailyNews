"""Explicit, privately verified email aliases for roster/account reconciliation.

Never match people by a similar name or email spelling. Account and roster data
stay unchanged; only report input keys are translated for the applicable roster.
"""
from __future__ import annotations
import copy
import json
import re
import unicodedata


def load_aliases(path):
    if not path.exists():
        return []
    value = json.loads(path.read_text(encoding='utf-8-sig'))
    if value.get('schema') != 1 or not isinstance(value.get('aliases'), list):
        raise ValueError('照合対応表の形式が不正です。')
    aliases = value['aliases']
    sources, targets = set(), set()
    for row in aliases:
        source, target = row.get('accountKey', ''), row.get('rosterKey', '')
        if not all(re.fullmatch(r'[0-9a-f]{64}', key) for key in (source, target)):
            raise ValueError('照合対応表のキーが不正です。')
        if source == target or source in sources or target in targets:
            raise ValueError('照合対応表に重複または競合があります。')
        if not all(isinstance(row.get(k), str) and row[k].strip()
                   for k in ('rosterName', 'verifiedAt', 'evidence')):
            raise ValueError('照合対応表に確認済みの氏名・日時・根拠が必要です。')
        sources.add(source); targets.add(target)
    if sources & targets:
        raise ValueError('照合対応表の連鎖は許可されていません。')
    return aliases


def match_source(roster, source, aliases):
    members = roster['members']
    account_keys = {row['key'] for data in source.values() for row in data['accounts']}
    mapping = {}
    normalize_name = lambda value: ' '.join(unicodedata.normalize('NFKC', value).split())
    for row in aliases:
        old, new = row['accountKey'], row['rosterKey']
        if new not in members:
            # A newer master may already contain the actual account address.
            continue
        if old in members or (old in account_keys and new in account_keys):
            raise ValueError('照合先が複数の名簿行またはアカウントと競合しています。集計を保留しました。')
        if normalize_name(members[new].get('name', '')) != normalize_name(row['rosterName']):
            raise ValueError('照合対応表と名簿の氏名が一致しません。集計を保留しました。')
        mapping[old] = new
    result = copy.deepcopy(source)
    for data in result.values():
        for metric in ('accounts', 'usage', 'reads', 'likes', 'comments'):
            for row in data[metric]:
                row['key'] = mapping.get(row['key'], row['key'])
    return result
