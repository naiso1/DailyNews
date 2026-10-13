"""Room-owned editions and named follow-up reports, for administrators only."""
from __future__ import annotations
import html, os
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOMS = {'interior': '内装開発室', 'exterior': '外装開発室'}
TITLES = {'interior': '内装製品デイリーニュース', 'exterior': '外装製品デイリーニュース'}

def day(stamp):
    if not stamp: return None
    value = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
    if value.tzinfo is None: value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone(timedelta(hours=9))).date().isoformat()

def group_name(name, room):
    return '室直属' if name == room else name.replace(room, '').replace('インテリア開発', '').replace('エクステリア開発', '').strip()

def summarize(members):
    result = {'headcount': len(members), 'registered': sum(m['registered'] for m in members),
              'active': sum(m['active'] for m in members),
              'unregistered': sum(not m['registered'] and not m['active'] for m in members),
              'registeredInactive': sum(m['registered'] and not m['active'] for m in members)}
    for metric in ('reads', 'likes', 'comments'):
        result[metric] = sum(m[metric] for m in members)
        result[metric+'Users'] = sum(m[metric] > 0 for m in members)
    return result

def build_rooms(report, roster, source):
    start, end = report['week'], report['end']
    registered = {r['key'] for r in source['interior']['accounts'] if day(r['createdAt']) and day(r['createdAt']) <= end}
    result = {}
    for edition, room in ROOMS.items():
        data = source[edition]
        events = {metric: [r for r in data[metric] if start <= r['date_key'] <= end] for metric in ('usage', 'reads', 'likes', 'comments')}
        members = []
        complete = bool(day(data['usageStarted']) and day(data['usageStarted']) < start)
        for key, person in roster['members'].items():
            if person['room'] != room: continue
            matched = {metric: [r for r in rows if r['key'] == key] for metric, rows in events.items()}
            dates = {r['date_key'] for rows in matched.values() for r in rows}
            active = bool(dates)
            member = {'name': person.get('name') or '氏名未取得', 'group': person['group'],
                      'registered': key in registered, 'active': active, 'days': len(dates),
                      'lastActivity': max(dates) if dates else None}
            member.update({metric: sum(r['count'] for r in matched[metric]) for metric in ('reads', 'likes', 'comments')})
            member['status'] = '利用あり' if active else '未登録' if key not in registered else '登録済・利用記録なし'
            members.append(member)
        groups = []
        for name in sorted({m['group'] for m in members}):
            selected = sorted((m for m in members if m['group'] == name), key=lambda m: (m['active'], m['registered'], m['name']))
            groups.append({'name': name, 'label': group_name(name, room), **summarize(selected), 'members': selected})
        summary = summarize(members)
        # A historical named reconstruction must reconcile with the frozen totals.
        frozen = next((r for r in report['rows'] if r['level'] == 'room' and r['name'] == room), None)
        if frozen:
            expected = {'headcount': frozen['headcount'], 'registered': frozen['registered'], **frozen['editions'][edition]}
            if any(summary[k] != v for k, v in expected.items()):
                raise ValueError('氏名付き集計が保存済みの室別集計と一致しません。元の週次結果を保持して確認してください。')
        result[edition] = {'room': room, 'edition': edition, 'title': TITLES[edition], **summary,
                           'groups': groups, 'usageComplete': complete}
    return result

def percentage(active, total): return round(100*active/total) if total else 0

def reads(report, edition, value):
    c = report['coverage'][edition]
    if not c['readsStarted'] or c['readsStarted'] > report['end']: return '計測前'
    return str(value) + ('回' if c['readsComplete'] else '回※')

