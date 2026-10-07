"""Source mismatches must be withheld, and weak ideas must not stop publication."""
import copy
import json
from pathlib import Path
import sys
import unittest
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dailynews import idea_quality as q


class IdeaQualityTests(unittest.TestCase):
    def setUp(self):
        self.sources = [{"newsId": "cn94", "title": "S07の黒いドアハンドル", "desc": "黒塗装のハンドルを採用。",
                         "originalDesc": "The S07 has black painted door handles and a dedicated bumper."}]
        self.idea = {"title": "交換式ハンドルカバー", "sourceFact": "S07は黒塗装のドアハンドルを採用している。",
                     "proposal": "本体を共通にして外観カバーを交換できる構造を提案する。",
                     "benefit": "傷の補修時に交換する部品を減らすことを狙う。",
                     "verification": "一体構造と部品費・交換時間を比較する。",
                     "sourceNewsIds": ["cn94"], "sourceQuotes": [{"sourceId": "cn94", "quote": "black painted door handles"}]}

    def review(self, **changes):
        return json.dumps({"reviews": [{"index": 0, **dict.fromkeys(q.CHECKS, True), "reason": "対応を確認", **changes}]})

    def test_valid_idea_retains_exact_source_and_independent_review(self):
        calls = []
        def model(prompt):
            calls.append(prompt)
            return self.review()
        passed, failures = q.review_candidates([self.idea], self.sources, "exterior", model, json.loads)
        self.assertEqual(len(passed), 1)
        self.assertFalse(failures)
        self.assertEqual(passed[0]["sourceNewsIds"], ["cn94"])
        self.assertTrue(q.is_reviewed(passed[0], self.sources))
        self.assertIn("black painted door handles", calls[0])

    def test_unknown_source_is_never_replaced_by_available_source(self):
        wrong = {**self.idea, "sourceNewsIds": ["eu1744"]}
        passed, failures = q.review_candidates([wrong], self.sources, "exterior", lambda _: self.fail("must not call model"), json.loads)
        self.assertFalse(passed)
        self.assertIn("別IDへの補正は禁止", failures[0]["reason"])
        self.assertEqual(wrong["sourceNewsIds"], ["eu1744"])

    def test_existing_id_with_unrelated_story_fails_semantic_check(self):
        passed, failures = q.review_candidates([self.idea], self.sources, "exterior", lambda _: self.review(sourceMatch=False, reason="本文と出典が異なる"), json.loads)
        self.assertFalse(passed)
        self.assertEqual(failures[-1]["reason"], "本文と出典が異なる")

    def test_wrong_test_method_and_unconfirmed_effect_are_withheld(self):
        for check in ("testMatchesPurpose", "hypothesisClearlyMarked", "logicalConnection", "scopeMatch", "concreteProposal"):
            with self.subTest(check=check):
                passed, _ = q.review_candidates([self.idea], self.sources, "exterior", lambda _: self.review(**{check: False}), json.loads)
                self.assertFalse(passed)

    def test_fabricated_quote_and_conflicting_embedded_id_are_rejected(self):
        for changes in ({"sourceQuotes": [{"sourceId": "cn94", "quote": "high strength safety confirmed"}]},
                        {"proposal": "電池の開発拠点[eu1744]を利用する案。"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                q.prepare({**self.idea, **changes}, self.sources)

    def test_string_true_missing_or_duplicate_review_cannot_pass(self):
        results = [self.review(sourceMatch="true"), '{"reviews":[]}', 'invalid',
                   json.dumps({"reviews": [json.loads(self.review())["reviews"][0]]*2})]
        for result in results:
            with self.subTest(result=result):
                passed, _ = q.review_candidates([self.idea], self.sources, "exterior", lambda _: result, json.loads)
                self.assertFalse(passed)

    def test_content_or_source_change_invalidates_retained_review(self):
        passed, _ = q.review_candidates([self.idea], self.sources, "exterior", lambda _: self.review(), json.loads)
        changed = copy.deepcopy(passed[0]); changed["desc"] += "実現済み。"
        self.assertFalse(q.is_reviewed(changed, self.sources))
        self.assertFalse(q.is_reviewed(passed[0], [{**self.sources[0], "originalDesc": "A different article"}]))

    def test_bounded_failures_return_zero_with_audit_instead_of_throwing(self):
        calls = []
        def model(prompt):
            calls.append(prompt)
            return '{"ideas":[]}'
        kept, audit = q.generate_country("exterior", "2026-10-05", "cn", self.sources, [], [], model, json.loads, lambda a, h, n: a[:n])
        self.assertEqual(kept, [])
        self.assertEqual(len(calls), 4)
        self.assertEqual(audit["withheld"], 2)

    def test_third_attempt_can_fill_second_slot_without_changing_accepted_idea(self):
        retained,_=q.review_candidates([self.idea],self.sources,'exterior',lambda _:self.review(),json.loads)
        before=copy.deepcopy(retained[0])
        second={**self.idea,'title':'排水溝付きハンドルカバー',
            'proposal':'カバー下側に排水溝を設ける案を提案する。',
            'benefit':'雨の後に残る水滴を減らすことを狙う。',
            'verification':'溝あり・なしで散水後の残水量を比較する。'}
        generation_calls=[]
        def model(prompt):
            if 'あなたは自動車部品の企画レビュー担当' in prompt:return self.review()
            generation_calls.append(prompt)
            return json.dumps({'ideas':[second] if len(generation_calls)==3 else []},ensure_ascii=False)
        kept,audit=q.generate_country('exterior','2026-10-05','cn',self.sources,[],retained,
                                     model,json.loads,lambda a,h,n:a[:n])
        self.assertEqual(len(kept),2)
        self.assertEqual(audit['attempts'],3)
        self.assertEqual(kept[0],before)
        self.assertIn('異なる部位・仕組み・利用場面',generation_calls[-1])

    def test_retry_uses_untried_articles_before_reusing_first_pair(self):
        sources=[{**self.sources[0],'newsId':'cn'+str(94+i)} for i in range(6)]
        loaded=[]
        q.generate_country('exterior','2026-10-05','cn',sources,[],[],lambda _: '{"ideas":[]}',
                           json.loads,lambda a,h,n:a[:n],source_loader=lambda items:loaded.append([s['newsId'] for s in items]))
        self.assertEqual(loaded[:3],[['cn94','cn95'],['cn96','cn97'],['cn98','cn99']])

    def test_cargo_fact_can_support_an_interior_storage_idea(self):
        source={'newsId':'eu1','originalDesc':'The electric car offers a 441-litre boot.'}
        self.assertIn('441-litre boot',q.focus_evidence(source,'interior'))

    def test_exterior_lighting_glass_roof_and_hood_are_component_evidence(self):
        for text in ['The car uses smiling taillights.', 'A glass roof blocks UV light.',
                     'The logo is fitted to the bonnet.', 'The mirror sits on a narrow arm.',
                     '細いテールランプとガラスルーフを採用する。']:
            with self.subTest(text=text):
                self.assertIn(text,q.focus_evidence({'originalDesc':text},'exterior'))

    def test_irrelevant_first_sources_do_not_exhaust_generation_attempts(self):
        sources=[{'newsId':f'cn{i}','originalDesc':'The manufacturer announced quarterly sales.'} for i in range(8)] + self.sources
        calls=[]
        def model(prompt):
            calls.append(prompt)
            return self.review() if 'あなたは自動車部品の企画レビュー担当' in prompt else json.dumps({'ideas':[self.idea]},ensure_ascii=False)
        kept,audit=q.generate_country('exterior','2026-10-06','cn',sources,[],[],model,json.loads,lambda a,h,n:a[:n],max_attempts=1)
        self.assertEqual(len(kept),1)
        self.assertEqual(audit['attempts'],1)
        self.assertEqual(audit['sourcesChecked'],9)
        self.assertEqual(len(calls),2)

    def test_failed_idea_is_repaired_and_reviewed_without_changing_valid_sibling(self):
        second={**self.idea,'title':'排水溝付きハンドルカバー',
                'proposal':'カバー下面に排水溝を設ける案を提案する。'}
        bad={**second,'proposal':'カバー下面に排水溝を設けた。'}
        calls=[]
        def model(prompt):
            calls.append(prompt)
            if 'あなたは自動車部品の企画レビュー担当' in prompt:return self.review()
            if '企画案の点検で指摘された箇所を修正する' in prompt:
                self.assertIn('排水溝付きハンドルカバー',prompt)
                self.assertNotIn('交換式ハンドルカバー',prompt)
                return json.dumps({'ideas':[second]},ensure_ascii=False)
            return json.dumps({'ideas':[self.idea,bad]},ensure_ascii=False)
        kept,audit=q.generate_country('exterior','2026-10-06','cn',self.sources,[],[],model,json.loads,lambda a,h,n:a[:n],max_attempts=1)
        self.assertEqual(len(kept),2)
        self.assertEqual(kept[0]['proposal'],self.idea['proposal'])
        self.assertTrue(all(q.is_reviewed(i,self.sources) for i in kept))
        self.assertEqual(audit['repairAttempts'],1)
        self.assertEqual(len(calls),4)

    def test_unsuccessful_repair_cannot_bypass_checks_and_is_bounded(self):
        def model(prompt):
            if 'あなたは自動車部品の企画レビュー担当' in prompt:return self.review(testMatchesPurpose=False,reason='確認方法が目的と不一致')
            return json.dumps({'ideas':[self.idea]},ensure_ascii=False)
        kept,audit=q.generate_country('exterior','2026-10-06','cn',self.sources,[],[],model,json.loads,lambda a,h,n:a[:n],max_attempts=2)
        self.assertFalse(kept)
        self.assertEqual(audit['attempts'],2)
        self.assertEqual(audit['repairAttempts'],2)

    def test_valid_sibling_survives_one_rejected_idea(self):
        bad = {**self.idea, "sourceNewsIds": ["cn999"]}
        passed, _ = q.review_candidates([bad, self.idea], self.sources, "exterior", lambda _: self.review(), json.loads)
        self.assertEqual(len(passed), 1)

    def test_distinct_references_can_change_order_without_invalidating_review(self):
        second = {"newsId": "cn95", "title": "別記事", "desc": "別の記事の具体的な根拠内容です。"}
        raw = {**self.idea, "sourceNewsIds": ["cn95", "cn94"], "sourceQuotes": self.idea["sourceQuotes"] + [{"sourceId": "cn95", "quote": second["desc"]}]}
        passed, _ = q.review_candidates([raw], [second, *self.sources], "exterior", lambda _: self.review(), json.loads)
        self.assertTrue(q.is_reviewed(passed[0], [*self.sources, second]))

    def test_analysis_only_prompt_has_no_random_product_requirement(self):
        import auto_update_daily_news as updater
        prompt = updater.make_country_prompt("2026-10-05", "cn", self.sources, "")
        self.assertNotIn("今回の発想切り口", prompt)
        self.assertNotIn("2件目）は豊田合成", prompt)
        self.assertIn("ideasは別工程", prompt)

    def test_english_fact_and_asserted_benefit_cannot_be_published(self):
        for changes in ({"sourceFact": "Black painted door handles are fitted."},
                        {"proposal": "カバーを採用済み。"}, {"benefit": "コストを削減した。"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                q.prepare({**self.idea, **changes}, self.sources)

    def test_future_prototype_is_a_proposal_but_completed_prototype_is_not(self):
        future={**self.idea,'proposal':'本体を共通にして外観カバーを交換できる構造を試作する。'}
        prepared=q.prepare(future,self.sources)
        self.assertEqual(prepared['proposal'],future['proposal'])
        with self.assertRaisesRegex(ValueError,'採用実績'):
            q.prepare({**future,'proposal':future['proposal'].replace('試作する','試作した')},self.sources)

    def test_original_fetch_is_cached_and_failures_do_not_repeat(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'evidence.json'
            item={"newsId":"cn94", "date":"2026-10-05", "url":"https://example.com/article", "originalDesc":"Short RSS snippet"}
            with patch('ニュース収集.source_highlights.make_session') as session, \
                 patch('ニュース収集.source_highlights.fetch_html',return_value=('html',item['url'])) as fetch, \
                 patch('ニュース収集.source_highlights.article_paragraphs',return_value=['The door handles are black. '*10]):
                q.enrich_originals([item],target,fetch_missing=True)
                self.assertIn('door handles',item['originalDesc'])
                retry={**item,'originalDesc':'Short RSS snippet'}
                q.enrich_originals([retry],target,fetch_missing=True)
                self.assertEqual(retry['originalDesc'],item['originalDesc'])
                self.assertEqual(fetch.call_count,1)
                session.return_value.close.assert_called_once()
            failed={**item,'url':'https://example.com/missing','originalDesc':'Short snippet'}
            with patch('ニュース収集.source_highlights.make_session'), \
                 patch('ニュース収集.source_highlights.fetch_html',side_effect=TimeoutError) as fetch:
                q.enrich_originals([failed],target,fetch_missing=True)
                q.enrich_originals([failed],target,fetch_missing=True)
                self.assertEqual(fetch.call_count,1)
                self.assertEqual(failed['originalDesc'],'Short snippet')

    def test_review_allows_explicit_new_hypothesis_without_claiming_existing_defect(self):
        prompt=q.review_prompt('exterior',[q.prepare(self.idea,self.sources)],self.sources)
        self.assertIn('その課題や需要の記載がないという理由だけでfalseにしない',prompt)
        self.assertIn('静的曲げ試験だけで共振周波数',prompt)

    def test_missing_component_evidence_makes_no_generation_call(self):
        kept,audit=q.generate_country('interior','2026-10-05','cn',
            [{'newsId':'cn1','originalDesc':'The company announced a charging station.'}],[],[],
            lambda _: self.fail('Unrelated source must not generate an idea'),json.loads,lambda a,h,n:a[:n])
        self.assertFalse(kept)
        self.assertEqual(audit['withheld'],2)

    def test_complete_analysis_allows_one_sourced_idea_but_not_wrong_reference(self):
        import auto_update_daily_news as updater
        sources = [{"newsId": "jp1", "country": "jp", "title": "グリル", "desc": "発光グリルを試作。"}]
        text = '''window.DAILY_INSIGHTS = [{date: "2026-10-05", analysis: {jp: "発光グリル[jp1]が試作された。均一性[jp1]の確認を検討する。"}, ideas: {jp: [{id: 1, img: "", title: "交換式発光枠", desc: "導光部の交換を提案する。[jp1]", sourceNewsIds: ["jp1"]}]}}];'''
        self.assertTrue(updater.exterior_existing_insights_complete(text, "2026-10-05", sources))
        self.assertFalse(updater.exterior_existing_insights_complete(text.replace('["jp1"]', '["jp999"]'), "2026-10-05", sources))


if __name__ == '__main__':
    unittest.main()
