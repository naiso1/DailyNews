"""Private, week-scoped report exclusions; never modify employee/account records."""
from copy import deepcopy
from datetime import date
import json
import re

from identity_matching import match_source


def monday(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('集計除外の適用週はYYYY-MM-DD形式で指定してください。')
    parsed = date.fromisoformat(value)
    if parsed.weekday() != 0:
        raise ValueError('集計除外の適用週は月曜日を指定してください。')
    return value


def validate_keys(keys):
    if not isinstance(keys, list) or any(not isinstance(k, str) or not re.fullmatch(r'[0-9a-f]{64}', k) for k in keys):
        raise ValueError('集計除外の照合キーが不正です。')
    if len(set(keys)) != len(keys):
        raise ValueError('集計除外の照合キーに重複があります。')
    return keys


def load_exclusions(path):
    if not path.exists():
        return []
    value = json.loads(path.read_text(encoding='utf-8-sig'))
    if value.get('schema') != 1 or not isinstance(value.get('exclusions'), list):
        raise ValueError('集計除外設定の形式が不正です。')
    rows = value['exclusions']
    periods = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('集計除外設定の行が不正です。')
        key = validate_keys([row.get('rosterKey')])[0]
        start = monday(row.get('fromWeek'))
        end = monday(row['untilWeek']) if row.get('untilWeek') is not None else '9999-12-31'
        if start >= end:
            raise ValueError('集計除外の終了週は開始週より後にしてください。')
        if any(start < old_end and old_start < end for old_start, old_end in periods.get(key, [])):
            raise ValueError('集計除外の適用期間が重複しています。')
        periods.setdefault(key, []).append((start, end))
    return rows


def keys_for_week(exclusions, week):
    monday(week)
    return sorted({row['rosterKey'] for row in exclusions
                   if row['fromWeek'] <= week and (row.get('untilWeek') is None or week < row['untilWeek'])})


def prepare_inputs(roster, source, aliases, keys):
    # Resolve verified aliases against the full roster before removing people.
    matched = match_source(roster, source, aliases)
    excluded = set(keys)
    eligible = deepcopy(roster)
    eligible['members'] = {key: person for key, person in roster['members'].items() if key not in excluded}
    by_room = {}
    for key, person in roster['members'].items():
        counts = by_room.setdefault(person['room'], {'masterHeadcount': 0, 'excludedCount': 0})
        counts['masterHeadcount'] += 1
        counts['excludedCount'] += key in excluded
    eligible['population'] = {'masterHeadcount': len(roster['members']),
                              'excludedCount': len(set(roster['members']) & excluded), 'byRoom': by_room}
    for data in matched.values():
        for metric in ('accounts', 'usage', 'reads', 'likes', 'comments'):
            # Do not reclassify excluded activity as "outside the employee master".
            data[metric] = [row for row in data[metric] if row['key'] not in excluded]
    return eligible, matched
