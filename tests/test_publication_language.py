"""Language regressions: offline only; no collection, LLM or live API calls."""

import ast
from collections import Counter
import csv
import importlib.util
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
COLLECTION = ROOT / "ニュース収集"
sys.path.insert(0, str(COLLECTION))
from summary_grounding import source_identifiers_match
from verify_rss_sources import collection_helpers


def anchor_helpers():
    tree = ast.parse((COLLECTION / "google_search_script.py").read_text(encoding="utf-8-sig"))
    names = {"extract_latin_source_anchors", "extract_cjk_keywords", "summary_matches_source"}
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    env = {"re": re, "Counter": Counter}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "source-anchors", "exec"), env)
    return env


class SourceAnchorTests(unittest.TestCase):
    def test_uppercase_headline_words_are_not_brand_identifiers(self):
        helpers = anchor_helpers()
        source = "WHAT AI CAN'T COPY. AI can generate almost anything, but cannot copy the gesture."
        self.assertEqual(helpers["extract_latin_source_anchors"](source), [])
        self.assertEqual(helpers["extract_latin_source_anchors"]("happy ownership electric veteran " * 3), [])

    def test_japanese_brand_spelling_matches_even_one_source_mention(self):
        helpers = anchor_helpers()
        source = "WHAT AI CAN'T COPY. Ikuo Maeda from Mazda discusses craftsmanship."
        self.assertEqual(helpers["extract_latin_source_anchors"](source), ["Mazda"])
        self.assertTrue(helpers["summary_matches_source"]("マツダ前田氏がAI時代の手仕事を語る。", source))
        self.assertFalse(helpers["summary_matches_source"]("トヨタの新型SUVを発表。", source))

    def test_model_identifiers_still_must_match(self):
        self.assertTrue(source_identifiers_match("Skynomad N90を発表。", ["Skynomad", "N90"]))
        self.assertFalse(source_identifiers_match("N900を発表。", ["N90"]))
        self.assertFalse(source_identifiers_match("別のブランドの新車。", ["Skynomad"]))


class ArticleBodyTests(unittest.TestCase):
    def setUp(self):
        self.env = collection_helpers(Mock())
        self.response = Mock(status_code=200)
        self.env["requests"].get = Mock(return_value=self.response)

    def test_auto_design_excludes_related_article_titles(self):
        self.response.text = '<article><div class="post-content">Mazda craftsmanship.</div><aside>OTHER BRANDS</aside></article>'
        self.assertEqual(self.env["fetch_article_text"]("https://autodesignmagazine.com/en/test/"), "Mazda craftsmanship.")

    def test_autocar_extracts_available_body_not_navigation(self):
        self.response.text = '<body><nav>MENU AND REVIEWS</nav><div class="field-name-body">EV charging advice.</div></body>'
        self.assertEqual(self.env["fetch_article_text"]("https://www.autocar.co.uk/car-news/test"), "EV charging advice.")


class PublicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("publisher_under_test", ROOT / "auto_update_daily_news.py")
        cls.publisher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.publisher)

    def test_both_fields_are_checked_independently(self):
        good = {"country": "eu", "title": "新型車発表", "desc": "新型車の内装を紹介する。", "url": "https://example.com/story"}
        self.publisher.validate_japanese_news_items([good])
        for field in ["title", "desc"]:
            with self.assertRaisesRegex(RuntimeError, "Japanese summary validation failed"):
                self.publisher.validate_japanese_news_items([{**good, field: "Still in English"}])
        with self.assertRaises(RuntimeError):
            self.publisher.validate_japanese_news_items([{**good, "title": "WHAT・COPY"}])

    def test_curated_papers_keep_existing_inclusion_policy(self):
        self.publisher.validate_japanese_news_items([{"country": "paper", "title": "Study title", "desc": "Study abstract."}])

    def test_main_aborts_before_writing_or_generating_anything(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = {key: root / name for key, name in [("NEWS_PATH", "news.js"), ("INSIGHTS_PATH", "insights.js"), ("HTML_PATH", "index.html")]}
            for path in paths.values():
                path.write_text("UNCHANGED", encoding="utf-8")
            sheet = root / "source.csv"
            with sheet.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["国", "日付", "タイトル（日本語）", "内容（日本語）", "画像URL", "URL", "LLM判定", "内装関連度"])
                writer.writerow(["欧州", "2026-09-09", "WHAT AI CANNOT COPY", "Still in English.", "https://example.com/image.jpg", "https://example.com/story", "対象", "70"])
            with patch.multiple(self.publisher, **paths), patch.object(sys, "argv", ["publisher", "--sheet", str(sheet)]), patch.object(self.publisher.requests, "post", side_effect=AssertionError("No LLM call allowed")):
                with self.assertRaisesRegex(RuntimeError, "Japanese summary validation failed"):
                    self.publisher.main()
            for path in paths.values():
                self.assertEqual(path.read_text(encoding="utf-8"), "UNCHANGED")


if __name__ == "__main__":
    unittest.main()
