#!/usr/bin/env python3
"""Vietnamese language profile and the SOLE source of Vietnamese lexical tells.

Everything that says "this phrase reads as machine-written Vietnamese" lives in
``VI_TELLS`` below and nowhere else:

* ``analyze_blog.py`` reads the derived ``ai_phrases`` / ``ai_trigger_words`` /
  ``ai_advisory_phrases`` keys of ``VI_PROFILE`` and ``scan_tells()``.
* ``vi_prose.py`` reads ``scan_tells()`` and ``FORMULA_TELLS`` (``AI_TELLS``).
* ``ai_structure.py`` reads ``residue_patterns()`` and ``closer_patterns()``.
* claude-seo's ``content_humanize.py`` uses a GENERATED copy of the rewrite
  table (``scripts/sync_vi_tells.py`` writes it; a test fails when the copy
  drifts). Never edit that copy by hand.

Adding, removing or rewording a tell means editing this file, then running
``python3 scripts/sync_vi_tells.py --write``.

The `\\b` trap: Python's `\\b` is defined over `[A-Za-z0-9_]`, so it does not
fire between a space and an accented Vietnamese letter such as `u+ dash` or
`d with stroke`. Every pattern below avoids `\\b` around Vietnamese words and
uses explicit `\\s+` or lookarounds instead.
"""

from __future__ import annotations

import re
from typing import Any, NamedTuple

# ---------------------------------------------------------------------------
# Lexical tells: the single list
# ---------------------------------------------------------------------------

#: A phrase a careful writer would rarely choose on purpose. Scored.
PHRASE = 'phrase'
#: A single loaded word or short collocation. Scored per 1,000 syllables.
TRIGGER = 'trigger'
#: Ordinary formal Vietnamese that is only sometimes a tell. Reported, never
#: scored (see skills/blog/references/vi-word-list-tiering.md).
ADVISORY = 'advisory'
#: A regex for a formulaic opener, connective or sign-off. Scored.
FORMULA = 'formula'
#: Leftover from a chat turn that was never meant for the reader. P0.
RESIDUE = 'residue'
#: A stock one-line paragraph closer (used by ai_structure.py).
CLOSER = 'closer'

SCORED_TIERS = (PHRASE, TRIGGER, FORMULA)


class Tell(NamedTuple):
    id: str
    tier: str
    label: str
    fix: str
    #: Literal phrase (PHRASE, TRIGGER, ADVISORY); words joined by one space.
    text: str | None = None
    #: Regex (FORMULA, RESIDUE, CLOSER). PHRASE/TRIGGER/ADVISORY derive theirs.
    regex: str | None = None
    #: (regex, replacement) for the claude-seo humanizer, or None.
    rewrite: tuple[str, str] | None = None
    #: RESIDUE only: match just on the first prose line (a chat preamble).
    preamble_only: bool = False


_LB = r'(?<![^\W\d_])'
_RB = r'(?![^\W\d_])'


def _phrase_regex(text: str) -> str:
    return _LB + r'\s+'.join(re.escape(w) for w in text.split()) + _RB


_INTENSIFIER = r'\s+(?:(?:mới|chính|thực\s+sự|thật\s+sự)\s+)*'

_FIX_CONCRETE = 'Nêu con số, ví dụ hoặc việc cụ thể thay cho tính từ.'
_FIX_CUT = 'Bỏ cụm này và giữ lại nội dung phía sau.'
_LABEL_WORN = 'Cụm mòn'

