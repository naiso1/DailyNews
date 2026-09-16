"""Decode exterior source pages and reject transport/error pages as evidence."""
import codecs
import re

ARTICLE_TEXT_VERSION = "exterior-html-v2"


def decode_html(content, content_type=""):
    """Honor document encodings; requests' implicit Latin-1 is not a charset."""
    if isinstance(content, str):
        return content
    content = bytes(content)
    if content.startswith(codecs.BOM_UTF8):
        return content.decode("utf-8-sig")
    if content.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return content.decode("utf-16")
    encodings = []
    for meta in re.findall(rb"<meta\b[^>]*>", content[:8192], re.I):
        match = re.search(rb"charset\s*=\s*[\"']?\s*([a-zA-Z0-9_-]+)", meta, re.I)
        if match:
            encodings.append(match.group(1).decode("ascii"))
    header = re.search(r"charset\s*=\s*[\"']?\s*([a-zA-Z0-9_-]+)", str(content_type), re.I)
    if header:
        encodings.append(header.group(1))
    encodings.extend(["utf-8", "gb18030", "windows-1252"])
    for encoding in encodings:
        try:
            return content.decode(encoding)
        except (LookupError, UnicodeError):
            continue
    return content.decode("utf-8", errors="replace")


def unusable_text(text):
    text = str(text or "")
    opening = " ".join(text.split())[:600].lower()
    denial_phrases = (
        "access denied", "you don't have permission to access", "you do not have permission to access",
        "checking your browser", "verify you are human", "verify that you are human",
        "please complete the captcha", "enable javascript and cookies to continue",
        "just a moment...", "attention required! | cloudflare",
    )
    if any(opening.startswith(phrase) for phrase in denial_phrases):
        return True
    if "you don't have permission to access" in opening or "you do not have permission to access" in opening:
        return True
    # Repeated UTF-8 bytes decoded as Latin-1 were observed in Gasgoo/cnBeta.
    # Do not reuse such a saved body if a fresh source fetch fails.
    c1_controls = sum("\x80" <= char <= "\x9f" for char in text)
    return c1_controls >= 5 and c1_controls / max(1, len(text)) > 0.01


def is_error_page(soup):
    for element in (soup.title, soup.find("h1")):
        if element is not None and unusable_text(element.get_text(" ", strip=True)):
            return True
    return unusable_text(soup.get_text(" ", strip=True))
