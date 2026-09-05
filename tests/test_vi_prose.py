import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import vi_prose

FIXTURES = Path(__file__).parent / "fixtures"


def test_every_pattern_compiles():
    """A bad escape in one pattern silently disables that check."""
    import re
    for pattern, label, _fix in vi_prose.AI_TELLS:
        re.compile(pattern)                     # raises re.error on a bad pattern
        assert label, "every tell needs a label"


def test_bad_fixture_is_caught():
    raw = (FIXTURES / "blog_vi_bad.md").read_text(encoding="utf-8")
    report = vi_prose.lint_text(raw)
    assert report["ai_tell_count"] >= 5
    assert report["ai_tell_density_per_1000"] > 2.0


def test_good_fixture_is_clean():
    raw = (FIXTURES / "blog_vi_good.md").read_text(encoding="utf-8")
    report = vi_prose.lint_text(raw)
    assert report["ai_tell_count"] == 0, [f["match"] for f in report["findings"]]
    assert report["ai_tell_density_per_1000"] <= 2.0


def test_register_drift_detected():
    text = "Quý khách vui lòng liên hệ. Các bạn cũng có thể tự làm."
    report = vi_prose.lint_text(text)
    assert any(f["type"] == "register_drift" for f in report["findings"])


def test_single_register_is_not_flagged():
    text = "Bạn nên nén ảnh trước. Sau đó bạn bật cache. Cuối cùng bạn đo lại."
    report = vi_prose.lint_text(text)
    assert not any(f["type"] == "register_drift" for f in report["findings"])


def test_code_blocks_are_ignored():
    """A tell inside a fenced block is a code sample, not prose."""
    text = "```\ntrong thế giới ngày nay\n```\nNội dung thật ở đây."
    assert vi_prose.lint_text(text)["ai_tell_count"] == 0


def test_english_text_produces_nothing():
    text = "In today's world, SEO plays a very important role for every business."
    assert vi_prose.lint_text(text)["ai_tell_count"] == 0
