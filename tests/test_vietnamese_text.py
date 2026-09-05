"""Placeholder tests for the scripts/vi_text.py module Phase 1 creates.

These fail with ModuleNotFoundError until Phase 1 lands - that is intended
and correct. Per docs/vietnamese/00-OVERVIEW.md § 3, all Vietnamese logic
(normalization, transliteration, syllable counting) must live in
scripts/vi_*.py rather than scattered inline unicodedata calls, so this
module is the contract Phase 1 must satisfy.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


def test_module_exists():
    import vi_text                                   # noqa: F401


def test_nfc_normalization():
    import unicodedata, vi_text
    nfd = unicodedata.normalize("NFD", "Hướng dẫn")
    assert vi_text.normalize(nfd) == unicodedata.normalize("NFC", "Hướng dẫn")


def test_d_stroke_maps_to_d():
    import vi_text
    assert vi_text.to_ascii("đặt") == "dat"
    assert vi_text.to_ascii("Đảng") == "Dang"


def test_syllable_count_is_whitespace_based():
    """Vietnamese is monosyllabic: syllables == whitespace-separated tokens."""
    import vi_text
    assert vi_text.count_syllables("Cách viết nội dung chuẩn SEO") == 6
