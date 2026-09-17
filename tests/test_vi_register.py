"""Tests for G3 (Phase G): Vietnamese address-register consistency.

Peer (ban, minh), polite (anh, chi), and formal (quy khach, quy vi) are
mutually exclusive registers within one post. A post mixing them is one of
the clearest marks of AI-assisted assembly to a Vietnamese reader. The bar
(per the phase plan): report the dominant register and the line number of
every off-register sentence, and do not fire on known homographs
("ban" the compound-noun component, "anh" inside a country/language name).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import analyze_blog
import vi_register


MIXED_POST = """Quý khách hàng nên tham khảo kỹ thông số kỹ thuật trước khi mua.
Quý vị có thể liên hệ bộ phận chăm sóc khách hàng để được tư vấn thêm.
Quý công ty cam kết hỗ trợ quý khách trong suốt quá trình sử dụng.
Nhiều anh chị đã mua sản phẩm đều hài lòng với chất lượng.
Chúc bạn thành công trong việc lựa chọn sản phẩm phù hợp cho gia đình mình.
"""

CONSISTENT_POST = """Quý khách hàng nên tham khảo kỹ thông số kỹ thuật trước khi mua.
Quý vị có thể liên hệ bộ phận chăm sóc khách hàng để được tư vấn thêm.
Quý công ty cam kết hỗ trợ quý khách trong suốt quá trình sử dụng.
"""


class TestDominantAndOffRegister:
    def test_mixed_post_names_dominant_and_off_register_lines(self):
        result = vi_register.analyze_register(MIXED_POST)
        assert result['dominant_register'] == 'formal'
        assert result['consistent'] is False
        off_lines = {row['line'] for row in result['off_register']}
        assert off_lines == {4, 5}
        registers_seen = {row['register'] for row in result['off_register']}
        assert registers_seen == {'polite', 'peer'}

    def test_consistent_post_reports_no_off_register_lines(self):
        result = vi_register.analyze_register(CONSISTENT_POST)
        assert result['dominant_register'] == 'formal'
        assert result['consistent'] is True
        assert result['off_register'] == []

    def test_no_markers_reports_no_dominant(self):
        result = vi_register.analyze_register("Đây là một đoạn văn không có từ xưng hô nào.")
        assert result['dominant_register'] is None
        assert result['consistent'] is True


class TestHomographFalsePositiveGuards:
    def test_ban_doc_compound_does_not_trigger_peer(self):
        # "ban doc" (reader) is a compound noun, not the pronoun "ban".
        text = "Bạn đọc thân mến, cảm ơn đã theo dõi bài viết này."
        result = vi_register.analyze_register(text)
        assert result['marker_counts']['peer'] == 0

    def test_ban_be_and_ban_hang_compounds_do_not_trigger(self):
        text = "Đây là nhóm bạn bè lâu năm và cũng là bạn hàng làm ăn tin cậy."
        result = vi_register.analyze_register(text)
        assert result['marker_counts']['peer'] == 0

    def test_tieng_anh_and_nuoc_anh_do_not_trigger_polite(self):
        # "tieng Anh" (the English language) and "nuoc Anh" (England) are not
        # the address pronoun "anh".
        text = "Cô ấy học tiếng Anh ở nước Anh trong ba năm."
        result = vi_register.analyze_register(text)
        assert result['marker_counts']['polite'] == 0

    def test_anh_hung_compound_does_not_trigger_polite(self):
        text = "Đây là câu chuyện về một anh hùng dân tộc nổi tiếng."
        result = vi_register.analyze_register(text)
        assert result['marker_counts']['polite'] == 0

    def test_genuine_peer_and_polite_pronouns_still_fire(self):
        # Regression guard: the exclusion lists must not overreach and
        # silence real pronoun usage.
        text = "Bạn nên thử sản phẩm này. Anh có thể mua ở đâu cũng được."
        result = vi_register.analyze_register(text)
        assert result['marker_counts']['peer'] >= 1
        assert result['marker_counts']['polite'] >= 1

    def test_longer_marker_consumes_shorter_overlapping_marker(self):
        # "cac ban" (polite) must not also be counted as a bare "ban" (peer).
        text = "Các bạn hãy để lại bình luận bên dưới nhé."
        result = vi_register.analyze_register(text)
        assert result['marker_counts']['polite'] == 1
        assert result['marker_counts']['peer'] == 0


class TestWiredIntoAnalyzeBlog:
    def test_vi_register_key_present_for_vietnamese_post(self, tmp_path):
        post = f"""---
title: Bai viet ve may pha ca phe
description: Huong dan chon may pha ca phe phu hop.
author: Nguyen Van A
date: 2026-01-01
lang: vi
---
# Bai viet ve may pha ca phe

{MIXED_POST}
"""
        path = tmp_path / "post.md"
        path.write_text(post, encoding="utf-8")
        result = analyze_blog.analyze_file(str(path))
        assert result['language'] == 'vi'
        assert result['vi_register'] is not None
        assert result['vi_register']['consistent'] is False

        issue_text = " ".join(item['issue'] for item in result['score']['issues'])
        assert 'xưng hô' in issue_text.lower() or 'Xưng hô' in issue_text

    def test_vi_register_key_is_none_for_english_post(self, tmp_path):
        post = """---
title: A Guide To Blog Quality
description: A minimal English fixture.
author: Jane Doe
date: 2026-01-01
---
# A Guide To Blog Quality

Plain English content with no register markers at all.
"""
        path = tmp_path / "post.md"
        path.write_text(post, encoding="utf-8")
        result = analyze_blog.analyze_file(str(path))
        assert result['language'] == 'en'
        assert result['vi_register'] is None

    def test_consistent_vietnamese_post_raises_no_register_issue(self, tmp_path):
        post = f"""---
title: Bai viet ve may pha ca phe
description: Huong dan chon may pha ca phe phu hop.
author: Nguyen Van A
date: 2026-01-01
lang: vi
---
# Bai viet ve may pha ca phe

{CONSISTENT_POST}
"""
        path = tmp_path / "post.md"
        path.write_text(post, encoding="utf-8")
        result = analyze_blog.analyze_file(str(path))
        issue_text = " ".join(item['issue'] for item in result['score']['issues']).lower()
        assert 'xưng hô' not in issue_text
