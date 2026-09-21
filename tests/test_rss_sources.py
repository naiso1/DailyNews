"""Offline regression tests for RSS sources and article extraction."""

import ast
import csv
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
import xml.etree.ElementTree as ET

import feedparser
import requests

from verify_rss_sources import collection_helpers

ROOT = Path(__file__).resolve().parents[1]
COLLECTION = ROOT / "\u30cb\u30e5\u30fc\u30b9\u53ce\u96c6"


class ArticleExtractionTests(unittest.TestCase):
    def setUp(self):
        self.env = collection_helpers(requests.Session())
        self.env["EDITION"] = SimpleNamespace(id="interior")
        self.response = Mock(status_code=200)
        self.env["requests"].get = Mock(return_value=self.response)

    def test_interior_world_ignores_navigation_articles(self):
        self.response.text = '''<body><nav><article>Old magazine issue</article></nav>
          <article class="type-post"><div class="entry-content">
          <p>The cockpit has a vertical display and physical switches.</p>
          <script>Unrelated tracking script</script></div></article></body>'''
        text = self.env["fetch_article_text"]("https://www.automotiveinteriorsworld.com/news/test.html")
        self.assertEqual(text, "The cockpit has a vertical display and physical switches.")

    def test_interior_world_does_not_fall_back_to_menu_when_body_is_missing(self):
        self.response.text = "<article>Old magazine issue</article>"
        self.assertEqual(self.env["fetch_article_text"]("https://automotiveinteriorsworld.com/news/test.html"), "")

    def test_other_hosts_keep_existing_article_extraction(self):
        self.response.text = "<article><p>Expected article.</p></article><aside>Related news</aside>"
        self.assertEqual(self.env["fetch_article_text"]("https://example.com/news"), "Expected article.")

    def test_rss_html_and_media_content_keep_the_original_image_url(self):
        url = "https://example.com/photos/interior.jpg?size=large"
        for entry in ({"content": [{"value": f'<p>Cabin</p><img src="{url}">'}]},
                      {"media_content": [{"url": url, "type": "image/jpeg"}]}):
            self.assertEqual(self.env["extract_image_from_rss"](entry), url)

    def test_media_and_atom_image_shapes(self):
        url = "https://example.com/photos/interior.jpg"
        for entry in (
            {"media_thumbnail": [{"url": url}]},
            {"enclosures": [{"href": url, "type": "image/jpeg"}]},
            {"links": [{"rel": "enclosure", "href": url, "type": "image/jpeg"}]},
            {"image": {"href": url}},
            {"media_content": [{"url": url, "medium": "image"}]},
        ):
            with self.subTest(entry=entry):
                self.assertEqual(self.env["extract_image_from_rss"](entry), url)

    def test_relative_lazy_uppercase_and_entity_images(self):
        entry = {"link": "https://example.com/news/story", "content": [{
            "value": '<IMG DATA-SRC="../photos/cabin.jpg?w=1000&amp;h=700">'}]}
        self.assertEqual(self.env["extract_image_from_rss"](entry),
                         "https://example.com/photos/cabin.jpg?w=1000&h=700")
        entry["content"] = [{"value": '<img src="//cdn.example.com/cabin.jpg">'}]
        self.assertEqual(self.env["extract_image_from_rss"](entry), "https://cdn.example.com/cabin.jpg")
        entry = {"summary": '<img src="photos/cabin.jpg">'}
        self.assertEqual(self.env["extract_image_from_rss"](entry, base_url="https://example.com/feed/"),
                         "https://example.com/feed/photos/cabin.jpg")

    def test_srcset_selects_large_image_and_skips_placeholder(self):
        entry = {"link": "https://example.com/news/story", "summary":
                 '<img src="/placeholder.gif" srcset="/small.jpg 320w, /large.jpg 1200w">'}
        self.assertEqual(self.env["extract_image_from_rss"](entry), "https://example.com/large.jpg")

    def test_srcset_keeps_commas_inside_cdn_image_query(self):
        entry = {"summary": '<img srcset="https://cdn.example.com/cabin.jpg?resize=400,300 400w, '
                 'https://cdn.example.com/cabin.jpg?resize=1200,800 1200w">'}
        self.assertEqual(self.env["extract_image_from_rss"](entry),
                         "https://cdn.example.com/cabin.jpg?resize=1200,800")

    def test_gasgoo_article_directory_does_not_match_logo_marker(self):
        for directory in ("image", "1640-X"):
            url = f"https://imagecn.gasgoo.com/moblogo/News/UEditor/{directory}/20260920/6392549835697512924997573.jpg"
            with self.subTest(directory=directory):
                self.assertFalse(self.env["is_suspicious_image_url"](url))
                self.assertEqual(self.env["extract_image_from_rss"]({"image": url}), url)
        for url in (
            "https://imagecn.gasgoo.com/moblogo/News/UEditor/image/logo.jpg",
            "https://imagecn.gasgoo.com/moblogo/News/UEditor/image/placeholder.jpg",
            "https://imagecn.gasgoo.com/moblogo/other/photo.jpg",
            "https://example.com/moblogo/News/UEditor/image/photo.jpg",
            "https://imagecn.gasgoo.com.example.com/moblogo/News/UEditor/image/photo.jpg",
        ):
            with self.subTest(url=url):
                self.assertTrue(self.env["is_suspicious_image_url"](url))

    def test_video_and_invalid_images_are_not_returned(self):
        entry = {"media_content": [
            {"url": "https://example.com/video.mp4", "type": "video/mp4"},
            {"url": "https://example.com/stream", "medium": "video"},
            {"url": "https://example.com/cabin.jpg", "type": "image/jpeg"}]}
        self.assertEqual(self.env["extract_image_from_rss"](entry), "https://example.com/cabin.jpg")
        for url in ("https://example.com/video.mp4", "https://example.com/logo.jpg",
                    "javascript:alert(1)", "data:image/png;base64,abc", "https://[broken/path.jpg",
                    "https://user:password@example.com/cabin.jpg"):
            with self.subTest(url=url):
                self.assertEqual(self.env["extract_image_from_rss"]({"image": url}), "")

    def test_malformed_optional_fields_do_not_hide_a_valid_image(self):
        entry = {"links": None, "content": None, "media_content": [None],
                 "summary": '<img src="https://example.com/cabin.jpg">'}
        self.assertEqual(self.env["extract_image_from_rss"](entry), "https://example.com/cabin.jpg")


