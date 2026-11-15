"""Persian-aware text normalization, used for catalogue uniqueness and search."""

import re
import unicodedata

_CHAR_MAP = str.maketrans(
    {
        "ي": "ی",  # Arabic yeh -> Persian yeh
        "ى": "ی",
        "ك": "ک",  # Arabic kaf -> Persian kaf
        "ة": "ه",
        "ۀ": "ه",
        "أ": "ا",
        "إ": "ا",
        "ٱ": "ا",
        "\u200c": " ",  # ZWNJ -> space, so "نرم‌افزار" == "نرم افزار"
        "\u200f": "",
        "\u200e": "",
        "ـ": "",  # tatweel
    }
)
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "0123456789" * 2)
_DIACRITICS = re.compile("[\u064b-\u065f\u0670]")
_SPACES = re.compile(r"\s+")


def normalize_text(value: str) -> str:
    """Return a canonical form: unified letters/digits, no diacritics, lowercase, single spaces."""
    if not value:
        return ""
    value = unicodedata.normalize("NFKC", value)
    value = value.translate(_CHAR_MAP).translate(_DIGITS)
    value = _DIACRITICS.sub("", value)
    return _SPACES.sub(" ", value).strip().lower()
