"""Tests pinned to the Vietnamese slug-destruction defect (see docs/vietnamese/00-OVERVIEW.md § 2.4).

These tests are expected to fail today. blog_render._slugify deletes every
non-ASCII character without transliterating, and blog_hygiene.slugify uses
NFKD, which does not decompose the d-with-stroke (dj) glyph. Both produce a
wrong, and mutually disagreeing, slug for Vietnamese titles. Only the English
regression guard is expected to pass until Phase 1 lands scripts/vi_text.py.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import blog_render
import blog_hygiene

# (input, expected) - expected is the correct Vietnamese transliteration
VI_SLUG_CASES = [
    ("Hướng dẫn đặt hàng online",     "huong-dan-dat-hang-online"),
    ("Đánh giá sản phẩm 2026",        "danh-gia-san-pham-2026"),
    ("Cách viết nội dung chuẩn SEO",  "cach-viet-noi-dung-chuan-seo"),
    ("Bí quyết để thành công",        "bi-quyet-de-thanh-cong"),
    ("Top 10 quán cà phê Hà Nội",     "top-10-quan-ca-phe-ha-noi"),
    ("Dịch vụ đăng ký kinh doanh",    "dich-vu-dang-ky-kinh-doanh"),
]


@pytest.mark.parametrize("title,expected", VI_SLUG_CASES)
def test_render_slugify_preserves_vietnamese(title, expected):
    """blog_render._slugify must transliterate, not delete, Vietnamese characters."""
    assert blog_render._slugify(title) == expected


@pytest.mark.parametrize("heading,expected", VI_SLUG_CASES)
def test_hygiene_slugify_preserves_d_stroke(heading, expected):
    """blog_hygiene.slugify must map d-with-stroke to plain d; NFKD alone deletes it."""
    assert blog_hygiene.slugify(heading) == expected


def test_both_slugifiers_agree():
    """Anchors and filenames must not disagree."""
    for title, _ in VI_SLUG_CASES:
        assert blog_render._slugify(title) == blog_hygiene.slugify(title)


def test_slug_is_stable_across_nfc_and_nfd():
    """Same visible text in NFC and NFD must produce the same slug."""
    import unicodedata
    title = "Hướng dẫn đặt hàng"
    nfc, nfd = unicodedata.normalize("NFC", title), unicodedata.normalize("NFD", title)
    assert nfc != nfd                                   # sanity: they really differ in bytes
    assert blog_render._slugify(nfc) == blog_render._slugify(nfd)


def test_english_slugs_unchanged():
    """Regression guard: English behavior must not shift."""
    assert blog_render._slugify("How to Optimize Your Blog") == "how-to-optimize-your-blog"
    assert blog_hygiene.slugify("What Are AI Citations?") == "what-are-ai-citations"