class FeedImageRequirementTests(unittest.TestCase):
    def setUp(self):
        self.env = collection_helpers(requests.Session())
        tree = ast.parse((COLLECTION / "google_search_script.py").read_text(encoding="utf-8-sig"))
        names = {"fetch_from_rss", "extract_item_image_map_from_rss_xml", "strip_expiring_params", "is_target_date"}
        nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
        self.assertEqual(len(nodes), len(names))
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "rss-fetch-test", "exec"), self.env)
        self.env.update(ET=ET, feedparser=feedparser, time=SimpleNamespace(sleep=Mock()), print=Mock(),
                        SOURCE_FETCH_COUNTS={"attempted": 0, "succeeded": 0},
                        resolve_final_url=Mock(side_effect=lambda url: url),
                        fetch_meta_description=Mock(return_value="Article summary"),
                        fetch_image_from_page=Mock(return_value="https://example.com/page.jpg"),
                        resolve_with_playwright=Mock(return_value=(None, None)),
                        choose_best_yimg_variant=Mock(side_effect=lambda url: url),
                        is_yimg_placeholder=Mock(return_value=False),
                        is_missing_url=lambda value: not value)

    def run_feed(self, items, *, required=True, dates=("2026-09-20",)):
        xml = ('<rss version="2.0"><channel><title>Test</title>' + "".join(items) + '</channel></rss>').encode()
        response = Mock(status_code=200, content=xml)
        self.env["requests"].get = Mock(return_value=response)
        feed = {"name": "Test", "url": "https://example.com/feed", "country": "米国"}
        if required:
            feed["require_feed_image"] = True
        self.env["RSS_FEEDS"] = [feed]
        return self.env["fetch_from_rss"](dates)

    @staticmethod
    def item(number, image="", published="Sun, 20 Sep 2026 10:00:00 +0000"):
        return (f'<item><title>Article {number}</title><link>https://example.com/news/{number}</link>'
                f'<pubDate>{published}</pubDate><description>Cabin materials</description>{image}</item>')

    def test_required_feed_without_image_never_scrapes_an_article(self):
        self.assertEqual(self.run_feed([self.item(1), self.item(2, '<image>https://example.com/logo.jpg</image>')]), [])
        for name in ("resolve_final_url", "fetch_meta_description", "fetch_image_from_page", "resolve_with_playwright"):
            self.env[name].assert_not_called()

    def test_existing_feed_keeps_page_image_fallback(self):
        rows = self.run_feed([self.item(1)], required=False)
        self.assertEqual(rows[0]["画像URL"], "https://example.com/page.jpg")
        self.env["fetch_image_from_page"].assert_called_once_with("https://example.com/news/1")

    def test_yahoo_item_image_is_kept_and_expiring_query_is_removed(self):
        rows = self.run_feed([self.item(1, '<image>https://news-pctr.c.yimg.jp/photo.jpg?exp=100&amp;w=800</image>')])
        self.assertEqual(rows[0]["画像URL"], "https://news-pctr.c.yimg.jp/photo.jpg")
        self.env["fetch_image_from_page"].assert_not_called()

    def test_required_feed_rejects_detected_yahoo_placeholder(self):
        self.env["is_yimg_placeholder"].return_value = True
        self.assertEqual(self.run_feed([self.item(1, '<image>https://news-pctr.c.yimg.jp/photo.jpg</image>')]), [])
        self.env["fetch_image_from_page"].assert_not_called()

    def test_date_guard_still_scans_later_valid_entries(self):
        image = '<enclosure url="https://example.com/cabin.jpg" type="image/jpeg"/>'
        rows = self.run_feed([
            self.item(1, image, published="Sat, 19 Sep 2026 10:00:00 +0000"),
            self.item(2, image, published=""), self.item(3, image), self.item(4, image)])
        self.assertEqual([row["タイトル"] for row in rows], ["Article 3", "Article 4"])
        self.assertEqual(self.env["resolve_final_url"].call_count, 2)

    def test_exterior_date_is_jst_in_isolated_helpers(self):
        self.env["EDITION"] = SimpleNamespace(id="exterior")
        image = '<enclosure url="https://example.com/cabin.jpg" type="image/jpeg"/>'
        rows = self.run_feed([self.item(1, image, published="Sat, 19 Sep 2026 17:00:00 +0000")])
        self.assertEqual(rows[0]["日付"], "2026-09-20")


