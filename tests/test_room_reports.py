import sys, unittest
from pathlib import Path
from datetime import date, datetime
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'deployment/weekly-report'))
import weekly_report as weekly
from room_reports import build_rooms, email_html, read_note, member_row

class RoomReportsTests(unittest.TestCase):
    def fixture(self):
        roster={'masterDate':'2026-09-21','masterName':'fixture','members':{
            'i1':{'name':'内装 利用者','room':'内装開発室','group':'内装開発室 1G'},
            'i2':{'name':'内装 外装のみ利用','room':'内装開発室','group':'内装開発室 1G'},
            'i3':{'name':'内装 未登録','room':'内装開発室','group':'内装開発室 2G'},
            'e1':{'name':'外装 利用者','room':'外装開発室','group':'外装開発室 1G'},
            'e2':{'name':'外装 未登録','room':'外装開発室','group':'外装開発室 1G'},
            'dept':{'name':'部員','room':'IE開発部（室外）','group':'IE開発部'}}}
        def data(): return {'accounts':[],'usageStarted':'2026-10-01 00:00:00','readsStarted':'2026-10-13 00:00:00','usage':[],'reads':[],'likes':[],'comments':[],'access':[]}
        source={'interior':data(),'exterior':data()}
        source['interior']['accounts']=[{'key':k,'createdAt':'2026-10-01 00:00:00'} for k in ('i1','i2','e1','dept')]+[{'key':'i3','createdAt':'2026-10-11 15:00:00'}]
        source['interior']['usage']=[{'key':'i1','date_key':'2026-10-05'},{'key':'i1','date_key':'2026-10-05'},{'key':'dept','date_key':'2026-10-05'}]
        source['exterior']['usage']=[{'key':'e1','date_key':'2026-10-06'},{'key':'i2','date_key':'2026-10-06'}]
        source['interior']['likes']=[{'key':'i1','date_key':'2026-10-06','count':2},{'key':'i2','date_key':'2026-10-12','count':1}]
        report=weekly.build_report(date(2026,10,5),date(2026,10,11),roster,source,datetime(2026,10,13,tzinfo=weekly.JST))
        report['rooms']=build_rooms(report,roster,source)
        return report,roster,source
    def test_own_room_own_edition_only(self):
        report,_,_=self.fixture()
        interior,exterior=report['rooms']['interior'],report['rooms']['exterior']
        self.assertEqual((interior['active'],interior['headcount'],interior['registeredInactive'],interior['unregistered']),(1,3,1,1))
        self.assertEqual((exterior['active'],exterior['headcount']),(1,2))
        people=[m for g in interior['groups'] for m in g['members']]
        active=next(m for m in people if m['active']);self.assertEqual(active['days'],2);self.assertEqual(active['likes'],2)
        self.assertEqual(active['lastActivity'],'2026-10-06')
        self.assertNotIn('部員',str(report['rooms']))
        self.assertNotIn('外装 利用者',str(interior))
    def test_named_status_period_and_email(self):
        report,_,_=self.fixture(); body=email_html(report)
        self.assertIn('内装 外装のみ利用（登録済・利用記録なし）',body)
        self.assertIn('内装 未登録（未登録）',body)
        self.assertIn('計測前',body)
        self.assertNotIn('両版合計',body)
        self.assertNotIn('部員',body)
        self.assertNotIn('i1',body)
    def test_reconstruction_must_reconcile(self):
        report,roster,source=self.fixture()
        source['interior']['usage'].append({'key':'i2','date_key':'2026-10-05'})
        with self.assertRaises(ValueError):build_rooms(report,roster,source)

    def test_days_combine_distinct_dates_without_counting_other_edition(self):
        _,roster,source=self.fixture()
        source['interior']['usage']=[{'key':'i1','date_key':'2026-10-13'}]*2
        source['interior']['reads']=[{'key':'i1','date_key':'2026-10-13','count':20}]
        source['interior']['likes']=[{'key':'i1','date_key':'2026-10-13','count':3}]
        source['interior']['comments']=[{'key':'i1','date_key':'2026-10-13','count':3}]
        source['exterior']['usage']=[{'key':'i1','date_key':'2026-10-14'}]
        report=weekly.build_report(date(2026,10,12),date(2026,10,18),roster,source,datetime(2026,10,19,tzinfo=weekly.JST))
        def person():
            return next(m for g in build_rooms(report,roster,source)['interior']['groups'] for m in g['members'] if m['name']=='内装 利用者')
        self.assertEqual((person()['days'],person()['lastActivity']),(1,'2026-10-13'))
        source['interior']['comments'].append({'key':'i1','date_key':'2026-10-15','count':1})
        report=weekly.build_report(date(2026,10,12),date(2026,10,18),roster,source,datetime(2026,10,19,tzinfo=weekly.JST))
        self.assertEqual(person()['days'],2)

    def test_partial_read_note_is_near_both_tables_and_uses_actual_start(self):
        report,_,_=self.fixture()
        report['coverage']['interior'].update(readsStarted='2026-10-08',readsComplete=False)
        body=email_html(report)
        note=read_note(report,'interior')
        self.assertIn('2026-10-08',note)
        self.assertIn('閲覧数だけ',note)
        self.assertEqual(body.count(note),2)
        self.assertLess(body.index(note),body.index('回※'))
        detail=body.index('グループごとの個人別利用状況')
        self.assertLess(body.index(note,detail),body.index('<th>利用日数</th>',detail))
        report['coverage']['interior']['readsComplete']=True
        self.assertEqual(read_note(report,'interior'),'')
        self.assertNotIn('※',email_html(report))

    def test_followup_marked_for_both_inactive_statuses_and_escapes_names(self):
        report,_,_=self.fixture()
        people=[m for g in report['rooms']['interior']['groups'] for m in g['members']]
        for m in people:
            row=member_row(report,'interior',{**m,'name':'<名前 & 確認>'})
            self.assertIn('&lt;名前 &amp; 確認&gt;',row)
            self.assertEqual('フォロー対象' in row,not m['active'])
            self.assertEqual('background:#fff4dc' in row,not m['active'])
            self.assertIn(m['status'],row)

if __name__=='__main__':unittest.main()