def email_html(report, sample=False):
    esc = html.escape
    sections = report['rooms']
    body = [f'<html lang="ja"><head><meta charset="utf-8"></head><body style="font-family:Meiryo,sans-serif;color:#20364a;max-width:1050px;margin:auto;padding:24px"><h1 style="font-size:25px">各室のデイリーニュース利用状況</h1><p>{report["week"]} 〜 {report["end"]}（月曜〜日曜・日本時間）</p><p>内装開発室は内装版、外装開発室は外装版の利用を集計しています。</p>']
    if sample: body.append('<p>中村さん向けの確認用です。試行中は中村さんのみに送信します。</p>')
    body.append('<table cellpadding="9" cellspacing="0" style="border-collapse:collapse;width:100%;background:#edf3f7"><tr><th align="left">対象</th><th>利用人数 / 室の人数</th><th>利用率</th><th>登録済・利用記録なし</th><th>未登録</th></tr>')
    for edition, section in sections.items():
        body.append(f'<tr><td>{section["room"]}（{section["title"][:2]}版）</td><td align="center">{section["active"]} / {section["headcount"]}人</td><td align="center"><b>{percentage(section["active"],section["headcount"])}%</b></td><td align="center">{section["registeredInactive"]}人</td><td align="center">{section["unregistered"]}人</td></tr>')
    body.append('</table><p style="font-size:13px">利用率＝自室の版を利用したメンバー数 ÷ その室の名簿人数。未登録の人も分母に含めます。</p>')
    for edition, section in sections.items():
        color = '#2375af' if edition == 'interior' else '#178274'
        body.append(f'<h2 style="border-bottom:3px solid {color};padding-top:24px">{section["room"]}：{section["title"]}の利用</h2><p><b>{section["active"]} / {section["headcount"]}人（{percentage(section["active"],section["headcount"])}%）</b>が利用。利用記録なしは{section["registeredInactive"]+section["unregistered"]}人です。</p>')
        if not section['usageComplete']: body.append('<p>この週は利用人数の部分計測です。利用記録がない人も、計測開始前に利用していた可能性があります。</p>')
        body.append('<table cellpadding="8" cellspacing="0" style="border-collapse:collapse;width:100%;font-size:14px"><tr style="background:#edf3f7"><th align="left">グループ</th><th>利用人数 / 人数</th><th>利用率</th><th>利用記録なし</th><th>閲覧</th><th>いいね</th><th>コメント</th></tr>')
        for group in section['groups']:
            pct = percentage(group['active'],group['headcount'])
            body.append(f'<tr style="border-bottom:1px solid #dce4ed"><td>{esc(group["label"])}</td><td align="center">{group["active"]}/{group["headcount"]}人</td><td style="min-width:110px">{pct}%<div style="height:8px;background:#e1e8ef"><div style="height:8px;background:{color};width:{pct}%"></div></div></td><td align="center">{group["registeredInactive"]+group["unregistered"]}人</td><td align="center">{reads(report,edition,group["reads"])}</td><td align="center">{group["likes"]}件</td><td align="center">{group["comments"]}件</td></tr>')
        body.append('</table><h3>フォロー対象の確認</h3><p style="font-size:13px">未登録の方には登録案内、登録済みで利用記録がない方にはアクセス方法や利用しづらい点の確認にお使いください。状態は対象週末時点です。</p>')
        for group in section['groups']:
            inactive = [m for m in group['members'] if not m['active']]
            text = '、'.join(esc(m['name'])+'（'+esc(m['status'])+'）' for m in inactive) or '利用記録なしの人はいません。'
            body.append(f'<p><b>{esc(group["label"])}</b>：{text}</p>')
        body.append('<h3>グループごとの個人別利用状況</h3>')
        for group in section['groups']:
            body.append(f'<h4>{esc(group["label"])}</h4><table cellpadding="8" cellspacing="0" style="border-collapse:collapse;width:100%;font-size:13px"><tr style="background:#edf3f7"><th align="left">氏名</th><th align="left">対象週の状態</th><th>利用日数</th><th>週内の最終利用</th><th>閲覧</th><th>いいね</th><th>コメント</th></tr>')
            for m in group['members']:
                body.append(f'<tr style="border-bottom:1px solid #dce4ed"><td>{esc(m["name"])}</td><td>{esc(m["status"])}</td><td align="center">{m["days"]}日</td><td align="center">{(m["lastActivity"] or "—")}</td><td align="center">{reads(report,edition,m["reads"])}</td><td align="center">{m["likes"]}件</td><td align="center">{m["comments"]}件</td></tr>')
            body.append('</table>')
    body.append(f'<h3>集計の見方</h3><ul style="font-size:13px"><li>名簿：{report["masterDate"]}時点。各室の所属グループで表示しています。</li><li>利用あり＝ログインした画面利用・記事閲覧・いいね・コメントのいずれかを対象週に確認。同じ人は1人、同じ日は1日です。</li><li>利用記録なし＝対象週の記録を確認できない状態。未ログインの閲覧は個人へ割り当てていません。</li><li>グループ・個人別の閲覧数は2026年10月13日から計測。過去分は「計測前」と表示します。※は週の途中からの計測です。</li><li>いいね・コメントは対象週に作成され、集計時点で残っている件数です。</li><li>このメールには管理者のフォローに使う個人別の利用状況を含みます。</li></ul><p><a href="http://IEWEB01/?admin=1">内装版の管理画面</a> ／ <a href="http://IEWEB01/exterior/?admin=1">外装版の管理画面</a></p></body></html>')
    return ''.join(body)

def chart(report, destination):
    from PIL import Image, ImageDraw, ImageFont
    font_path = Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts/meiryo.ttc'
    font = lambda n: ImageFont.truetype(str(font_path), n)
    count = sum(len(r['groups']) for r in report['rooms'].values())
    image = Image.new('RGB',(1500,410+count*85),'#f6f8fb'); d = ImageDraw.Draw(image)
    d.text((50,25),'各室のデイリーニュース利用状況',font=font(34),fill='#20364a')
    d.text((50,85),f'{report["week"]} 〜 {report["end"]}　利用人数 / 各室・グループの名簿人数',font=font(23),fill='#506578')
    y = 140
    for edition, section in report['rooms'].items():
        color = '#2375af' if edition == 'interior' else '#178274'
        d.text((50,y),f'{section["room"]} × {section["title"][:2]}版　{section["active"]}/{section["headcount"]}人（{percentage(section["active"],section["headcount"])}%）',font=font(29),fill=color); y+=65
        for group in section['groups']:
            pct = percentage(group['active'],group['headcount'])
            d.text((65,y),group['label'],font=font(25),fill='#20364a')
            d.rectangle((235,y+5,1125,y+32),fill='#e1e8ef')
            if pct: d.rectangle((235,y+5,235+round(890*pct/100),y+32),fill=color)
            d.text((1150,y),f'{group["active"]}/{group["headcount"]}人　{pct}%',font=font(25),fill='#20364a')
            d.text((235,y+42),f'利用記録なし {group["registeredInactive"]+group["unregistered"]}人（登録済 {group["registeredInactive"]}人 / 未登録 {group["unregistered"]}人）',font=font(18),fill='#506578')
            y+=85
        y+=25
    d.text((50,image.height-48),'同じ人は1人として集計。個人名と週内の利用状況はメール本文に掲載しています。',font=font(21),fill='#506578')
    image.save(destination)