VI_TELLS: tuple[Tell, ...] = (
    # ---- PHRASE: scored, order kept stable for the humanizer table ----
    Tell('thoi-dai-so-hoa', PHRASE, 'Mở bài sáo rỗng', 'Vào thẳng vấn đề người đọc đang gặp.',
         text='trong thời đại số hóa',
         rewrite=(r'trong\s+thời\s+đại\s+số\s+hóa(?:\s+(?:ngày\s+nay|hiện\s+nay))?\s*', 'hiện nay ')),
    Tell('khong-the-phu-nhan-rang', PHRASE, 'Khẳng định rỗng',
         'Bỏ. Nếu đúng thì không cần nói là không thể phủ nhận.',
         text='không thể phủ nhận rằng',
         rewrite=(r'không\s+thể\s+phủ\s+nhận\s+rằng\s*', '')),
    Tell('vai-tro-vo-cung-quan-trong', PHRASE, _LABEL_WORN, 'Nói rõ nó làm gì.',
         text='đóng vai trò vô cùng quan trọng',
         rewrite=(r'đóng\s+vai\s+trò\s+vô\s+cùng\s+quan\s+trọng', 'rất quan trọng')),
    Tell('loi-ich-thiet-thuc', PHRASE, 'Hứa hẹn mơ hồ', 'Nêu lợi ích cụ thể đo được.',
         text='mang lại nhiều lợi ích thiết thực',
         rewrite=(r'mang\s+lại\s+nhiều\s+lợi\s+ích\s+thiết\s+thực', 'hữu ích')),
    Tell('de-dang-hon-bao-gio-het', PHRASE, 'Hứa hẹn mơ hồ', 'Nêu mức tiết kiệm thực tế.',
         text='giúp bạn dễ dàng hơn bao giờ hết',
         rewrite=(r'giúp\s+bạn\s+dễ\s+dàng\s+hơn\s+bao\s+giờ\s+hết', 'giúp bạn dễ dàng hơn')),
    Tell('hy-vong-da-mang-den', PHRASE, 'Kết bài sáo rỗng', 'Kết bằng bước tiếp theo cụ thể.',
         text='hy vọng bài viết đã mang đến'),
    Tell('hy-vong-da-giup', PHRASE, 'Kết bài sáo rỗng', 'Kết bằng bước tiếp theo cụ thể.',
         text='hy vọng bài viết này đã giúp'),
    Tell('chuc-ban-thanh-cong', PHRASE, 'Kết bài sáo rỗng', 'Bỏ lời chúc. Kết bằng bước tiếp theo cụ thể.',
         text='chúc bạn thành công',
         rewrite=(r'chúc\s+(?:các\s+)?bạn\s+thành\s+công[ \t]*[.!]*[ \t]*', '')),
    Tell('dieu-nay-cho-thay-rang', PHRASE, 'Câu đệm', _FIX_CUT,
         text='điều này cho thấy rằng',
         rewrite=(r'điều\s+này\s+cho\s+thấy\s+rằng', 'điều này cho thấy')),
    Tell('co-the-noi-rang', PHRASE, 'Câu đệm', _FIX_CUT,
         text='có thể nói rằng',
         rewrite=(r'có\s+thể\s+nói\s+rằng\s*', '')),
    Tell('yeu-to-quan-trong-nhat', PHRASE, _LABEL_WORN, 'Xếp hạng cụ thể hoặc bỏ.',
         text='một trong những yếu tố quan trọng nhất',
         rewrite=(r'một\s+trong\s+những\s+yếu\s+tố\s+quan\s+trọng\s+nhất', 'một yếu tố quan trọng')),
    Tell('phat-trien-manh-me', PHRASE, 'Mở bài sáo rỗng', 'Vào thẳng vấn đề.',
         text='với sự phát triển mạnh mẽ của',
         rewrite=(r'với\s+sự\s+phát\s+triển\s+mạnh\s+mẽ\s+của', 'nhờ sự phát triển của')),
    Tell('nhu-cau-ngay-cang-cao', PHRASE, _LABEL_WORN, 'Đưa số liệu về nhu cầu thay vì tính từ.',
         text='đáp ứng nhu cầu ngày càng cao',
         rewrite=(r'đáp\s+ứng\s+nhu\s+cầu\s+ngày\s+càng\s+cao', 'đáp ứng nhu cầu ngày càng lớn')),
    Tell('khong-co-gi-ngac-nhien', PHRASE, 'Câu đệm', _FIX_CUT, text='không có gì ngạc nhiên khi'),
    Tell('hay-cung-tim-hieu', PHRASE, 'Dẫn dắt thừa', 'Bỏ. Người đọc đã bấm vào bài rồi.',
         text='hãy cùng tìm hiểu'),
    Tell('bai-viet-nay-se-giup-ban', PHRASE, 'Meta thừa', 'Bỏ. Bắt đầu bằng nội dung.',
         text='bài viết này sẽ giúp bạn'),
    Tell('hy-vong-nhung-chia-se', PHRASE, 'Kết bài sáo rỗng', 'Kết bằng bước tiếp theo cụ thể.',
         text='hy vọng những chia sẻ trên'),

    # ---- TRIGGER: scored per 1,000 syllables ----
    Tell('vo-cung-quan-trong', TRIGGER, _LABEL_WORN, _FIX_CONCRETE, text='vô cùng quan trọng'),
    Tell('dong-vai-tro-quan-trong', TRIGGER, _LABEL_WORN, _FIX_CONCRETE, text='đóng vai trò quan trọng'),
    Tell('khong-the-phu-nhan', TRIGGER, 'Khẳng định rỗng', _FIX_CUT, text='không thể phủ nhận'),
    Tell('de-dang-hon-bao-gio-het-trigger', TRIGGER, 'Hứa hẹn mơ hồ', _FIX_CONCRETE,
         text='dễ dàng hơn bao giờ hết'),
    Tell('vai-tro-then-chot', TRIGGER, _LABEL_WORN, _FIX_CONCRETE, text='vai trò then chốt'),
    Tell('mot-cach-toan-dien', TRIGGER, _LABEL_WORN, _FIX_CONCRETE, text='một cách toàn diện'),
    Tell('het-suc-quan-trong', TRIGGER, _LABEL_WORN, _FIX_CONCRETE, text='hết sức quan trọng'),
    Tell('chia-khoa-thanh-cong', TRIGGER, _LABEL_WORN, _FIX_CONCRETE, text='chìa khóa thành công'),
    Tell('buoc-tien-quan-trong', TRIGGER, _LABEL_WORN, _FIX_CONCRETE, text='bước tiến quan trọng'),
    Tell('yeu-to-then-chot', TRIGGER, _LABEL_WORN, _FIX_CONCRETE, text='yếu tố then chốt'),
    Tell('xu-huong-tat-yeu', TRIGGER, _LABEL_WORN, _FIX_CONCRETE, text='xu hướng tất yếu'),
    Tell('khong-ngung-phat-trien', TRIGGER, _LABEL_WORN, _FIX_CONCRETE, text='không ngừng phát triển'),
    Tell('dong-gop-to-lon', TRIGGER, _LABEL_WORN, _FIX_CONCRETE, text='đóng góp to lớn'),
    Tell('vai-tro-khong-the-thay-the', TRIGGER, _LABEL_WORN, _FIX_CONCRETE,
         text='vai trò không thể thay thế'),
    Tell('giai-phap-toi-uu', TRIGGER, _LABEL_WORN, _FIX_CONCRETE, text='giải pháp tối ưu'),
    Tell('trai-nghiem-tuyet-voi', TRIGGER, _LABEL_WORN, _FIX_CONCRETE, text='trải nghiệm tuyệt vời'),
    Tell('buoc-ngoat-quan-trong', TRIGGER, _LABEL_WORN, _FIX_CONCRETE, text='bước ngoặt quan trọng'),
    Tell('tiem-nang-to-lon', TRIGGER, _LABEL_WORN, _FIX_CONCRETE, text='tiềm năng to lớn'),
    Tell('gia-tri-to-lon', TRIGGER, _LABEL_WORN, _FIX_CONCRETE, text='giá trị to lớn'),
    Tell('cot-moc-quan-trong', TRIGGER, _LABEL_WORN, _FIX_CONCRETE, text='cột mốc quan trọng'),

    # ---- ADVISORY: reported, never scored ----
    Tell('da-va-dang', ADVISORY, 'Cụm dễ thừa', 'Dùng "đang" nếu chỉ có một nghĩa.',
         text='đã và đang', rewrite=(r'đã\s+và\s+đang\s+', 'đang ')),
    Tell('adv-boi-canh-hien-nay', ADVISORY, 'Cụm dễ thừa', _FIX_CUT, text='trong bối cảnh hiện nay'),
    Tell('adv-vai-tro-quan-trong', ADVISORY, 'Cụm dễ thừa', _FIX_CONCRETE, text='vai trò quan trọng'),
    Tell('adv-ngay-cang-pho-bien', ADVISORY, 'Cụm dễ thừa', _FIX_CONCRETE, text='ngày càng phổ biến'),
    Tell('adv-ngay-cang-tang', ADVISORY, 'Cụm dễ thừa', _FIX_CONCRETE, text='ngày càng tăng'),
    Tell('adv-khong-the-thieu', ADVISORY, 'Cụm dễ thừa', _FIX_CONCRETE, text='không thể thiếu'),
    Tell('adv-hieu-qua-cao', ADVISORY, 'Cụm dễ thừa', _FIX_CONCRETE, text='hiệu quả cao'),
    Tell('adv-chat-luong-cao', ADVISORY, 'Cụm dễ thừa', _FIX_CONCRETE, text='chất lượng cao'),
    Tell('adv-nhu-cau-ngay-cang-cao', ADVISORY, 'Cụm dễ thừa', _FIX_CONCRETE, text='nhu cầu ngày càng cao'),
    Tell('adv-xu-huong-phat-trien', ADVISORY, 'Cụm dễ thừa', _FIX_CONCRETE, text='xu hướng phát triển'),

    # ---- FORMULA: regexes for formulaic openers, connectives, sign-offs ----
    Tell('f-mo-bai-thoi-dai', FORMULA, 'Mở bài sáo rỗng', 'Vào thẳng vấn đề người đọc đang gặp.',
         regex=r'trong\s+(?:thế\s+giới|thời\s+đại|bối\s+cảnh)\s+(?:ngày\s+nay|hiện\s+nay|'
               r'số\s+ho[áa]|công\s+nghệ\s+số|4\.0)'),
    Tell('f-khong-the-phu-nhan', FORMULA, 'Khẳng định rỗng',
         'Bỏ. Nếu đúng thì không cần nói là không thể phủ nhận.',
         regex=r'không\s+thể\s+phủ\s+nhận\s+(?:rằng|là)'),
    Tell('f-dieu-quan-trong', FORMULA, 'Câu đệm', 'Bỏ cụm này và giữ lại nội dung phía sau.',
         regex=r'điều\s+(?:quan\s+trọng|đáng\s+lưu\s+ý)\s+(?:cần\s+)?(?:lưu\s+ý|nhớ|biết)\s+là'),
    Tell('f-hay-cung', FORMULA, 'Dẫn dắt thừa', 'Bỏ. Người đọc đã bấm vào bài rồi.',
         regex=r'hãy\s+cùng\s+(?:đi\s+sâu|tìm\s+hiểu|khám\s+phá|điểm\s+qua)'),
    Tell('f-tom-lai', FORMULA, 'Kết bài sáo rỗng', 'Kết bằng một hành động cụ thể.',
         regex=r'(?:tóm\s+lại|nhìn\s+chung)\s*,?\s*(?:có\s+thể\s+thấy|chúng\s+ta\s+có\s+thể\s+thấy)'),
    Tell('f-vai-tro-quan-trong', FORMULA, _LABEL_WORN, 'Nói rõ nó làm gì.',
         regex=r'đóng\s+(?:một\s+)?vai\s+trò\s+(?:vô\s+cùng\s+)?quan\s+trọng'),
    Tell('f-ngay-cang-tro-nen', FORMULA, _LABEL_WORN, 'Đưa số liệu thay vì tính từ.',
         regex=r'ngày\s+càng\s+trở\s+nên\s+(?:phổ\s+biến|quan\s+trọng|cần\s+thiết)',
         rewrite=(r'ngày\s+càng\s+trở\s+nên\s+phổ\s+biến', 'ngày càng phổ biến')),
    Tell('f-yeu-to-then-chot', FORMULA, _LABEL_WORN, 'Xếp hạng cụ thể hoặc bỏ.',
         regex=r'là\s+một\s+trong\s+những\s+yếu\s+tố\s+(?:then\s+chốt|quan\s+trọng\s+nhất)'),
    Tell('f-giup-toi-uu', FORMULA, 'Hứa hẹn mơ hồ', 'Nêu con số cải thiện thực tế.',
         regex=r'giúp\s+(?:bạn\s+)?(?:tối\s+ưu\s+ho[áa]|nâng\s+cao|cải\s+thiện)\s+'
               r'(?:một\s+cách\s+)?(?:hiệu\s+quả|đáng\s+kể|tối\s+đa)'),
    Tell('f-trong-bai-viet-nay', FORMULA, 'Meta thừa', 'Bỏ. Bắt đầu bằng nội dung.',
         regex=r'trong\s+bài\s+viết\s+(?:này|dưới\s+đây)\s*,?\s*(?:chúng\s+ta|chúng\s+tôi|tôi)\s+sẽ'),
    Tell('f-hy-vong-bai-viet', FORMULA, 'Kết bài sáo rỗng', 'Kết bằng bước tiếp theo cụ thể.',
         regex=r'hy\s+vọng\s+(?:rằng\s+)?bài\s+viết\s+(?:này\s+)?(?:sẽ\s+|đã\s+)?'
               r'(?:hữu\s+ích|giúp\s+ích|giúp\s+được|mang\s+đến)',
         # Consume the whole sign-off sentence; deleting only the opening
         # clause left the orphan "cho bạn những thông tin hữu ích."
         rewrite=(r'hy\s+vọng\s+(?:rằng\s+)?bài\s+viết\s+(?:này\s+)?(?:sẽ\s+|đã\s+)?'
                  r'(?:hữu\s+ích|giúp\s+ích|giúp\s+được|mang\s+đến)[^.!?]*[.!?]?[ \t]*', '')),
    Tell('f-phat-trien-cong-nghe', FORMULA, 'Mở bài sáo rỗng', 'Vào thẳng vấn đề.',
         regex=r'với\s+sự\s+phát\s+triển\s+(?:không\s+ngừng\s+)?của\s+(?:công\s+nghệ|internet)'),

    # ---- RESIDUE: chat-turn leftovers, P0 ----
    Tell('r-hy-vong-bai-viet-nay', RESIDUE, 'Chatbot residue', 'Xóa câu này. Nó không dành cho người đọc.',
         regex=r'hy\s+vọng\s+bài\s+viết\s+này'),
    Tell('r-duoi-day-la', RESIDUE, 'Chatbot residue',
         'Xóa lời dẫn đầu bài và vào thẳng nội dung.',
         regex=r'^\s*dưới\s+đây\s+là\b', preamble_only=True),
    Tell('r-chac-chan-roi', RESIDUE, 'Chatbot residue', 'Xóa câu này. Nó không dành cho người đọc.',
         regex=r'chắc\s+chắn\s+rồi'),
    Tell('r-rat-vui-duoc-ho-tro', RESIDUE, 'Chatbot residue', 'Xóa câu này. Nó không dành cho người đọc.',
         regex=r'rất\s+vui\s+được\s+hỗ\s+trợ\s+bạn'),
    Tell('r-ban-co-muon-toi', RESIDUE, 'Chatbot residue', 'Xóa câu này. Nó không dành cho người đọc.',
         regex=r'bạn\s+có\s+muốn\s+(?:tôi|mình)'),
    Tell('r-hay-cho-toi-biet', RESIDUE, 'Chatbot residue', 'Xóa câu này. Nó không dành cho người đọc.',
         regex=r'hãy\s+cho\s+tôi\s+biết\s+nếu\s+bạn'),

    # ---- CLOSER: stock one-line paragraph closers ----
    Tell('c-doc-lai-cau-tren', CLOSER, 'Câu chốt sáo rỗng', _FIX_CUT, regex=r'hãy\s+đọc\s+lại\s+câu\s+trên'),
    Tell('c-mau-chot', CLOSER, 'Câu chốt sáo rỗng', _FIX_CUT,
         regex=r'đó' + _INTENSIFIER + r'là\s+mấu\s+chốt'),
    Tell('c-cot-loi', CLOSER, 'Câu chốt sáo rỗng', _FIX_CUT,
         regex=r'đó' + _INTENSIFIER + r'là\s+(?:điều|vấn\s+đề)\s+(?:cốt\s+lõi|quan\s+trọng)'),
    Tell('c-tham', CLOSER, 'Câu chốt sáo rỗng', _FIX_CUT, regex=r'hãy\s+để\s+điều\s+đó\s+thấm'),
    Tell('c-nam-o-do', CLOSER, 'Câu chốt sáo rỗng', _FIX_CUT, regex=r'vấn\s+đề\s+(?:chính\s+)?nằm\s+ở\s+đó'),
    Tell('c-ly-do', CLOSER, 'Câu chốt sáo rỗng', _FIX_CUT, regex=r'và\s+đó\s+là\s+lý\s+do'),
)


