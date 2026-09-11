"""Repair unambiguous Indian scale loss using source amounts, never an LLM guess."""

from decimal import Decimal
import re


NUMBER = r"(?:\d{1,3}(?:,\d{3})+|\d{1,2}(?:,\d{2})*,\d{3}|\d+)(?:\.\d+)?"
SCALE = r"lakhs?|lacs?|crores?|\u30af\u30ed\u30fc\u30eb|\u30e9\u30c3\u30af|\u30e9\u30af|\u5104|\u4e07|\u5343"
CURRENCY = r"INR|Rs\.?|\u20b9|rupees?|\u30a4\u30f3\u30c9\u30eb\u30d4\u30fc|\u30eb\u30d4\u30fc"
MONEY = re.compile(
    rf"(?<![A-Za-z\d,\.\u5104\u4e07\u5343-])(?:(?P<prefix>{CURRENCY})\s*)?"
    rf"(?P<first>{NUMBER})\s*(?P<scale1>{SCALE})?"
    rf"(?:\s*(?P<mid>{CURRENCY}))?"
    rf"(?:\s*(?:[~\u301c\uff5e\u2013\u2014-]|to|\u304b\u3089)\s*"
    rf"(?:(?P<prefix2>{CURRENCY})\s*)?(?P<second>{NUMBER})\s*(?P<scale2>{SCALE})?)?"
    rf"(?:\s*(?P<suffix>{CURRENCY}))?(?![A-Za-z\d,.\u5104\u4e07\u5343])",
    re.I,
)
INDIAN_SCALES = {
    "lakh": 100000, "lakhs": 100000, "lac": 100000, "lacs": 100000,
    "crore": 10000000, "crores": 10000000,
    "\u30e9\u30c3\u30af": 100000, "\u30e9\u30af": 100000, "\u30af\u30ed\u30fc\u30eb": 10000000,
}
SCALES = {**INDIAN_SCALES, "\u4e07": 10000, "\u5104": 100000000, "\u5343": 1000}
CURRENCY_RULES = (
    "Preserve the source currency and magnitude. Never convert prices to JPY. "
    "Keep Lakh/Crore explicitly: 1 lakh = 100000 INR (10\u4e07\u30eb\u30d4\u30fc), "
    "1 crore = 10000000 INR (1000\u4e07\u30eb\u30d4\u30fc). "
    "Example: Rs 19.22 lakh = 192.2\u4e07\u30eb\u30d4\u30fc, "
    "NOT 19.22\u30eb\u30d4\u30fc or 19.22\u4e07\u30eb\u30d4\u30fc. "
    "Do not change which model/variant each price belongs to.\n"
)


class CurrencyUnitError(ValueError):
    pass


def _parts(match):
    g = match.groupdict()
    scales = [(g["scale1"] or g["scale2"] or "").lower(),
              (g["scale2"] or g["scale1"] or "").lower()]
    if not any(g[k] for k in ("prefix", "mid", "prefix2", "suffix")) and not any(
        scale in INDIAN_SCALES for scale in scales
    ):
        return []
    parts = []
    for raw, scale in zip((g["first"], g["second"]), scales):
        if raw:
            number = Decimal(raw.replace(",", ""))
            parts.append((number, scale, number * SCALES.get(scale, 1)))
    return parts


def repair_indian_price_units(text, source, country):
    """Return (text, corrections). Unknown amounts are not guessed or multiplied.

    Correct only when the coefficient is present with Lakh/Crore in the source
    and uniquely identifies a value. Already-grounded amounts take precedence.
    """
    if str(country).lower() not in ("in", "india", "\u30a4\u30f3\u30c9"):
        return text, []
    source_parts = [part for match in MONEY.finditer(str(source or "")) for part in _parts(match)]
    known_values = {value for _, _, value in source_parts}
    changes = []

    def replace(match):
        parts = _parts(match)
        if not parts:
            return match[0]
        corrected = []
        for number, scale, value in parts:
            if value in known_values:
                corrected.append(value)
                continue
            candidates = {v for n, s, v in source_parts if n == number and s in INDIAN_SCALES}
            if len(candidates) > 1:
                raise CurrencyUnitError(f"Ambiguous source currency scale for {match[0]!r}")
            corrected.append(next(iter(candidates)) if candidates else value)
        if corrected == [p[2] for p in parts]:
            return match[0]
        if len(corrected) == 2 and corrected[1] < corrected[0]:
            raise CurrencyUnitError(f"Inconsistent source price range for {match[0]!r}")

        def format_amount(value):
            # Decimal avoids introducing rounding errors while converting to man.
            amount, unit = (value / 10000, "\u4e07") if value >= 10000 else (value, "")
            return format(amount.normalize(), "f") + unit

        replacement = "\u301c".join(map(format_amount, corrected)) + "\u30eb\u30d4\u30fc"
        changes.append((match[0], replacement))
        return replacement

    return MONEY.sub(replace, str(text or "")), changes
