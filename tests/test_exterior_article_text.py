"""Regression coverage for source evidence encoding and blocked-page handling."""
from contextlib import redirect_stdout
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ニュース収集"))
from dailynews.article_text import ARTICLE_TEXT_VERSION, decode_html, unusable_text


class ArticleDecodingTests(unittest.TestCase):
    def test_utf8_japanese_and_chinese_ignore_requests_default_latin1(self):
        for body in ("新しいグリルを発表した。", "汽车外饰与空气动力学。"):
            html = f'<meta charset="utf-8"><article>{body}</article>'
            self.assertEqual(decode_html(html.encode("utf-8"), "text/html"), html)

    def test_gb18030_meta_and_explicit_http_header(self):
        html = '<meta http-equiv="Content-Type" content="text/html; charset=GB18030"><article>汽车外饰新技术。</article>'
        self.assertEqual(decode_html(html.encode("gb18030"), "text/html"), html)
        plain = "<article>汽车外饰新技术。</article>"
        self.assertEqual(decode_html(plain.encode("gb18030"), "text/html; charset=gb18030"), plain)

    def test_saved_mojibake_is_invalid_but_real_chinese_is_not(self):
        text = "汽车外饰与空气动力学的新技术。" * 8
        self.assertTrue(unusable_text(text.encode("utf-8").decode("latin1")))
        self.assertFalse(unusable_text(text))


class ArticleFetchingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global collector
        import google_search_script as collector

    def setUp(self):
        collector.configure_edition("exterior")

    def tearDown(self):
        collector.configure_edition("interior")

    def fetch(self, url, html, encoding="utf-8"):
        response = Mock(status_code=200, content=html.encode(encoding), headers={"Content-Type": "text/html"})
        response.text = html.encode(encoding).decode("latin1")
        with patch.object(collector.requests, "get", return_value=response), redirect_stdout(io.StringIO()):
            return collector.fetch_article_text(url)

    def test_correct_short_article_is_retained_and_navigation_removed(self):
        result = self.fetch("https://example.com/short", '<meta charset="utf-8"><main><nav>購買・ログイン</nav><p>新しいグリルを発表した。</p></main>')
        self.assertEqual(result, "新しいグリルを発表した。")

    def test_gasgoo_body_excludes_menu_and_honors_document_encoding(self):
        result = self.fetch("https://auto.gasgoo.com/news/test.shtml", '<meta charset="utf-8"><body>采购项目导航<div id="ArticleContent">四部门开展道路机动车辆生产一致性和质量提升专项行动。</div>页尾菜单</body>')
        self.assertEqual(result, "四部门开展道路机动车辆生产一致性和质量提升专项行动。")

    def test_denial_and_bot_pages_never_enter_article_cache(self):
        for index, html in enumerate((
            "<title>Access Denied</title><h1>Access Denied</h1><p>You don't have permission to access this page.</p>",
            "<title>Just a moment...</title><p>Enable JavaScript and cookies to continue</p>",
            "<title>Verify you are human</title><main>Please complete the CAPTCHA.</main>",
        )):
            url = f"https://example.com/blocked/{index}"
            self.assertEqual(self.fetch(url, html), "")
            self.assertNotIn((ARTICLE_TEXT_VERSION, url), collector._article_text_cache)

    def test_legacy_body_cache_is_not_reused_by_exterior(self):
        url = "https://example.com/updated"
        collector._article_text_cache[url] = "Access Denied"
        self.assertEqual(self.fetch(url, '<meta charset="utf-8"><article>正しい記事本文です。</article>'), "正しい記事本文です。")

    def test_interior_retains_existing_response_and_cache_behavior(self):
        collector.configure_edition("interior")
        url = "https://example.com/interior"
        response = Mock(status_code=200, text="<article>Existing interior text.</article>")
        with patch.object(collector.requests, "get", return_value=response), redirect_stdout(io.StringIO()):
            self.assertEqual(collector.fetch_article_text(url), "Existing interior text.")
        self.assertEqual(collector._article_text_cache[url], "Existing interior text.")


if __name__ == "__main__":
    unittest.main()
