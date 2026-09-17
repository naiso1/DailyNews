"""Compression cannot discard a validated analysis because an LLM loses citations."""
from contextlib import redirect_stdout
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import auto_update_daily_news as publisher
from dailynews.editions import get_edition


class AnalysisCompressionTests(unittest.TestCase):
    def setUp(self):
        self.sources = [{"newsId": f"jp{i}", "title": f"グリルの設計{i}", "desc": "グリルの意匠を公開した。",
                         "img": "", "interiorScore": 80} for i in range(1, 5)]
        self.allowed = publisher.build_allowed_news_ids(self.sources)
        self.original = "".join(("グリルの意匠と素材の組み合わせを検討する" * 7) + f"[jp{i}]。" for i in range(1, 5))
        self.assertGreater(len(self.original), publisher.ANALYSIS_CHAR_LIMIT)
        self.assertTrue(publisher.analysis_ref_coverage_ok(self.original))

    def pipeline(self, text, output=None, failure=None):
        # Match the production normalization order after the existing quality gate.
        before = publisher.filter_analysis_refs_to_allowed(publisher.normalize_analysis_refs_per_sentence(text), self.allowed)
        with patch.object(publisher, "call_llm", side_effect=failure, return_value=output) as llm:
            candidate = publisher.shorten_analysis_with_llm("unused", "mock", before)
        candidate = publisher.filter_analysis_refs_to_allowed(publisher.normalize_analysis_refs_per_sentence(
            publisher.bracket_bare_allowed_ids(candidate, self.allowed)), self.allowed)
        candidate = publisher.filter_analysis_refs_to_allowed(publisher.normalize_analysis_refs_per_sentence(
            publisher.ensure_analysis_image_refs(candidate, self.sources)), self.allowed)
        with redirect_stdout(io.StringIO()) as log:
            final = publisher.preserve_analysis_citations(before, candidate, self.allowed)
        return final, candidate, log.getvalue(), llm

    def test_citation_loss_after_quality_gate_restores_original_for_both_editions(self):
        for edition in ("interior", "exterior"):
            with patch.object(publisher, "EDITION", get_edition(edition)), patch.object(publisher, "call_llm", side_effect=AssertionError("Quality gate already passed")):
                checked = publisher.ensure_analysis_ref_quality("unused", "mock", "jp", self.original, self.sources)
            self.assertEqual(checked, self.original)
            with patch.object(publisher, "EDITION", get_edition(edition)):
                final, candidate, log, _ = self.pipeline(checked, output="意匠を検討する[jp1]。部品の価値を高める。")
            self.assertFalse(publisher.analysis_ref_coverage_ok(candidate))
            self.assertEqual(final, self.original)
            self.assertIn("over_target=True", log)
            self.assertEqual(publisher.analysis_unique_refs(final), self.allowed)

    def test_failed_shortening_cannot_cut_off_late_reference_in_long_first_sentence(self):
        original = "グリルの形状と素材を検討する" * 45 + "[jp1]。"
        final, candidate, _, llm = self.pipeline(original, failure=RuntimeError("mock unavailable"))
        self.assertLessEqual(len(candidate), publisher.ANALYSIS_CHAR_LIMIT)
        self.assertFalse(publisher.analysis_ref_coverage_ok(candidate))
        self.assertEqual(final, original)
        llm.assert_called_once()

    def test_valid_compression_and_normalized_bare_existing_ids_are_kept(self):
        output = "グリルの意匠を検討するjp1。素材と形状を考察する[jp2]。"
        final, candidate, log, _ = self.pipeline(self.original, output=output)
        self.assertEqual(final, candidate)
        self.assertIn("[jp1]", final)
        self.assertLess(len(final), len(self.original))
        self.assertEqual(log, "")

    def test_unknown_compressed_refs_are_filtered_before_restoring_original(self):
        final, candidate, _, _ = self.pipeline(self.original, output="グリルの設計を検討する[eu999]。")
        self.assertNotIn("eu999", candidate)
        self.assertEqual(final, self.original)

    def test_invalid_original_is_not_made_valid_and_no_refs_are_added(self):
        original = "グリルの素材を検討する。"
        for candidate in ("参照のない考察。", "許可されていない参照[eu999]。", "English only[jp1]."):
            with redirect_stdout(io.StringIO()) as log:
                final = publisher.preserve_analysis_citations(original, candidate, self.allowed)
            self.assertEqual(final, candidate)
            self.assertEqual(log.getvalue(), "")
        self.assertFalse(publisher.exterior_analysis_complete(original, self.sources))

    def test_original_with_disallowed_refs_cannot_be_used_as_fallback(self):
        original = "不正な参照を含む考察[eu999]。"
        candidate = "参照のない考察。"
        self.assertEqual(publisher.preserve_analysis_citations(original, candidate, self.allowed), candidate)


if __name__ == "__main__":
    unittest.main()