def tell_regex(tell: Tell) -> str:
    """The detection regex for a tell (derived from ``text`` for literal tiers)."""
    if tell.regex is not None:
        return tell.regex
    assert tell.text is not None, tell.id
    return _phrase_regex(tell.text)


def tells_in(*tiers: str) -> tuple[Tell, ...]:
    return tuple(t for t in VI_TELLS if t.tier in tiers)


_COMPILED = {t.id: re.compile(tell_regex(t), re.IGNORECASE | re.MULTILINE) for t in VI_TELLS}

#: (regex, label, fix) triples, the shape ``vi_prose.AI_TELLS`` always had.
FORMULA_TELLS: tuple[tuple[str, str, str], ...] = tuple(
    (t.regex, t.label, t.fix) for t in tells_in(FORMULA) if t.regex is not None
)


def scan_tells(text: str, tiers: tuple[str, ...] = SCORED_TIERS) -> list[dict[str, Any]]:
    """Find scored tells in ``text``; overlapping matches keep only the longest.

    "không thể phủ nhận rằng" is a PHRASE, a TRIGGER ("không thể phủ nhận") and
    a FORMULA at once; it is one tell in the report, not three.
    """
    candidates: list[tuple[int, int, Tell]] = []
    for tell in tells_in(*tiers):
        for m in _COMPILED[tell.id].finditer(text):
            if m.end() > m.start():
                candidates.append((m.start(), m.end(), tell))
    candidates.sort(key=lambda c: (c[0], -(c[1] - c[0])))
    kept: list[dict[str, Any]] = []
    last_end = -1
    for start, end, tell in candidates:
        if start < last_end:
            continue
        last_end = end
        kept.append({
            'id': tell.id, 'tier': tell.tier, 'label': tell.label, 'fix': tell.fix,
            'match': text[start:end], 'start': start, 'end': end,
            'line': text.count('\n', 0, start) + 1,
        })
    return kept


