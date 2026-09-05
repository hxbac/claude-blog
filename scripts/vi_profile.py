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
}
