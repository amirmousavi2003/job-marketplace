import pytest

from apps.common.text import normalize_text


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  Photoshop  ", "photoshop"),
        ("كيبورد", "کیبورد"),  # Arabic letters -> Persian
        ("نرم‌افزار", "نرم افزار"),  # ZWNJ
        ("۱۲۳ و ٤٥٦", "123 و 456"),  # Persian + Arabic-Indic digits
        ("", ""),
    ],
)
def test_normalize_text(raw, expected):
    assert normalize_text(raw) == expected
