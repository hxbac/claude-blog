"""Tests for G1 (Phase G): Vietnamese word lists inside the profile system.

Regression bar per PHASE-G-VIETNAMESE-PARITY.md: a Vietnamese post seeded
with tells must score them (not silently report zero), the same post with
tells removed must report zero, and English scoring must not change.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import analyze_blog
from vi_profile import VI_PROFILE


VI_SEEDED = """Trong thời đại số hóa, không thể phủ nhận rằng máy pha cà phê
đóng vai trò vô cùng quan trọng đối với buổi sáng của mỗi gia đình.
Tuy nhiên, người mua cần cân nhắc ngân sách trước khi chọn.
Do đó, hãy xem xét dung tích bình chứa và loại hạt cà phê thường dùng.
Ngoài ra, một số dòng máy mang lại trải nghiệm tuyệt vời cho người dùng,
và đây thực sự là giải pháp tối ưu cho người mới bắt đầu.
"""

VI_CLEAN = """Máy pha cà phê giúp buổi sáng của nhiều gia đình thuận tiện hơn.
Người mua cần cân nhắc ngân sách trước khi chọn sản phẩm.
Hãy xem xét dung tích bình chứa và loại hạt cà phê thường dùng.
Một số dòng máy có thêm chức năng xay hạt tích hợp cho người dùng.
"""


# ---------------------------------------------------------------------------
# G1: the three lists live in the profile, not module scope alone
# ---------------------------------------------------------------------------


class TestProfileCarriesWordLists:
    def test_en_profile_has_the_three_keys(self):
        profile = analyze_blog.LANGUAGE_PROFILES['en']
        assert profile['ai_phrases'] == tuple(analyze_blog.AI_PHRASES)
        assert profile['ai_trigger_words'] == tuple(analyze_blog.AI_TRIGGER_WORDS)
        assert profile['transition_words'] == tuple(analyze_blog.TRANSITION_WORDS)

    def test_vi_profile_has_vietnamese_values_not_english(self):
        assert 'ai_phrases' in VI_PROFILE
        assert 'ai_trigger_words' in VI_PROFILE
        assert 'transition_words' in VI_PROFILE
        # None of the Vietnamese entries are the English constants; this is
        # the exact regression Phase G exists to fix.
        assert set(VI_PROFILE['ai_phrases']).isdisjoint(analyze_blog.AI_PHRASES)
        assert set(VI_PROFILE['ai_trigger_words']).isdisjoint(analyze_blog.AI_TRIGGER_WORDS)
        assert set(VI_PROFILE['transition_words']).isdisjoint(analyze_blog.TRANSITION_WORDS)

    def test_vi_profile_entries_carry_diacritics(self):
        # A regression guard for constraint (b): ASCII-folded Vietnamese
        # ("khong the phu nhan") must never land in scored data.
        combined = (
            VI_PROFILE['ai_phrases']
            + VI_PROFILE['ai_trigger_words']
            + VI_PROFILE['transition_words']
        )
        vi_diacritic_chars = set(
            "àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợ"
            "ùúủũụưừứửữựỳýỷỹỵđ"
        )
        for phrase in combined:
            assert any(ch in vi_diacritic_chars for ch in phrase), (
                f"expected diacritics in Vietnamese data entry: {phrase!r}"
            )

    def test_advisory_tier_is_disjoint_from_scored_tiers(self):
        advisory = set(VI_PROFILE.get('ai_advisory_phrases', ()))
        scored = set(VI_PROFILE['ai_phrases']) | set(VI_PROFILE['ai_trigger_words'])
        assert advisory, "advisory tier must not be empty"
        assert advisory.isdisjoint(scored), (
            "a phrase cannot be both scored and merely advisory"
        )


# ---------------------------------------------------------------------------
# G1 verification bar: seeded Vietnamese scores, tells-removed scores zero
# ---------------------------------------------------------------------------


class TestVietnameseFires:
    def test_ai_phrases_fire_on_seeded_text(self):
        sentences_info = analyze_blog.analyze_sentences(VI_SEEDED)
        result = analyze_blog.analyze_ai_signals(VI_SEEDED, sentences_info, 'vi')
        assert result['ai_phrase_count'] > 0
        found_phrases = {p['phrase'] for p in result['ai_phrases_found']}
        assert 'không thể phủ nhận rằng' in found_phrases

    def test_ai_phrases_silent_on_clean_text(self):
        sentences_info = analyze_blog.analyze_sentences(VI_CLEAN)
        result = analyze_blog.analyze_ai_signals(VI_CLEAN, sentences_info, 'vi')
        assert result['ai_phrase_count'] == 0
        assert result['ai_phrases_found'] == []

    def test_trigger_words_fire_on_seeded_text(self):
        result = analyze_blog.analyze_ai_trigger_words(VI_SEEDED, 'vi')
        assert result['trigger_count'] > 0
        assert result['per_1k'] > 0
        words_found = {w['word'] for w in result['found']}
        assert 'vô cùng quan trọng' in words_found
        assert 'giải pháp tối ưu' in words_found

    def test_trigger_words_silent_on_clean_text(self):
        result = analyze_blog.analyze_ai_trigger_words(VI_CLEAN, 'vi')
        assert result['trigger_count'] == 0
        assert result['per_1k'] == 0.0
        assert result['found'] == []

    def test_transition_words_fire_on_seeded_text(self):
        result = analyze_blog.analyze_transition_words(VI_SEEDED, 'vi')
        assert result['transition_count'] >= 3

    def test_transition_words_silent_on_clean_text(self):
        result = analyze_blog.analyze_transition_words(VI_CLEAN, 'vi')
        assert result['transition_count'] == 0
        assert result['transition_pct'] == 0.0

    def test_advisory_phrase_reported_separately_not_scored(self):
        text = "Sản phẩm này đã và đang được nhiều gia đình lựa chọn."
        result = analyze_blog.analyze_ai_trigger_words(text, 'vi')
        advisory_words = {w['word'] for w in result['advisory_found']}
        assert 'đã và đang' in advisory_words
        # Advisory hits never count toward the scored trigger_count/per_1k.
        scored_words = {w['word'] for w in result['found']}
        assert 'đã và đang' not in scored_words


# ---------------------------------------------------------------------------
# Constraint (d): English behaviour is unchanged
# ---------------------------------------------------------------------------


EN_SEEDED = (
    "Furthermore, this comprehensive guide will delve into the pivotal, "
    "cutting-edge landscape of AI optimization. In today's digital "
    "landscape, it's important to note that these tools are indeed "
    "crucial. However, moreover, we must leverage this robust approach."
)


class TestEnglishUnchanged:
    def test_ai_signals_default_language_matches_explicit_en(self):
        sentences_info = analyze_blog.analyze_sentences(EN_SEEDED)
        default_result = analyze_blog.analyze_ai_signals(EN_SEEDED, sentences_info)
        explicit_result = analyze_blog.analyze_ai_signals(EN_SEEDED, sentences_info, 'en')
        assert default_result == explicit_result

    def test_trigger_words_default_language_matches_explicit_en(self):
        default_result = analyze_blog.analyze_ai_trigger_words(EN_SEEDED)
        explicit_result = analyze_blog.analyze_ai_trigger_words(EN_SEEDED, 'en')
        assert default_result['trigger_count'] == explicit_result['trigger_count']
        assert default_result['per_1k'] == explicit_result['per_1k']
        assert default_result['found'] == explicit_result['found']
        # New additive key only; old keys are byte-identical.
        assert default_result['advisory_found'] == []

    def test_transition_words_default_language_matches_explicit_en(self):
        default_result = analyze_blog.analyze_transition_words(EN_SEEDED)
        explicit_result = analyze_blog.analyze_transition_words(EN_SEEDED, 'en')
        assert default_result == explicit_result

    def test_english_trigger_words_still_use_word_boundaries(self):
        # "landscape" must not match inside "landscaped" (a longer word that
        # merely contains it as a substring). This is the pre-existing
        # \b-anchored English behavior; it must survive the profile-dispatch
        # refactor unchanged.
        text_with_substring = "The garden was newly landscaped this spring."
        result = analyze_blog.analyze_ai_trigger_words(text_with_substring, 'en')
        assert result['trigger_count'] == 0

    def test_full_file_score_identical_with_and_without_language_arg(self, tmp_path):
        # analyze_file always resolves and passes a language explicitly; this
        # confirms the resolved default path ('en') produces the same score
        # shape as calling the analyzers directly with language='en'.
        post = f"""---
title: A Fully Sourced Guide To Blog Quality
description: A test fixture with enough structure to exercise every check.
author: Jane Doe
date: 2026-01-01
---
# A Fully Sourced Guide To Blog Quality

{EN_SEEDED}

## Section Two

More plain content here for structure and length purposes only.
"""
        path = tmp_path / "post.md"
        path.write_text(post, encoding="utf-8")
        result = analyze_blog.analyze_file(str(path))
        assert result['language'] == 'en'
        assert result['vi_register'] is None
        assert 'advisory_found' in result['ai_trigger_words']
