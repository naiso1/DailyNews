"""Whitespace cleanup for displayed article titles and summaries, not URLs."""
import re


def normalize_prose_whitespace(value):
    text = str(value or "")
    # Model responses can contain literal \\n even after JSON decoding. Handle
    # repeated escaping without decoding unrelated Unicode/quote/backslash data.
    text = re.sub(r"\\+(?:r\\+n|[rn])", " ", text)
    return re.sub(r"\s+", " ", text).strip()