def residue_patterns(*, preamble: bool) -> tuple[str, ...]:
    """Chatbot-residue regexes. ``preamble=True`` returns only the ones that
    are residue solely on the first prose line ("Dưới đây là ...")."""
    return tuple(
        t.regex for t in tells_in(RESIDUE)
        if t.regex is not None and t.preamble_only == preamble
    )


def closer_patterns() -> tuple[str, ...]:
    return tuple(t.regex for t in tells_in(CLOSER) if t.regex is not None)


def rewrite_table() -> tuple[tuple[str, str, str], ...]:
    """(regex, replacement, label) rows for the humanizer, in list order."""
    return tuple((t.rewrite[0], t.rewrite[1], t.id) for t in VI_TELLS if t.rewrite is not None)


def _texts(tier: str) -> tuple[str, ...]:
    return tuple(t.text for t in VI_TELLS if t.tier == tier and t.text is not None)


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
    # G1 (Phase G) word lists, now DERIVED from VI_TELLS above (Phase J):
    # there is one list, and this is a view of it. See
    # skills/blog/references/vi-word-list-tiering.md for the bar an entry
    # must clear to be scored versus advisory.
    #
    # Scored: counted into ai_trigger_words / per_1k and ai_phrase_count,
    # the same way the English lists are scored.
    'ai_phrases': _texts(PHRASE),
    'ai_trigger_words': _texts(TRIGGER),
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
    'ai_advisory_phrases': _texts(ADVISORY),

    # ------------------------------------------------------------------
    # Phase J: draft-mode rubric inputs.
    #
    # Trust and contact boilerplate belongs in the site footer, not in the
    # post body (docs/review/02 section 3, item 2). A hit is a P1 issue.
    'trust_boilerplate_patterns': (
        r'bài\s+viết\s+(?:này\s+)?(?:đã\s+)?được\s+(?:biên\s+tập|kiểm\s+chứng|kiểm\s+duyệt|'
        r'thẩm\s+định|rà\s+soát)(?:\s+và\s+(?:biên\s+tập|kiểm\s+chứng|kiểm\s+duyệt|thẩm\s+định))?\s+bởi',
        r'về\s+chúng\s+tôi',
        r'liên\s+hệ\s+(?:với\s+)?chúng\s+tôi',
        r'thông\s+tin\s+liên\s+hệ',
        r'đội\s+ngũ\s+biên\s+tập\s+của\s+chúng\s+tôi',
    ),
    # Words that mark a number as an illustration, not a measured fact.
    'illustrative_markers': (
        'ví dụ', 'giả sử', 'giả định', 'minh họa', 'chẳng hạn', 'ước tính',
        'tưởng tượng', 'thử tính',
    ),
    # "According to X" style attribution. A number attached to one of these
    # with no link or (nguồn, năm) reference is an unsourced authority claim.
    'attribution_patterns': (
        r'theo\s+(?:một\s+)?(?:nghiên\s+cứu|khảo\s+sát|báo\s+cáo|thống\s+kê|số\s+liệu|điều\s+tra)',
        r'(?:nghiên\s+cứu|khảo\s+sát|báo\s+cáo|thống\s+kê|điều\s+tra)\s+(?:của|từ|cho\s+thấy|chỉ\s+ra)',
        r'theo\s+(?:[A-ZĐ][\w]+)(?:\s+[A-ZĐ][\w]+)*\s*,',
    ),
    # Vietnamese example markers (the English list in analyze_engagement
    # never matched these).
    'example_patterns': (
        r'ví\s+dụ', r'chẳng\s+hạn', r'giả\s+sử', r'hãy\s+tưởng\s+tượng', r'cụ\s+thể\s+là',
        r'thử\s+tính', r'hãy\s+xem',
    ),
    # Generic bylines that name no person.
    'generic_authors': (
        'admin', 'administrator', 'staff', 'team', 'quản trị viên', 'ban biên tập',
        'nhóm nội dung', 'đội ngũ', 'biên tập viên',
    ),
    # Sentence-length threshold (syllables) from arXiv 2411.04756.
    'long_sentence_syllables': 20,

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
