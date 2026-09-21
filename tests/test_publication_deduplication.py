"""Publishing defenses and retained source references after editorial consolidation."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import auto_update_daily_news as publisher
from dailynews.collection_digest import parse_published_news, published_row


def news_text(items):
    return 'window.LOADED_NEWS_DATA = ' + json.dumps(items, ensure_ascii=False) + ';'


class PublicationDeduplicationTests(unittest.TestCase):
    def test_tracking_variants_merge_but_query_article_ids_remain_distinct(self):
        items = [dict(url='https://example.com/read?id=1&utm_source=rss', title='第一報', relatedUrls=['https://other.test/a']),
                 dict(url='https://example.com/read?id=1&utm_source=email', title='転載', relatedUrls=['https://other.test/b']),
                 dict(url='https://example.com/read?id=2', title='別記事')]
        original = copy.deepcopy(items)
        selected = publisher.unique_publication_items(items)
        self.assertEqual(len(selected), 2)
        self.assertEqual(selected[0]['title'], '第一報')
        self.assertEqual(selected[0]['relatedUrls'], ['https://other.test/a', 'https://other.test/b'])
        self.assertEqual(items, original)

    def test_batch_related_source_graph_merges_even_when_a_later_row_bridges_groups(self):
        items = [dict(url='https://x.test/a', title='代表', relatedUrls=['https://x.test/b']),
                 dict(url='https://x.test/c', title='別経路', relatedUrls=['https://x.test/d']),
                 dict(url='https://x.test/b?utm_source=rss', title='橋渡し', relatedUrls=['https://x.test/c'])]
        original = copy.deepcopy(items)
        selected = publisher.unique_publication_items(items)
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]['title'], '代表')
        self.assertEqual(selected[0]['relatedUrls'], ['https://x.test/b', 'https://x.test/c', 'https://x.test/d'])
        self.assertEqual(items, original)

    def test_new_primary_with_known_related_url_uses_existing_article_identity(self):
        text = news_text([dict(id='jp1', url='https://x.test/a', date='2026-09-20')])
        item = dict(url='https://x.test/new-copy', relatedUrls=['https://x.test/a'])
        known = set(publisher.publication_url_id_map(text))
        self.assertTrue(known.intersection(publisher.publication_item_url_keys(item)))
        merged = publisher.merge_related_sources(text, [item])
        self.assertEqual(publisher.publication_url_id_map(merged)['https://x.test/new-copy'], 'jp1')
        self.assertEqual(len(parse_published_news(merged)), 1)

    def test_legacy_tabs_and_related_sources_survive_history_round_trip(self):
        text = 'window.LOADED_NEWS_DATA = [{id:"jp1",url:"https://x.test/a",date:"2026-09-20",title:"a\tb",relatedUrls:["https://y.test/b"]}];'
        parsed = parse_published_news(text)
        self.assertEqual(parsed[0]['title'], 'a\tb')
        self.assertEqual(parsed[0]['relatedUrls'], ['https://y.test/b'])
        self.assertEqual(json.loads(published_row(parsed[0])['関連URL']), ['https://y.test/b'])

    def test_existing_primary_and_related_urls_resolve_without_reassigning_ids(self):
        articles = [dict(id='jp2', url='https://copy.test/a', date='2026-09-20', duplicateOf='jp1'),
                    dict(id='jp1', url='https://source.test/a', date='2026-09-18', relatedUrls=['https://gallery.test/a']),
                    dict(id='jp3', url='https://broken.test/a', date='2026-09-20', duplicateOf='missing'),
                    dict(id='jp4', url='https://cycle.test/a', date='2026-09-20', duplicateOf='jp5'),
                    dict(id='jp5', url='https://cycle.test/b', date='2026-09-20', duplicateOf='jp4')]
        mapped = publisher.publication_url_id_map(news_text(articles))
        self.assertEqual(set(mapped.values()), {'jp1'})
        self.assertEqual(mapped['https://copy.test/a'], 'jp1')
        self.assertEqual(mapped['https://gallery.test/a'], 'jp1')

    def test_same_issue_retry_merges_source_urls_without_changing_copy_or_history(self):
        text = 'window.LOADED_NEWS_DATA = [{id:"jp2",url:"https://x.test/new",date:"2026-09-20",title:"現行",desc:"現在の本文。"},\n{id:"jp1",url:"https://x.test/old",date:"2026-09-17",title:"履歴",desc:"元の本文。"}];'
        items = [dict(url='https://x.test/new?utm_source=rss', relatedUrls=['https://y.test/copy', 'javascript:alert(1)', 'https://y.test/copy?utm_source=rss'])]
        merged = publisher.merge_related_sources(text, items)
        after = parse_published_news(merged)
        self.assertEqual(after[0]['relatedUrls'], ['https://y.test/copy'])
        self.assertEqual(after[1], parse_published_news(text)[1])
        self.assertEqual(after[0]['desc'], '現在の本文。')
        self.assertEqual(publisher.merge_related_sources(merged, items), merged)

    def test_retry_preserves_related_sources_in_json_quoted_fields(self):
        text = news_text([dict(id='jp1', url='https://x.test/a', date='2026-09-20',
                              relatedUrls=['https://first.test/a'])])
        merged = publisher.merge_related_sources(text, [dict(url='https://x.test/a',
                                      relatedUrls=['https://second.test/a'])])
        self.assertEqual(merged.count('relatedUrls'), 1)
        self.assertEqual(parse_published_news(merged)[0]['relatedUrls'],
                         ['https://first.test/a', 'https://second.test/a'])

    def test_retry_via_related_url_keeps_new_sources_on_representative(self):
        text = news_text([dict(id='jp1', url='https://x.test/a', date='2026-09-20',
                              title='代表', relatedUrls=['https://x.test/b'])])
        merged = publisher.merge_related_sources(text, [dict(url='https://x.test/b?utm_source=rss',
                                                            relatedUrls=['https://x.test/c'])])
        article = parse_published_news(merged)[0]
        self.assertEqual(article['relatedUrls'], ['https://x.test/b', 'https://x.test/c'])
        self.assertEqual(article['title'], '代表')
        self.assertEqual(publisher.publication_url_id_map(merged)['https://x.test/c'], 'jp1')

    def test_alias_chain_sources_merge_to_representative_without_changing_alias_records(self):
        articles = [dict(id='jp1', url='https://x.test/a', date='2026-09-18', title='代表'),
                    dict(id='jp2', url='https://x.test/b', date='2026-09-19', duplicateOf='jp1', title='出典B'),
                    dict(id='jp3', url='https://x.test/c', date='2026-09-20', duplicateOf='jp2',
                         title='出典C', relatedUrls=['https://x.test/d']),
                    dict(id='jp4', url='https://x.test/other', date='2026-09-20', title='独立記事')]
        text = news_text(articles)
        items = [dict(url='https://x.test/c', relatedUrls=['https://x.test/e'])]
        merged = publisher.merge_related_sources(text, items)
        after = parse_published_news(merged)
        self.assertEqual(set(after[0]['relatedUrls']), {'https://x.test/b', 'https://x.test/c', 'https://x.test/d', 'https://x.test/e'})
        self.assertEqual(after[1:], articles[1:])
        self.assertEqual(publisher.merge_related_sources(merged, items), merged)

    def test_normalized_fix_updates_correct_object_and_preserves_url_identity(self):
        articles = [dict(id='jp1', url='https://x.test/read?id=1&source=rss', date='2026-09-18',
                         title='旧タイトル', desc='旧本文。', source='source', relatedUrls=['https://copy.test/a']),
                    dict(id='jp2', url='https://x.test/read?id=2', date='2026-09-20', title='別記事', desc='別の本文。')]
        text = news_text(articles)
        fixed = publisher.fix_existing_entries(text, [dict(url='https://x.test/read?id=1', title='訂正タイトル',
                                                          desc='訂正本文「引用」。')])
        after = parse_published_news(fixed)
        self.assertEqual(after[0]['title'], '訂正タイトル')
        self.assertEqual(after[0]['desc'], '訂正本文「引用」。')
        for field in ('id', 'url', 'date', 'relatedUrls'):
            self.assertEqual(after[0][field], articles[0][field])
        self.assertEqual(after[1], articles[1])

    def test_fix_does_not_replace_representative_copy_with_a_different_source(self):
        text = news_text([dict(id='jp1', url='https://x.test/a', date='2026-09-20',
                              title='代表', desc='原文。', relatedUrls=['https://x.test/b'])])
        self.assertEqual(publisher.fix_existing_entries(text, [dict(url='https://x.test/b', title='別出典の訂正')]), text)

    def test_consolidation_keeps_existing_citations_but_never_accepts_unknown_ids(self):
        items = [dict(country='jp', date='2026-09-20', url='https://x.test/new', newsId='jp2')]
        published = [dict(id='jp1', country='jp', date='2026-09-18', url='https://x.test/original'),
                     dict(id='jp2', country='jp', date='2026-09-20', digestDate='2026-09-20', url='https://x.test/new'),
                     dict(id='jp3', country='jp', date='2026-09-20', digestDate='2026-09-20', url='https://x.test/copy', duplicateOf='jp1')]
        text = '''window.DAILY_INSIGHTS = [{date: "2026-09-20",analysis:{jp:"形状を検討する[jp3]。"},ideas:{jp:[
        {id:1,img:"images/a.jpg",title:"案1",desc:"案[jp3]",sourceNewsIds:["jp3"]},
        {id:2,img:"images/b.jpg",title:"案2",desc:"案[jp2]",sourceNewsIds:["jp2"]}]}}];'''
        self.assertTrue(publisher.exterior_existing_insights_complete(text, '2026-09-20', items, published))
        self.assertFalse(publisher.exterior_existing_insights_complete(text.replace('jp3', 'jp999'), '2026-09-20', items, published))
        published[-1]['duplicateOf'] = 'missing'
        self.assertFalse(publisher.exterior_existing_insights_complete(text, '2026-09-20', items, published))


if __name__ == '__main__':
    unittest.main()
