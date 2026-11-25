import tempfile
import unittest
from pathlib import Path

from dailynews import regulatory_news as policy


class RegulatoryNewsTests(unittest.TestCase):
    def test_selection_preserves_source_and_requires_evidence(self):
        body = "The proposed vehicle safety regulation concerns occupant protection. " * 3
        rows = [{"国": "米国", "タイトル": "New vehicle safety regulation", "内容": body,
                 "URL": f"https://example.com/{i}"} for i in range(8)]
        rows += [dict(rows[0]), dict(rows[0], URL="https://news.google.com/rss/articles/item")]
        candidates = policy.shortlist(rows)
        self.assertEqual(len(candidates), 8)
        sources = policy.collect_evidence(candidates, lambda url: self.fail("unnecessary request"))
        card = {"title": "安全規制の案", "region": "米国", "stage": "検討・審議中",
                "summary": "基準案に関する発表。", "question": "どの車種が対象か。", "quote": "occupant protection"}
        rejected = [dict(card, source=99), dict(card, source=1, quote="not found in evidence")]
        proposed = [dict(card, title=f"制度案{i}", source=i) for i in range(1, 9)]
        result = policy.select_cards(sources, lambda prompt: {"cards": rejected + [proposed[0]] + proposed})
        self.assertEqual(len(result), 5)
        self.assertEqual(result[0]["links"], [["example.com", "https://example.com/0"]])
        for unusable in ({}, {"cards": rejected}):
            with self.assertRaises(ValueError):
                policy.select_cards(sources, lambda prompt: unusable)
        self.assertEqual(policy.select_cards(sources, lambda prompt: {"cards": []}), [])

    def test_images_follow_selected_source_without_refetching_rss_images_or_pdfs(self):
        urls = ["https://example.org/" + name for name in ("article", "notice", "law.pdf")]
        cards = [{"links": [["出典", url]]} for url in urls]
        rows = [{"URL": urls[0], "画像URL": "https://example.org/photo.jpg"},
                {"URL": urls[1], "画像URL": "https://example.org/logo.jpg"}]
        fetched = []
        def fetch(url):
            fetched.append(url)
            return "https://example.org/other.jpg"
        policy.add_source_images(cards, rows, lambda url: "logo" in url, fetch)
        self.assertEqual(fetched, [urls[1]])
        self.assertEqual([card.get("img") for card in cards], [rows[0]["画像URL"], "https://example.org/other.jpg", None])

    def test_retry_does_not_replace_a_reviewed_day(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "policy_data.js"
            path.write_text(policy.PREFIX + "{};\n", encoding="utf-8")
            policy.save_issue(path, "2026-11-24", [{"title": "確認済み"}])
            policy.save_issue(path, "2026-11-25", [])
            policy.save_issue(path, "2026-11-24", [])
            self.assertEqual(policy.read_issues(path), {
                "2026-11-24": [{"title": "確認済み", "id": "policy-2026-11-24-1"}], "2026-11-25": []})
