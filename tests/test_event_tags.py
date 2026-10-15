import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

import auto_update_daily_news as publisher
from dailynews.collection_digest import published_news
from dailynews.event_tags import LABELS, browser_script, derive

ROOT = Path(__file__).resolve().parents[1]

SOURCE_CASES = [
    (dict(title='VWの新コックピット', date='2026-10-15', url='https://news.yahoo.co.jp/articles/vw',
          originalDesc='助手席ディスプレイを採用。【関連リンク】シトロエンをパリモーターショー2026で公開'), []),
    (dict(title='防雪フィルムを発売', date='2026-10-15', url='https://news.yahoo.co.jp/articles/film',
          originalDesc='ヘッドライトに貼り付ける製品。【関連リンク】パリモーターショー2026の展示車'), []),
    (dict(title='限定車にサテンフィルム', date='2026-10-15', url='https://news.yahoo.co.jp/articles/satin',
          originalDesc='外装フィルムの限定仕様。【関連記事】パリモーターショー2026'), []),
    (dict(title='Avatr 06', date='2026-10-15', url='https://cnevpost.com/2026/10/15/avatr/',
          originalDesc='Updated seats. Related Posts Deepal at the Paris Motor Show 2026'), []),
    (dict(title='インドへの投入計画', date='2026-10-15', url='https://www.autocarindia.com/launches',
          originalDesc='Speaking at the 2026 Paris Motor Show, the executive described the launch plan.'), [LABELS[1]]),
    (dict(title='小型車の軽量化が課題', date='2026-10-15', url='https://www.autocar.co.uk/concept',
          originalDesc='The concept made an appearance at the Paris motor show.'), [LABELS[1]]),
    (dict(title='新材料', date='2026-10-15', url='https://cnevpost.com/material/',
          originalDesc='Shown at CEATEC 2026. Related Posts Paris Motor Show 2026'), [LABELS[0]]),
]


class EventTagsTests(unittest.TestCase):
    def test_recommendations_are_not_event_evidence_but_interviews_are(self):
        for item, expected in SOURCE_CASES:
            with self.subTest(title=item['title']):
                self.assertEqual(derive(item), expected)

    def test_event_aliases_and_years(self):
        for text in ['CEATEC2026', 'ＣＥＡＴＥＣ ２０２６', 'Japan Mobility Show Bizweek 2026', 'JMS2026', 'シーテック2026']:
            self.assertEqual(derive(dict(title=text)), [LABELS[0]])
        for text in ['2026 Paris Motor Show', 'Mondial de l’Auto 2026', '巴黎国际车展2026', 'パリ・モーターショー2026']:
            self.assertEqual(derive(dict(title=text)), [LABELS[1]])
        self.assertEqual(derive(dict(title='パリモーターショーで2027年型車を公開', date='2026-10-15')), [LABELS[1]])
        self.assertEqual(derive(dict(title='CEATECに出展', date='2026-10-15')), [LABELS[0]])
        self.assertEqual(derive(dict(title='CEATECに出展', date='2027-10-15')), [])

    def test_historic_events_and_ideas_are_not_current_events(self):
        for text in ['2025年秋のジャパンモビリティショー', '2023年のジャパンモビリティショー', 'Paris Motor Show 2024', '16年前のパリモーターショー', 'Paris motor show 16 years ago', '昨年のCEATEC', 'JMSBroker software']:
            self.assertEqual(derive(dict(title=text, date='2026-10-15')), [], text)
        self.assertEqual(derive(dict(title='新しいセンサー', date='2026-10-15', tags=LABELS, idea='CEATEC2026に出展しよう')), [])
        self.assertEqual(derive(dict(title='パリモーターショー', desc='Paris motor show 16 years ago', date='2026-10-15')), [])

    def test_publisher_both_editions_preserves_original_evidence_and_genres(self):
        item=dict(title='HMIと冷却を改善', desc='車載システム', originalTitle='CEATEC 2026', date='2026-10-15')
        for edition, genre in [('interior', 'HMI'), ('exterior', '冷却')]:
            with patch.object(publisher, 'EDITION', publisher.get_edition(edition)):
                tags=publisher.generate_item_tags(item)
                self.assertEqual(tags[0], LABELS[0])
                self.assertIn(genre, tags)

    def test_python_browser_parity_on_archives_and_edge_cases(self):
        self.assertEqual((ROOT/'dailynews_event_tags.js').read_text(encoding='utf8'), browser_script())
        samples=[dict(title=s, date='2026-10-15') for s in ['CEATEC2026', '2025年秋のジャパンモビリティショー', '2023年のJMS', '16年前のパリモーターショー', 'Mondial de l’Auto 2026', 'Paris motor show 16 years ago', 'CEATEC2026とParis Motor Show 2026']]
        samples += published_news(ROOT/'news_data.js') + published_news(ROOT/'content/exterior/news_data.js')
        samples += [item for item, _ in SOURCE_CASES]
        code="""const fs=require('fs'),vm=require('vm'),window={};vm.runInNewContext(fs.readFileSync('dailynews_event_tags.js','utf8'),{window,URL});const items=JSON.parse(fs.readFileSync(0,'utf8'));process.stdout.write(JSON.stringify(items.map(i=>window.DailyNewsEventTags.derive(i))));"""
        result=subprocess.run(['node','-e',code],input=json.dumps(samples),cwd=ROOT,capture_output=True,text=True,encoding='utf8',check=True)
        self.assertEqual(json.loads(result.stdout), [derive(item) for item in samples])


if __name__ == '__main__':
    unittest.main()
