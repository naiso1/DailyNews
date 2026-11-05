import copy
from datetime import date, datetime
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'deployment/weekly-report'))
import weekly_report as weekly
from report_exclusions import load_exclusions, keys_for_week, prepare_inputs
from room_reports import build_rooms, email_html


class WeeklyExclusionsTests(unittest.TestCase):
    def fixture(self):
        keys = [weekly.identity(value+'@example.com') for value in ('inside', 'outside', 'excluded', 'unmatched')]
        inside, outside, excluded, unmatched = keys
        roster = {'masterDate':'2026-11-02', 'masterName':'fixture', 'members':{
            inside:{'name':'内装 対象者','room':'内装開発室','group':'内装開発室 1G'},
            outside:{'name':'外装 対象者','room':'外装開発室','group':'外装開発室 1G'},
            excluded:{'name':'除外される人','room':'外装開発室','group':'外装開発室 1G'}}}
        def data():
            return {'accounts':[], 'usageStarted':'2026-10-01 00:00:00', 'readsStarted':'2026-10-01 00:00:00',
                    'usage':[], 'reads':[], 'likes':[], 'comments':[], 'access':[]}
        source = {'interior':data(), 'exterior':data()}
        source['interior']['accounts'] = [{'key':key,'createdAt':'2026-10-01 00:00:00'} for key in keys[:3]]
        for edition in source:
            for metric in ('usage','reads','likes','comments'):
                source[edition][metric]=[{'key':excluded,'date_key':'2026-11-03','count':9},
                                         {'key':unmatched,'date_key':'2026-11-03','count':1}]
        source['exterior']['usage'].append({'key':outside,'date_key':'2026-11-04'})
        return roster, source, keys

    def report(self, roster, source, aliases, keys):
        eligible, matched=prepare_inputs(roster,source,aliases,keys)
        report=weekly.build_report(date(2026,11,2),date(2026,11,8),eligible,matched,datetime(2026,11,5,tzinfo=weekly.JST))
        report['rooms']=build_rooms(report,eligible,matched)
        return report

    def test_excluded_person_removed_from_denominator_numerator_details_and_outside(self):
        roster,source,keys=self.fixture()
        original=copy.deepcopy((roster,source))
        report=self.report(roster,source,[],[keys[2]])
        room=report['rooms']['exterior']
        self.assertEqual((room['masterHeadcount'],room['excludedCount'],room['headcount'],room['active']),(2,1,1,1))
        self.assertEqual(room['registered'],1)
        self.assertEqual((room['reads'],room['likes'],room['comments']),(0,0,0))
        self.assertEqual(room['registeredInactive']+room['unregistered'],0)
        self.assertEqual(report['rows'][0]['headcount'],2)
        self.assertEqual(report['unmatched']['exterior']['active'],1)
        self.assertEqual(report['unmatched']['exterior']['reads'],1)
        self.assertNotIn('除外される人',email_html(report))
        self.assertIn('集計除外 1人',email_html(report))
        self.assertNotIn(keys[2],json.dumps(report))
        self.assertEqual((roster,source),original)

    def test_inactive_person_is_not_in_followup(self):
        roster,source,keys=self.fixture()
        for data in source.values():
            for metric in ('accounts','usage','reads','likes','comments'):
                data[metric]=[row for row in data[metric] if row['key']!=keys[2]]
        report=self.report(roster,source,[],[keys[2]])
        self.assertNotIn('除外される人',email_html(report))
        self.assertEqual(report['rooms']['exterior']['unregistered'],0)

    def test_verified_alias_is_resolved_before_exclusion(self):
        roster,source,keys=self.fixture()
        alias=weekly.identity('old@example.com')
        for data in source.values():
            for metric in ('accounts','usage','reads','likes','comments'):
                for row in data[metric]:
                    if row['key']==keys[2]: row['key']=alias
        aliases=[{'accountKey':alias,'rosterKey':keys[2],'rosterName':'除外される人'}]
        report=self.report(roster,source,aliases,[keys[2]])
        self.assertEqual(report['unmatched']['combined']['reads'],2)
        self.assertEqual(report['rooms']['exterior']['active'],1)

    def test_week_boundaries_and_resume(self):
        key='a'*64
        rows=[{'rosterKey':key,'fromWeek':'2026-11-02','untilWeek':'2027-01-11'}]
        self.assertEqual(keys_for_week(rows,'2026-10-26'),[])
        self.assertEqual(keys_for_week(rows,'2026-11-02'),[key])
        self.assertEqual(keys_for_week(rows,'2027-01-04'),[key])
        self.assertEqual(keys_for_week(rows,'2027-01-11'),[])
        rows[0]['untilWeek']=None
        self.assertEqual(keys_for_week(rows,'2027-03-01'),[key])

    def test_resume_restores_person_and_unmodified_roster_still_has_them(self):
        roster,source,keys=self.fixture()
        before=self.report(roster,source,[],[keys[2]])
        resumed=self.report(roster,source,[],[])
        self.assertEqual(before['rooms']['exterior']['headcount'],1)
        self.assertEqual(resumed['rooms']['exterior']['headcount'],2)
        self.assertEqual(resumed['rooms']['exterior']['active'],2)
        self.assertIn('除外される人',email_html(resumed))

    def test_invalid_configuration_fails_closed(self):
        valid={'rosterKey':'a'*64,'fromWeek':'2026-11-02','untilWeek':None}
        invalid=[{}, {'schema':1,'exclusions':[dict(valid,rosterKey='person@example.com')]},
                 {'schema':1,'exclusions':[dict(valid,fromWeek='2026-11-05')]},
                 {'schema':1,'exclusions':[dict(valid,untilWeek='2026-11-02')]},
                 {'schema':1,'exclusions':[valid,valid]}]
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'exclusions.json'
            self.assertEqual(load_exclusions(path),[])
            for value in invalid:
                path.write_text(json.dumps(value),encoding='utf8')
                with self.assertRaises(ValueError):load_exclusions(path)
            path.write_text(json.dumps({'schema':1,'exclusions':[valid]}),encoding='utf8')
            self.assertEqual(load_exclusions(path),[valid])


if __name__=='__main__':unittest.main()
