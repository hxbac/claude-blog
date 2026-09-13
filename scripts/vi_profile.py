#!/usr/bin/env python3
"""Vietnamese LANGUAGE_PROFILES payload for analyze_blog.py. Stdlib only.

Kept out of analyze_blog.py so the Vietnamese rules can be reviewed, tested and
ported independently of the analyzer.

The `\\b` trap: Python's `\\b` is defined over `[A-Za-z0-9_]`, so it does not
fire between a space and an accented Vietnamese letter such as `u+ dash` or
`d with stroke`. Every pattern below avoids `\\b` around Vietnamese words and
uses explicit `\\s+` or lookarounds instead.
"""

from __future__ import annotations

from typing import Any

VI_PROFILE: dict[str, Any] = {
    # "TL;DR" equivalents Vietnamese writers actually use as headings.
    'summary_labels': (
        r'tóm\s+tắt',
        r'tóm\s+lược',
        r'điểm\s+chính',
        r'ý\s+chính',
        r'nội\s+dung\s+chính',
        r'tổng\s+quan\s+nhanh',
        r'đọc\s+nhanh',
        r'những\s+điều\s+cần\s+biết',
        r'TL;?DR',                      # bilingual tech blogs use the English form too
    ),

    'about_patterns': (
        r'về\s+chúng\s+tôi',
        # "giới thiệu" alone means "to introduce" and appears in ordinary prose
        # ("bài viết giới thiệu sản phẩm"), so require an about-page object, a
        # heading, or link syntax, mirroring how the 'en' profile requires
        # "about us / the author / me" rather than bare "about".
        r'giới\s+thiệu\s+(?:về\s+)?(?:chúng\s+tôi|công\s+ty|doanh\s+nghiệp|'
        r'tác\s+giả|đội\s+ngũ|website|trang\s+web)',
        r'(?:^|\n)\s*#{1,6}\s*giới\s+thiệu\s*(?:$|\n)',
        r'\[\s*giới\s+thiệu[^\]]*\]',
        r'chúng\s+tôi\s+là\s+ai',
        r'câu\s+chuyện\s+của\s+chúng\s+tôi',
        r'/(?:gioi-thieu|ve-chung-toi|about)(?:[/?#]|$)',
    ),

    'contact_patterns': (
        r'liên\s+hệ',
        r'liên\s+lạc',
        r'thông\s+tin\s+liên\s+hệ',
        r'/(?:lien-he|contact)(?:[/?#]|$)',
    ),

    # First-hand experience. Vietnamese has no single-word "I" that is safe to
    # match (toi/minh/chung toi all appear in ordinary prose), so match the
    # pronoun WITH an evidence verb, the same approach the 'en' profile takes.
    'first_person_patterns': (
        r'(?:chúng\s+tôi|chúng\s+mình|tôi|mình|đội\s+ngũ\s+của\s+chúng\s+tôi)\s+'
        r'(?:đã\s+)?(?:thử\s+nghiệm|kiểm\s+nghiệm|kiểm\s+chứng|thử|đo|đo\s+lường|'
        r'phân\s+tích|khảo\s+sát|xây\s+dựng|triển\s+khai|áp\s+dụng|nhận\s+thấy|'
        r'phát\s+hiện|tìm\s+ra|rút\s+ra|tổng\s+hợp|thống\s+kê)',
        r'(?:theo|qua)\s+(?:kinh\s+nghiệm|trải\s+nghiệm|thực\s+tế)\s+'
        r'(?:của\s+)?(?:chúng\s+tôi|tôi|mình|chúng\s+mình)',
        r'(?:từ|dựa\s+trên)\s+(?:dữ\s+liệu|số\s+liệu|kết\s+quả|quá\s+trình)\s+'
        r'(?:thử\s+nghiệm|kiểm\s+nghiệm|đo\s+lường|phân\s+tích|khảo\s+sát)\s+'
        r'(?:của\s+)?(?:chúng\s+tôi|tôi|mình)',
        r'(?:trong|qua)\s+\d+\s+(?:năm|tháng)\s+(?:làm|triển\s+khai|vận\s+hành|thực\s+hiện)',
    ),

    # Second pattern mirrors 'en': an evidence verb followed within 180 characters
    # by a number or a link, so an unsubstantiated claim does not score.
    'methodology_patterns': (
        r'(?:phương\s+pháp(?:\s+nghiên\s+cứu|\s+luận)?|phương\s+pháp\s+đo|'
        r'cỡ\s+mẫu|kích\s+thước\s+mẫu|quy\s+mô\s+mẫu|mẫu\s+khảo\s+sát|'
        r'cách\s+(?:đo|thử\s+nghiệm|kiểm\s+nghiệm|tiến\s+hành)|'
        r'thiết\s+lập\s+thử\s+nghiệm|quy\s+trình\s+(?:đo|kiểm\s+nghiệm|nghiên\s+cứu)|'
        r'nguồn\s+dữ\s+liệu|bộ\s+dữ\s+liệu)',
        r'(?:chúng\s+tôi|tôi|mình|đội\s+ngũ)\s+(?:đã\s+)?'
        r'(?:thử\s+nghiệm|kiểm\s+nghiệm|đo|đo\s+lường|phân\s+tích|khảo\s+sát)'
        r'[^.\n]{0,180}(?:\d|https?://|\[[^\]]+\]\(https?://)',
    ),

    'readability_model': 'vi_syllable',

    # New keys: these do not exist in 'en'/'tr' by default. analyze_blog.py
    # backfills the same key onto 'en' (and, for now, 'tr') with the
    # equivalent English patterns, so no profile has a missing key.
    'entity_definition_patterns': (
        r'\*\*[^*]+\*\*\s*(?:là|nghĩa\s+là|có\s+nghĩa\s+là|được\s+hiểu\s+là|'
        r'được\s+định\s+nghĩa\s+là|dùng\s+để\s+chỉ|ám\s+chỉ|tức\s+là)',
    ),
    'editorial_patterns': (
        r'biên\s+tập',
        r'(?:đã\s+được\s+)?(?:kiểm\s+chứng|kiểm\s+duyệt|thẩm\s+định|rà\s+soát)(?:\s+bởi)?',
        r'(?:người|ban)\s+(?:biên\s+tập|duyệt)',
        r'cố\s+vấn\s+(?:chuyên\s+môn|nội\s+dung)',
    ),

    # ------------------------------------------------------------------
    # G1 (Phase G): word lists moved into the profile system so a new
    # language cannot repeat the mistake of hardcoded English defaults
    # silently scoring zero on every non-English post. See
    # skills/blog/references/vi-word-list-tiering.md for the bar an entry
    # must clear to belong in the scored tiers below versus the advisory
    # tier: a phrase a careful Vietnamese writer would rarely choose on
    # purpose, not merely a common formal phrase.
    #
    # Scored: counted into ai_trigger_words / per_1k and ai_phrase_count,
    # the same way the English lists are scored.
    'ai_phrases': (
        'trong thời đại số hóa',
        'không thể phủ nhận rằng',
        'đóng vai trò vô cùng quan trọng',
        'mang lại nhiều lợi ích thiết thực',
        'giúp bạn dễ dàng hơn bao giờ hết',
        'hy vọng bài viết đã mang đến',
        'hy vọng bài viết này đã giúp',
        'chúc bạn thành công',
        'điều này cho thấy rằng',
        'có thể nói rằng',
        'một trong những yếu tố quan trọng nhất',
        'với sự phát triển mạnh mẽ của',
        'đáp ứng nhu cầu ngày càng cao',
        'không có gì ngạc nhiên khi',
        'hãy cùng tìm hiểu',
        'bài viết này sẽ giúp bạn',
        'hy vọng những chia sẻ trên',
    ),
    'ai_trigger_words': (
        'vô cùng quan trọng',
        'đóng vai trò quan trọng',
        'không thể phủ nhận',
        'dễ dàng hơn bao giờ hết',
        'vai trò then chốt',
        'một cách toàn diện',
        'hết sức quan trọng',
        'chìa khóa thành công',
        'bước tiến quan trọng',
        'yếu tố then chốt',
        'xu hướng tất yếu',
        'không ngừng phát triển',
        'đóng góp to lớn',
        'vai trò không thể thay thế',
        'giải pháp tối ưu',
        'trải nghiệm tuyệt vời',
        'bước ngoặt quan trọng',
        'tiềm năng to lớn',
        'giá trị to lớn',
        'cột mốc quan trọng',
    ),
    'transition_words': (
        'tuy nhiên', 'do đó', 'vì vậy', 'ngoài ra', 'bên cạnh đó',
        'mặt khác', 'nói cách khác', 'chẳng hạn', 'ví dụ', 'kết quả là',
        'cụ thể là', 'đặc biệt là', 'tóm lại', 'nhìn chung', 'thực tế',
        'tuy vậy', 'hơn nữa', 'trong khi đó', 'ngược lại', 'vì thế',
        'do vậy', 'trước hết', 'cuối cùng', 'thứ nhất', 'thứ hai',
        'thứ ba',
    ),
    # Advisory only: reported for awareness, never summed into the scored
    # trigger_count / per_1k or the ai_phrase_count. These read as ordinary
    # formal Vietnamese at least as often as they read as an AI tell, so
    # scoring them would train writers to avoid normal prose.
    'ai_advisory_phrases': (
        'đã và đang',
        'trong bối cảnh hiện nay',
        'vai trò quan trọng',
        'ngày càng phổ biến',
        'ngày càng tăng',
        'không thể thiếu',
        'hiệu quả cao',
        'chất lượng cao',
        'nhu cầu ngày càng cao',
        'xu hướng phát triển',
    ),

    # ------------------------------------------------------------------
    # G2 (Phase G): Vietnamese marks passive voice with a preverbal marker
    # ("bị" negative connotation, "được" neutral or positive), not with an
    # auxiliary + participle like English. Both markers are also ordinary
    # main verbs ("được" can mean "to get/receive", "bị" "to undergo"), so a
    # bare marker match overcounts (example: "bị bệnh", to get sick, where
    # "bệnh" is a noun, not a verb). Requiring the marker be followed by a
    # verb from this list, optionally after one adverb, rules that class of
    # false positive out.
    #
    # Known, accepted over-count: this does not and cannot without a parser
    # distinguish a true patient-subject passive ("được công nhận", is
    # recognized) from a benefactive or permissive reading of the identical
    # surface form ("được nghỉ", gets to rest). Both are counted; treating
    # them alike mirrors how English "get"-passives are usually counted with
    # "be"-passives rather than excluded.
    'passive_verbs': (
        'công nhận', 'sử dụng', 'phê duyệt', 'phê chuẩn', 'chấp nhận',
        'chấp thuận', 'phát hiện', 'xác nhận', 'xác định', 'đánh giá',
        'xử lý', 'giải quyết', 'kiểm duyệt', 'phân phối', 'sản xuất',
        'thiết kế', 'phát triển', 'triển khai', 'áp dụng', 'ban hành',
        'khuyến khích', 'yêu cầu', 'kiểm tra', 'kiểm soát', 'quản lý',
        'giám sát', 'tổ chức', 'thực hiện', 'xây dựng', 'ghi nhận',
        'đề cập', 'đề xuất', 'giới thiệu', 'công bố', 'cung cấp',
        'hỗ trợ', 'bảo vệ', 'cải thiện', 'cải tiến', 'nâng cấp',
        'cập nhật', 'tuyển dụng', 'bổ nhiệm', 'lựa chọn', 'mời',
        'xếp hạng', 'công khai', 'tiết lộ', 'xuất bản', 'biên tập',
        'kiểm chứng', 'thẩm định', 'khen ngợi', 'vinh danh', 'trao tặng',
        'xử phạt', 'sa thải', 'từ chối', 'ảnh hưởng', 'tác động',
        'tấn công', 'đe dọa', 'bắt giữ', 'truy tố', 'kết án',
        'mua', 'bán', 'ưa chuộng', 'yêu thích',
        # Phase G review: the original 69 verb list missed common commerce
        # and logistics verbs, so a Vietnamese shipping post reported far
        # fewer passives than it contained. Metric is descriptive only, but
        # a wrong number shown to a writer is still a wrong number.
        "trả", "trả lại", "hoàn", "hoàn trả", "giao", "giao hàng", "gửi", "nhận", "tính", "tính toán", "thanh toán", "đặt", "đặt hàng", "duyệt", "phê duyệt", "xử lý", "vận chuyển", "đóng gói", "niêm yết", "chiết khấu", "hủy", "thu", "thu hộ", "bồi thường", "ghi nhận", "thống kê", "phân loại", "chuyển", "chuyển khoản", "lưu", "lưu trữ", "sắp xếp", "ưu tiên",
    ),
    # A single optional adverb may sit between the marker and the verb
    # ("đã", "đang được công nhận"). More than one adverb, or an adverb the
    # list omits, is a documented miss, not a crash: the marker is still
    # reported if it appears elsewhere in the sentence unadorned.
    'passive_adverbs': (
        'đã', 'sẽ', 'đang', 'cũng', 'vẫn', 'còn', 'luôn', 'thường', 'mới',
    ),
}
