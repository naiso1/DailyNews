"""Offline regression tests for RSS sources and article extraction."""

import csv
import json
from pathlib import Path
import unittest
from unittest.mock import Mock

import requests

from verify_rss_sources import collection_helpers

ROOT = Path(__file__).resolve().parents[1]
COLLECTION = ROOT / "\u30cb\u30e5\u30fc\u30b9\u53ce\u96c6"


class ArticleExtractionTests(unittest.TestCase):
    def setUp(self):
        self.env = collection_helpers(requests.Session())
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


class SourceConfigurationTests(unittest.TestCase):
    def test_csv_and_public_directory_match_collection_config(self):
        config = json.loads((COLLECTION / "department_settings.json").read_text(encoding="utf-8-sig"))["interior"]["rss_feeds"]
        with (COLLECTION / "rss_feed_list.csv").open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.reader(handle))[1:]
        self.assertEqual(rows, [[f["country"], f["name"], f["url"]] for f in config])
        source = (ROOT / "source_list_data.js").read_text(encoding="utf-8")
        published = json.loads(source.split("window.DAILYNEWS_CONFIGURED_SOURCES = ", 1)[1].strip().removesuffix(";"))
        self.assertEqual(published, [{"country": f["country"], "name": f["name"], "rssUrl": f["url"]} for f in config])
        self.assertEqual(len({f["url"] for f in config}), len(config))


if __name__ == "__main__":
    unittest.main()
