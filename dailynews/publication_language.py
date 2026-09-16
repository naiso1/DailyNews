"""Language checks for the collector's final selection, matching publication guards."""
import re


class SummaryQuarantineError(RuntimeError):
    """No usable selected summaries remain; this is not a valid no-news day."""


def summary_language_problem(country, title, body):
    if str(country or "").strip().lower() in {"論文", "paper", "papers"}:
        return ""
    # Keep the publisher's title policy (kanji-only headlines are valid), while
    # rejecting punctuation such as the middle dot as proof of translation.
    if not re.search(r"[\u3041-\u3096\u30a1-\u30fa\u4e00-\u9fff]", str(title or "")):
        return "untranslated_title"
    if not re.search(r"[\u3041-\u3096\u30a1-\u30fa]", str(body or "")):
        return "untranslated_summary"
    return ""