class SourceConfigurationTests(unittest.TestCase):
    def test_csv_and_public_directory_match_collection_config(self):
        editions = (
            ("interior", COLLECTION / "department_settings.json", COLLECTION / "rss_feed_list.csv",
             ROOT / "source_list_data.js"),
            ("exterior", ROOT / "editions/exterior/settings.json", ROOT / "runtime/exterior/rss_feed_list.csv",
             ROOT / "content/exterior/source_list_data.js"),
        )
        for edition, config_path, csv_path, public_path in editions:
            with self.subTest(edition=edition):
                config = json.loads(config_path.read_text(encoding="utf-8-sig"))[edition]["rss_feeds"]
                # Exterior CSV is private runtime output and absent in fresh checkouts.
                if edition == "interior" or csv_path.exists():
                    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
                        rows = list(csv.reader(handle))[1:]
                    self.assertEqual(rows, [[f["country"], f["name"], f["url"]] for f in config])
                source = public_path.read_text(encoding="utf-8")
                published = json.loads(source.split("window.DAILYNEWS_CONFIGURED_SOURCES = ", 1)[1].strip().removesuffix(";"))
                self.assertEqual(published, [{"country": f["country"], "name": f["name"], "rssUrl": f["url"]} for f in config])
                self.assertEqual(len({f["url"] for f in config}), len(config))
                self.assertTrue(any(f.get("require_feed_image") is True for f in config),
                                "The new image-bearing sources must enforce RSS-native images.")


if __name__ == "__main__":
    unittest.main()
