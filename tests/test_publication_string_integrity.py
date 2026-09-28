"""Keep source text intact through JS serialization and regex insertion."""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import auto_update_daily_news as publisher
from dailynews.collection_digest import parse_published_news


class PublicationStringIntegrityTests(unittest.TestCase):
    def test_news_roundtrip_preserves_source_backslashes_and_control_characters(self):
        values = [r'ギャラリーが続きます\。', r'\n \t \1 \g<1> C:\new\test',
                  '引用 "座席" と apostrophe\'\n次行\tタブ\b\f\x00']
        for value in values:
            with self.subTest(value=value):
                block = ('{id:"jp1",url:"https://example.test/a",date:"2026-09-27",'
                         'desc:"' + publisher.js_escape(value) + '"},')
                text = publisher.append_news_items('window.LOADED_NEWS_DATA = [\n];\n',
                                                    {'2026-09-27': [block]})
                self.assertEqual(parse_published_news(text)[0]['desc'], value)

    def test_insight_roundtrip_preserves_backslashes_newlines_and_quotes(self):
        value = '考察 "引用"\n次行 ' + r'\。 \n \1 \g<1>'
        entry = '{"analysis":"' + publisher.js_escape(value) + '"}'
        output = publisher.insert_insight('window.DAILY_INSIGHTS = [\n];', entry)
        data = json.loads(output.split('=', 1)[1].strip().rstrip(';'))
        self.assertEqual(data, [{'analysis': value}])

    def test_legacy_line_separator_normalization_and_existing_history(self):
        self.assertEqual(json.loads('"' + publisher.js_escape('a\r\nb\rc\u2028d\u2029e') + '"'),
                         'a\nb\nc d e')
        previous = '{id:"jp1",url:"https://example.test/old",date:"2026-09-24",desc:"既報"},'
        text = 'window.LOADED_NEWS_DATA = [\n' + previous + '\n];\n'
        result = publisher.append_news_items(text, {'2026-09-27': [
            '{id:"jp2",url:"https://example.test/new",date:"2026-09-27",desc:"新報"},']})
        self.assertIn(previous, result)
        self.assertEqual([x['id'] for x in parse_published_news(result)], ['jp1', 'jp2'])


if __name__ == '__main__':
    unittest.main()
