"""Tests for G2 (Phase G): Vietnamese passive voice detection.

Vietnamese marks passive with a preverbal marker ("bi" negative, "duoc"
neutral/positive) rather than English's auxiliary + participle. Both
markers are also ordinary main verbs, so the bar (per the phase plan) is:
false positives matter more than misses, because this feeds a score.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import analyze_blog


class TestDispatchesOnLanguage:
    def test_english_default_uses_english_regex(self):
        text = "The report was written by the team. The data was analyzed carefully."
        result = analyze_blog.analyze_passive_voice(text)
        assert result['passive_count'] >= 1
        assert 'bi_count' not in result

    def test_vietnamese_uses_marker_model(self):
        text = "Sản phẩm được công nhận là an toàn."
        result = analyze_blog.analyze_passive_voice(text, 'vi')
        assert result['model'] == 'vi_marker'
        assert 'bi_count' in result and 'duoc_count' in result


class TestVietnamesePassiveFires:
    def test_three_bi_duoc_passives_report_three(self):
        text = (
            "Sản phẩm được công nhận là an toàn. "
            "Đề xuất bị từ chối ngay lập tức. "
            "Nhân viên đó bị sa thải tuần trước."
        )
        result = analyze_blog.analyze_passive_voice(text, 'vi')
        assert result['passive_count'] == 3
        assert result['bi_count'] == 2
        assert result['duoc_count'] == 1

    def test_bi_and_duoc_reported_separately(self):
        text = "Kế hoạch được phê duyệt nhanh chóng. Yêu cầu bị từ chối sau đó."
        result = analyze_blog.analyze_passive_voice(text, 'vi')
        assert result['duoc_count'] == 1
        assert result['bi_count'] == 1
        assert result['passive_count'] == result['bi_count'] + result['duoc_count']

    def test_optional_adverb_between_marker_and_verb_still_matches(self):
        text = "Chính sách này đã được áp dụng trên toàn quốc từ năm ngoái."
        result = analyze_blog.analyze_passive_voice(text, 'vi')
        assert result['duoc_count'] == 1


class TestVietnamesePassiveFalsePositiveGuards:
    def test_duoc_as_main_verb_reports_zero(self):
        # "duoc" here means "received/got" a noun, not a passive marker.
        text = "Em được năm điểm mười trong kỳ thi. Cô ấy được một món quà sinh nhật."
        result = analyze_blog.analyze_passive_voice(text, 'vi')
        assert result['passive_count'] == 0
        assert result['duoc_count'] == 0

    def test_bi_followed_by_noun_reports_zero(self):
        # "bi" + a noun ("cam", a cold; "dau bung", a stomach ache) is the
        # ordinary main-verb reading of "bi", not a passive marker.
        text = "Anh ta bị cảm nặng vào mùa đông. Chị ấy bị đau bụng sau bữa trưa."
        result = analyze_blog.analyze_passive_voice(text, 'vi')
        assert result['passive_count'] == 0
        assert result['bi_count'] == 0

    def test_no_markers_at_all_reports_zero(self):
        text = "Chúng tôi xây dựng sản phẩm này trong hai năm."
        result = analyze_blog.analyze_passive_voice(text, 'vi')
        assert result['passive_count'] == 0

    def test_empty_text_reports_zero_not_crash(self):
        result = analyze_blog.analyze_passive_voice("", 'vi')
        assert result['passive_count'] == 0
        assert result['total_sentences'] == 0


class TestCommerceVerbCoverage:
    """The first verb whitelist covered 69 verbs and missed most of the ones a
    Vietnamese shipping or e-commerce post actually uses, so a real draft
    reported roughly a third of the passives it contained. The metric is
    descriptive rather than scored, but a wrong number shown to a writer is
    still wrong. Found by running the detector on hand written sentences
    rather than on the fixture it was built against.
    """

    def test_logistics_passives_are_counted(self):
        text = "Hàng bị trả lại. Đơn được xác nhận. Phí được tính hai chiều."
        assert analyze_blog.analyze_passive_voice(text, language="vi")["passive_count"] == 3

    def test_payment_and_delivery_passives_are_counted(self):
        text = "Đơn được giao trong hai ngày. Tiền được thanh toán sau. Yêu cầu bị hủy."
        assert analyze_blog.analyze_passive_voice(text, language="vi")["passive_count"] == 3

    def test_the_added_verbs_did_not_create_false_positives(self):
        text = "Em được điểm mười. Anh ấy bị cảm nặng. Tôi mua được hàng rẻ."
        assert analyze_blog.analyze_passive_voice(text, language="vi")["passive_count"] == 0
