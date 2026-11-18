"""Offline regressions: a shared word must not replace a news source."""
import ast
import difflib
from pathlib import Path
import re
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock
from urllib.parse import urlparse
from dailynews.source_policy import is_excluded_source

class ArticleSearchIdentityTests(unittest.TestCase):
    def setUp(self):
        src=Path('ニュース収集/google_search_script.py').read_text(encoding='utf-8-sig')
        names={'search_hit_matches_title','search_article_url','is_valid_article_url'}
        nodes=[n for n in ast.parse(src).body if isinstance(n,ast.FunctionDef) and n.name in names]
        self.ddgs=MagicMock()
        self.env=dict(re=re,difflib=difflib,urlparse=urlparse,DDGS_AVAILABLE=True,DDGS=self.ddgs,
                      EDITION=SimpleNamespace(id='interior'),is_excluded_source=is_excluded_source)
        exec(compile(ast.Module(body=nodes,type_ignores=[]),'article-identity','exec'),self.env)
    def test_short_dictionary_hit_does_not_match_long_headline(self):
        title='Technological Advancements Drive Growth in the Car Seat and Accessories Market - openPR.com'
        match=self.env['search_hit_matches_title']
        self.assertFalse(match(title,'technological - 英和辞典 - Linguee'))
        self.assertFalse(match(title,'Technological'))
        self.assertTrue(match(title,title.removesuffix(' - openPR.com')))
        self.ddgs.return_value.__enter__.return_value.text.return_value=[
            {'title':'technological - Linguee','href':'https://www.linguee.jp/translation/technological.html'},
            {'title':title,'href':'https://unrelated.example.com/market.html'},
            {'title':title,'href':'https://www.openpr.com/news/123/market.html'}]
        self.assertEqual(self.env['search_article_url'](title),'https://www.openpr.com/news/123/market.html')
    def test_failed_identity_resolution_leaves_url_empty(self):
        self.ddgs.return_value.__enter__.return_value.text.return_value=[{'title':'Technology','href':'https://example.com/technology'}]
        self.assertEqual(self.env['search_article_url']('Technology advances vehicle seat materials - Publisher'),'')

if __name__=='__main__':unittest.main()
