import importlib.util, tempfile, unittest, sys
from datetime import date, datetime
from pathlib import Path

spec=importlib.util.spec_from_file_location('weekly',Path(__file__).resolve().parents[1]/'deployment/weekly-report/weekly_report.py')
weekly=importlib.util.module_from_spec(spec);spec.loader.exec_module(weekly)

class WeeklyReportTests(unittest.TestCase):
    def test_large_roster_change_is_held(self):
        previous={'members':{str(n):{} for n in range(47)}}
        weekly.validate_roster_change({'members':{str(n):{} for n in range(48)}},previous)
        with self.assertRaises(ValueError): weekly.validate_roster_change({'members':{'one':{}}},previous)
    def test_mail_flow_guard_and_recipient(self):
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'deployment/weekly-report'))
        from build_flow import build
        source={'properties':{'connectionReferences':{'shared_office365':{},'shared_onedriveforbusiness':{},'unused':{}},'definition':{'parameters':{}},'environment':{}}}
        for sample in (True,False):
            flow=build(source,datetime(2026,10,13,10,tzinfo=weekly.JST),sample)['properties']
            self.assertEqual(flow['state'],'Stopped')
            self.assertEqual(len(flow['connectionReferences']),2)
            trigger=flow['definition']['triggers']['Weekly_schedule']
            self.assertEqual(trigger['runtimeConfiguration']['concurrency']['runs'],1)
            guard=flow['definition']['actions']['Check_ready_and_unsent']
            self.assertEqual(len(guard['expression']['and']),5)
            mail=guard['actions']['Send_report']
            self.assertEqual(mail['inputs']['parameters']['emailMessage/To'],weekly.TEST_TO)
            self.assertNotIn('emailMessage/Cc',mail['inputs']['parameters'])
            self.assertEqual(mail['runAfter'],{'Claim_delivery':['Succeeded']})
            self.assertEqual(mail['inputs']['retryPolicy'],{'type':'none'})
    def test_identity_and_period(self):
        self.assertEqual(weekly.identity(' Ａ@EXAMPLE.com '),weekly.identity('a@example.com'))
        self.assertEqual(weekly.week_start(date(2026,10,11)),date(2026,10,5))
        self.assertEqual(weekly.stamp_day('2026-10-04 15:00:00'),'2026-10-05')
    def test_union_denominator_and_independent_editions(self):
        roster={'masterDate':'2026-09-21','masterName':'fixture','members':{'one':{'group':'内装開発室 1G','room':'内装開発室'},'two':{'group':'内装開発室 1G','room':'内装開発室'},'three':{'group':'外装開発室 1G','room':'外装開発室'}}}
        def source(): return {'accounts':[{'key':'one','createdAt':'2026-10-04 15:00:00'},{'key':'two','createdAt':'2026-10-11 15:00:00'}], 'usageStarted':'2026-10-01 00:00:00','readsStarted':'2026-10-13 00:00:00','usage':[{'key':'one','date_key':'2026-10-05'},{'key':'one','date_key':'2026-10-06'},{'key':'outsider','date_key':'2026-10-06'}],'reads':[],'likes':[{'key':'one','date_key':'2026-10-05','count':2}],'comments':[],'access':[]}
        result=weekly.build_report(date(2026,10,5),date(2026,10,11),roster,{'interior':source(),'exterior':source()},datetime(2026,10,13,tzinfo=weekly.JST))
        total=result['rows'][0];self.assertEqual(total['headcount'],3);self.assertEqual(total['registered'],1)
        self.assertEqual(total['editions']['combined']['active'],1)
        self.assertEqual(total['editions']['combined']['likes'],4)
        self.assertEqual(total['editions']['combined']['likesUsers'],1)
        self.assertEqual(result['unmatched']['combined']['active'],1)
        self.assertEqual(weekly.read_label(result,'combined',0),'計測前')
        self.assertNotIn('outsider',weekly.email_html(result))
    def test_latest_uses_effective_date_and_validates_duplicates(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'old').mkdir();(root/'new').mkdir()
            header='社員コード,メールアドレス,見出し名\n'
            (root/'old/社員マスタ_20260921.csv').write_text(header+'1,a@example.com,内装開発室　インテリア開発　１G\n',encoding='utf-8-sig')
            (root/'new/社員マスタ_20261020.csv').write_text(header+'2,b@example.com,外装開発室\n',encoding='utf-8-sig')
            roster=weekly.select_master(root,date(2026,10,13))
            self.assertEqual(roster['masterDate'],'2026-09-21')
            self.assertEqual(next(iter(roster['members'].values()))['group'],'内装開発室 インテリア開発 1G')
            (root/'old/社員マスタ_20260921.csv').write_text(header+'1,a@example.com,X\n2,A@example.com,Y\n',encoding='utf-8-sig')
            with self.assertRaises(ValueError):weekly.select_master(root,date(2026,10,13))

if __name__=='__main__':unittest.main()
