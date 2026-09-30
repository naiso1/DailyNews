"""Verify requested genres, multilingual boundaries, and publisher/browser parity."""
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

import auto_update_daily_news as publisher
from dailynews.exterior_tags import RULES, browser_script, generate_tags

ROOT = Path(__file__).resolve().parents[1]
REQUESTED = "冷却 3Dプリンター CN/CE NV 低コスト化 バックドア フェンダー ドア ルーフ リアスポイラー ピラー フード 型内塗装 ホットスタンプ インクジェット フィルム 印刷 メッキ レーザー ミリ波 Lidar カメラ ソナー フロントエンドモジュール 軽量 アブソーバー シームレス 樹脂化 鉄との接合 塗装 歩行者保護 軽衝突 法規 アセス 自動運転 車両骨格 ADAS 走行安定 Cd値".split()


class ExteriorTagsTests(unittest.TestCase):
    def test_requested_genres_remain_individually_selectable(self):
        labels = [r['tag'] for r in RULES]
        self.assertEqual(len(labels), len(set(labels)))
        self.assertEqual(len(REQUESTED), 39)
        for label in REQUESTED:
            with self.subTest(label=label):
                self.assertIn(label, labels)
                self.assertIn(label, generate_tags(label))

    def test_abbreviations_do_not_match_inside_other_words(self):
        tags = generate_tags('Advanced CNC environment cancelled scaffolding toyota software')
        for tag in ('NV', 'CN/CE', 'Cd値', '照明・発光', 'ADAS'):
            self.assertNotIn(tag, tags)
        self.assertIn('NV', generate_tags('NVHを評価する'))
        self.assertIn('Cd値', generate_tags('Cd値0.25'))
        self.assertIn('ADAS', generate_tags('ＡＤＡＳ搭載'))
        self.assertNotIn('CN/CE', generate_tags('CE marking for equipment'))
        self.assertNotIn('Cd値', generate_tags('CD player in a concept vehicle'))

    def test_multilingual_phrases_describe_the_same_development_topics(self):
        samples = [
            ('Steel polymer joining by laser', {'鉄との接合', 'レーザー'}),
            ('Tailgate and roof made by 3D printing', {'バックドア', 'ルーフ', '3Dプリンター'}),
            ('模内涂装と热冲压、汽车尾门の轻量化', {'型内塗装', 'ホットスタンプ', 'バックドア', '軽量'}),
            ('NVH, millimetre wave radar, LiDAR and ultrasonic cameras', {'NV', 'ミリ波', 'Lidar', 'ソナー', 'カメラ'}),
            ('Euro NCAP pedestrian protection low-speed impact', {'アセス', '歩行者保護', '軽衝突'}),
            ('Carbon-neutral polymer and circular economy', {'CN/CE', '新素材'}),
        ]
        for text, expected in samples:
            self.assertTrue(expected.issubset(generate_tags(text)), text)

    def test_no_cap_silently_removes_matching_genres(self):
        tags = generate_tags(' '.join(REQUESTED))
        self.assertTrue(set(REQUESTED).issubset(tags))

    def test_publisher_uses_shared_tags_without_changing_interior(self):
        with patch.object(publisher, 'EDITION', publisher.get_edition('exterior')):
            self.assertEqual(publisher.generate_tags('NVHを評価、レーザー接合'), generate_tags('NVHを評価、レーザー接合'))
        with patch.object(publisher, 'EDITION', publisher.get_edition('interior')):
            self.assertNotIn('NV', publisher.generate_tags('NVHを評価'))
            self.assertIn('HMI', publisher.generate_tags('HMI操作を改善'))

    def test_browser_asset_and_archive_have_same_classification_as_publisher(self):
        self.assertEqual((ROOT/'dailynews_exterior_tags.js').read_text(encoding='utf-8'), browser_script())
        code = """
const fs=require('fs'),vm=require('vm'),w={}; const context={window:w};
vm.runInNewContext(fs.readFileSync('dailynews_exterior_tags.js','utf8'),context);
vm.runInNewContext(fs.readFileSync('content/exterior/news_data.js','utf8'),context);
const samples=JSON.parse(fs.readFileSync(0,'utf8'));
const api=w.DailyNewsExteriorTags;
const items=[...samples.map(title=>({title})),...w.LOADED_NEWS_DATA];
const values=items.map(item=>({text:[item.title,item.desc,item.summary].filter(Boolean).join(' '),tags:api.derive(item)}));
if(api.derive({title:'無関係な記事',tags:['NV','ADAS']}).length)throw Error('Stored tags reused as evidence');
if(!api.matches({tags:['軽量']},'軽量化')||api.matches({tags:['NV']},'N'))throw Error('Filter mismatch');
process.stdout.write(JSON.stringify(values));
"""
        samples = REQUESTED + ['invention CNC cancelled', 'ＮＶＨを評価', 'LiDARとミリ波', '钢塑连接、激光雷达']
        result = subprocess.run(['node','-e',code],cwd=ROOT,input=json.dumps(samples),text=True,encoding='utf-8',capture_output=True,check=True)
        for row in json.loads(result.stdout):
            self.assertEqual(row['tags'], generate_tags(row['text']), row['text'])


if __name__ == '__main__':
    unittest.main()
