"""Tests pinned to each profile-driven Vietnamese signal from
docs/vietnamese/00-OVERVIEW.md § 2.3.

analyze_blog.LANGUAGE_PROFILES currently has exactly two entries, 'en' and
'tr'. A Vietnamese post is silently classified as English by _detect_language,
so readability, E-E-A-T trust, first-person experience, methodology, and AI
Citation Readiness all misfire. These tests are expected to fail until a
'vi' profile lands (Phase 2) and, for the two hardcoded-English regexes
noted below, until Phase 2/3 make those regexes language-aware too.

Implementer note on the real API (confirmed against scripts/analyze_blog.py,
~2,000 lines, and against tests/test_analyze_blog.py's conventions):

- There is no top-level `analyze_blog.analyze(content)`. The real entry
  point is `analyze_file(file_path)`, which takes a path, not a string, and
  returns a dict with `result["score"]["total"]` and
  `result["score"]["category_details"]` (not `report["total_score"]` /
  `report["breakdown"]` as an earlier draft of this test assumed).
- `analyze_ai_citation_readiness` takes three positional arguments before
  `language`: `(content, headings_info, faq_info, language="en")`, not just
  `(content, language=...)`. `headings_info` and `faq_info` come from
  `analyze_headings(body)` and `analyze_faq(body)` respectively.
"""

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import analyze_blog

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def vi_good():
    return (FIXTURES / "blog_vi_good.md").read_text(encoding="utf-8")


def test_vi_profile_exists():
    assert "vi" in analyze_blog.LANGUAGE_PROFILES


def test_declared_lang_vi_is_honored(vi_good):
    fm = analyze_blog.extract_frontmatter(vi_good)
    assert fm.get("lang") == "vi"
    assert analyze_blog._detect_language(fm, vi_good) == "vi"


def test_vietnamese_detected_without_declaration(vi_good):
    """Heuristic must catch Vietnamese even when frontmatter omits lang."""
    body = analyze_blog.strip_frontmatter(vi_good)
    assert analyze_blog._detect_language({}, body) == "vi"


def test_unknown_language_still_falls_back_to_en():
    """Regression guard: the fallback itself must not change."""
    assert analyze_blog._detect_language({"lang": "de"}, "Guten Tag") == "en"


def test_readability_model_is_not_flesch_for_vi():
    profile = analyze_blog.LANGUAGE_PROFILES["vi"]
    assert profile["readability_model"] != "flesch"


@pytest.mark.parametrize("key,sample", [
    ("summary_labels",        "## Tóm tắt"),
    ("about_patterns",        "Xem thêm tại [Giới thiệu](/gioi-thieu)"),
    ("contact_patterns",      "[Liên hệ](/lien-he) với chúng tôi"),
    ("first_person_patterns", "Chúng tôi đã thử nghiệm trên 40 website"),
    ("methodology_patterns",  "Cỡ mẫu: 40 website, đo trong 3 tháng"),
])
def test_vi_profile_patterns_match_real_vietnamese(key, sample):
    profile = analyze_blog.LANGUAGE_PROFILES["vi"]
    assert any(re.search(p, sample, re.IGNORECASE) for p in profile[key]), \
        f"no pattern in {key} matched: {sample!r}"


def test_vietnamese_entity_definition_detected():
    """analyze_blog's entity-definition regex is hardcoded to English
    is/are/refers to/means; a vi profile alone will not fix it, because
    entity_definitions is computed directly in analyze_ai_citation_readiness
    and is not routed through LANGUAGE_PROFILES at all."""
    content = "**Core Web Vitals** là bộ chỉ số đo trải nghiệm người dùng."
    headings_info = analyze_blog.analyze_headings(content)
    faq_info = analyze_blog.analyze_faq(content)
    result = analyze_blog.analyze_ai_citation_readiness(
        content, headings_info, faq_info, language="vi"
    )
    assert result["entity_definitions"] >= 1


def test_vietnamese_tldr_detected(vi_good):
    body = analyze_blog.strip_frontmatter(vi_good)
    headings_info = analyze_blog.analyze_headings(body)
    faq_info = analyze_blog.analyze_faq(body)
    result = analyze_blog.analyze_ai_citation_readiness(
        body, headings_info, faq_info, language="vi"
    )
    assert result["has_tldr"] is True


def test_good_vietnamese_post_can_reach_gate_threshold(vi_good, tmp_path):
    """The headline test: Gate 4 requires >= 90. Today this is unreachable
    for vi because the post is silently scored under the 'en' profile."""
    path = tmp_path / "blog_vi_good.md"
    path.write_text(vi_good, encoding="utf-8")
    result = analyze_blog.analyze_file(str(path))
    assert result["score"]["total"] >= 90, (
        f"scored {result['score']['total']}; "
        f"category_details: {result['score'].get('category_details')}"
    )
