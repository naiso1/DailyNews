import copy, json, sys, tempfile, unittest
from pathlib import Path
from datetime import date, datetime
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'deployment/weekly-report'))
import weekly_report as w
from identity_matching import load_aliases, match_source


class IdentityMatchingTests(unittest.TestCase):
    def fixture(self):
        old,new=w.identity('actual@example.com'),w.identity('master@example.com')
        aliases=[{'accountKey':old,'rosterKey':new,'rosterName':'照合 対象','verifiedAt':'2026-10-19','evidence':'verified fixture'}]
        roster={'masterDate':'2026-09-21','masterName':'fixture','members':{new:{'name':'照合 対象','room':'内装開発室','group':'内装開発室 1G'}}}
        def data():return {'accounts':[{'key':old,'createdAt':'2026-10-01 00:00:00'}], 'usageStarted':'2026-10-01 00:00:00','readsStarted':'2026-10-01 00:00:00','usage':[{'key':old,'date_key':'2026-10-12'}],'reads':[{'key':old,'date_key':'2026-10-12','count':2}],'likes':[{'key':old,'date_key':'2026-10-13','count':3}],'comments':[{'key':old,'date_key':'2026-10-13','count':1}],'access':[]}
        return old,new,aliases,roster,{'interior':data(),'exterior':data()}
    def test_registration_and_all_activity_share_the_mapping(self):
        old,new,aliases,roster,source=self.fixture();original=copy.deepcopy(source)
        resolved=match_source(roster,source,aliases)
        report=w.build_report(date(2026,10,12),date(2026,10,18),roster,resolved,datetime(2026,10,19,tzinfo=w.JST))
        rooms=w.build_rooms(report,roster,resolved)
        person=rooms['interior']['groups'][0]['members'][0]
        self.assertEqual((person['registered'],person['active'],person['days'],person['reads'],person['likes'],person['comments']),(True,True,2,2,3,1))
        self.assertEqual(report['rows'][0]['editions']['combined']['active'],1)
        self.assertEqual(report['unmatched']['combined']['active'],0)
        self.assertEqual(source,original)
    def test_no_implicit_match_and_week_end_is_preserved(self):
        old,new,aliases,roster,source=self.fixture()
        self.assertEqual(match_source(roster,source,[]),source)
        source['interior']['accounts'][0]['createdAt']='2026-10-18 15:00:00'
        for data in source.values():
            for metric in ('usage','reads','likes','comments'):data[metric]=[]
        resolved=match_source(roster,source,aliases)
        report=w.build_report(date(2026,10,12),date(2026,10,18),roster,resolved,datetime(2026,10,19,tzinfo=w.JST))
        self.assertEqual(w.build_rooms(report,roster,resolved)['interior']['unregistered'],1)
    def test_corrected_master_uses_exact_address(self):
        old,new,aliases,roster,source=self.fixture()
        roster['members'][old]=roster['members'].pop(new)
        self.assertEqual(match_source(roster,source,aliases),source)
    def test_ambiguous_accounts_or_roster_hold_report(self):
        old,new,aliases,roster,source=self.fixture()
        source['interior']['accounts'].append({'key':new,'createdAt':'2026-10-01'})
        with self.assertRaises(ValueError):match_source(roster,source,aliases)
        source['interior']['accounts'].pop();roster['members'][old]=roster['members'][new]
        with self.assertRaises(ValueError):match_source(roster,source,aliases)
        del roster['members'][old];roster['members'][new]['name']='別の 人'
        with self.assertRaises(ValueError):match_source(roster,source,aliases)
    def test_alias_file_requires_evidence_and_no_chain(self):
        old,new,aliases,_,_=self.fixture()
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'aliases.json';self.assertEqual(load_aliases(path),[])
            def write(items):path.write_text(json.dumps({'schema':1,'aliases':items}),encoding='utf8')
            write(aliases);self.assertEqual(load_aliases(path),aliases)
            write(aliases*2)
            with self.assertRaises(ValueError):load_aliases(path)
            write([{**aliases[0],'evidence':''}])
            with self.assertRaises(ValueError):load_aliases(path)
            write(aliases+[{**aliases[0],'accountKey':new,'rosterKey':w.identity('third@example.com')}])
            with self.assertRaises(ValueError):load_aliases(path)


if __name__=='__main__':unittest.main()
