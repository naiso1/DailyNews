"""Private, explicitly approved recipients for weekly reports."""
import json, re
from pathlib import Path

TEST_TO = 'yuki.nakamura@toyoda-gosei.co.jp'
CONFIG = Path(__file__).resolve().parents[2] / 'runtime/weekly-report/delivery.json'

def validate_recipients(values):
    if not isinstance(values, list) or not values or any(not isinstance(v, str) for v in values):
        raise ValueError('週次レポートの配信先が不正です。')
    if any(v != v.strip().lower() or len(v) > 254 or not re.fullmatch(r'[a-z0-9._+%-]+@(?:[a-z0-9-]+\.)*toyoda-gosei\.co\.jp', v) for v in values):
        raise ValueError('承認済みの会社メールアドレスを指定してください。')
    if len(values) != len(set(values)):
        raise ValueError('週次レポートの配信先が重複しています。')
    return ';'.join(sorted(values))

def recipient_to(sample=False, config=CONFIG):
    if sample or not config.exists():
        return TEST_TO
    data = json.loads(config.read_text(encoding='utf-8-sig'))
    if data.get('schema') != 1 or data.get('mode') != 'administrators' or not data.get('approvedAt'):
        raise ValueError('週次レポートの管理者配信設定を確認してください。')
    return validate_recipients(data.get('recipients'))
