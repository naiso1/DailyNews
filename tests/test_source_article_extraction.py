"""Isolated regressions for bodies used by image-bearing RSS sources."""
from contextlib import redirect_stdout
import io
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import requests
from verify_rss_sources import collection_helpers


class SourceArticleExtractionTests(unittest.TestCase):
    def setUp(self):
        self.env = collection_helpers(requests.Session())

    def fetch(self, url, html, edition="interior"):
        self.env["EDITION"] = SimpleNamespace(id=edition)
        response = Mock(status_code=200, content=html.encode("utf-8"),
                        headers={"Content-Type": "text/html"})
        response.text = html.encode("utf-8").decode("latin1") if "gasgoo.com" in url else html
        self.env["requests"].get = Mock(return_value=response)
        with redirect_stdout(io.StringIO()):
            return self.env["fetch_article_text"](url)

    def test_gasgoo_both_editions_use_body_and_utf8_not_legacy_cache(self):
        url = "https://auto.gasgoo.com/news/story.shtml"
        self.env["_article_text_cache"][url] = "old corrupt body"
        html = '<meta charset="utf-8"><body>采购菜单<div id="ArticleContent">新材料改善汽车内饰触感。</div>无关页尾</body>'
        for edition in ("interior", "exterior"):
            with self.subTest(edition=edition):
                self.assertEqual(self.fetch(url, html, edition), "新材料改善汽车内饰触感。")

    def test_gasgoo_does_not_use_navigation_when_body_is_absent(self):
        self.assertEqual(self.fetch("https://auto.gasgoo.com/news/missing.shtml",
                                    '<meta charset="utf-8"><body>采购项目导航菜单</body>'), "")

    def test_gasgoo_does_not_accept_access_denied_as_article(self):
        self.assertEqual(self.fetch("https://auto.gasgoo.com/news/blocked.shtml",
                                    '<title>Access Denied</title><div id="ArticleContent">Access Denied</div>'), "")

    def test_uki_publications_skip_navigation_article_cards(self):
        html = '<nav><article>Old magazine</article></nav><article class="type-post"><div class="entry-content">Expected test equipment story.</div></article>'
        for host in ("automotiveinteriorsworld.com", "automotivetestingtechnologyinternational.com"):
            with self.subTest(host=host):
                self.assertEqual(self.fetch(f"https://www.{host}/news/story.html", html),
                                 "Expected test equipment story.")
                self.assertEqual(self.fetch(f"https://www.{host}/news/missing.html",
                                            "<article>Old magazine</article>"), "")

    def test_plastics_engineering_uses_material_story_not_featured_card(self):
        html = '<article>Featured unrelated story</article><div class="post-content">Additives improve polymer surface performance.</div>'
        self.assertEqual(self.fetch("https://www.plasticsengineering.org/news/story/", html),
                         "Additives improve polymer surface performance.")


if __name__ == "__main__":
    unittest.main()
