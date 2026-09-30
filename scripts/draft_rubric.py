#!/usr/bin/env python3
"""Draft-mode rubric: what a Vietnamese reader can judge about an unpublished post.

The full 100-point rubric in ``analyze_blog.calculate_score`` measures a
published page: internal links, about/contact, JSON-LD, Open Graph, crawler
access. A draft in ``blog-results/`` can never have those, so scoring it with
the full rubric made real posts and AI slop score alike (review 2026-09-17,
finding A3: 48, 42 and 48).

This module scores only what the draft controls. Site-level items are reported
in a pre-publish checklist and are NOT in the denominator.

Weights (sum 100; an item that does not apply is left out of the denominator
and the total is rescaled, it is never scored as a loss):

    register consistency          12   vi only
    lexical tell density          16
    structural cluster            12   ai_structure.py cluster score
    sentence-length distribution   8   vs the 20-syllable threshold
    evidence discipline           14   numbers need a source or an illustrative marker
    title convention               6
    snippet length (title, meta)   6
    heading structure              8   scaled to post length
    reader utility                 8   scaled to post length
    frontmatter                    6
    no trust boilerplate in body   4

P0 (blocks Gate 4 regardless of the number): register drift above the ratio,
chatbot residue, fabricated statistic, missing legal disclosure (``legal_disclosure_p0``,
shared with Gate 5 via ``vi_compliance``).

Stdlib only. Messages are Vietnamese for ``lang: vi`` posts and English
otherwise.
"""

from __future__ import annotations

import re
from typing import Any

import vi_compliance
import vi_profile
import vi_text

GATE4_MIN_SCORE = 85

#: Posts shorter than this many syllables/words-equivalents are not asked for
#: sections or reader-utility scaffolding (no word-count target, ever).
SHORT_POST_UNITS = 400

#: Below this there is no text to judge: every prose item would pass by
#: default, which is a vacuous 100, not evidence of quality. Not a length
#: target; a stub is reported as unscorable and cannot pass Gate 4.
STUB_UNITS = 120
STUB_SCORE_CAP = 50

WEIGHTS: dict[str, int] = {
    'register': 12,
    'lexical_tells': 16,
    'structure_cluster': 12,
    'sentence_length': 8,
    'evidence': 14,
    'title_convention': 6,
    'snippet_length': 6,
    'headings': 8,
    'reader_utility': 8,
    'frontmatter': 6,
    'no_trust_boilerplate': 4,
}

GROUPS: dict[str, tuple[str, ...]] = {
    'voice_and_register': ('register', 'lexical_tells', 'structure_cluster', 'sentence_length'),
    'evidence': ('evidence',),
    'search_basics': ('title_convention', 'snippet_length', 'headings'),
    'reader_utility': ('reader_utility',),
    'draft_hygiene': ('frontmatter', 'no_trust_boilerplate'),
}

ITEM_LABELS_VI = {
    'register': 'Xưng hô nhất quán',
    'lexical_tells': 'Mật độ cụm từ sáo rỗng',
    'structure_cluster': 'Cấu trúc câu chữ (dấu hiệu máy)',
    'sentence_length': 'Độ dài câu',
    'evidence': 'Số liệu có nguồn hoặc ghi rõ là ví dụ',
    'title_convention': 'Quy ước tiêu đề',
    'snippet_length': 'Độ dài tiêu đề và mô tả',
    'headings': 'Bố cục tiêu đề mục',
    'reader_utility': 'Ví dụ, danh sách, tóm tắt cho người đọc',
    'frontmatter': 'Thông tin đầu bài (frontmatter)',
    'no_trust_boilerplate': 'Không chèn giới thiệu/liên hệ vào thân bài',
}


def _m(lang: str, vi: str, en: str) -> str:
    return vi if lang == 'vi' else en


# ---------------------------------------------------------------------------
# Small measurements
# ---------------------------------------------------------------------------

_SENT_SPLIT = re.compile(r'(?<=[.!?…])\s+')
_STAT_RE = re.compile(r'\d+(?:[.,]\d+)?\s*(?:%|phần\s+trăm|percent)', re.IGNORECASE)
_LINK_RE = re.compile(r'\[[^\]]+\]\(https?://')
_REF_RE = re.compile(r'\([^)]*(?:19|20)\d{2}[^)]*\)|(?:nguồn|source)\s*:', re.IGNORECASE)


def _paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]


def _is_prose_paragraph(paragraph: str) -> bool:
    first = paragraph.lstrip()
    return not (first.startswith('#') or first.startswith('|') or first.startswith('```'))


def sentence_lengths(plain_text: str, language: str) -> list[int]:
    """Sentence lengths in syllables (vi) or words (everything else)."""
    if language == 'vi':
        parts = [s for s in re.split(r'[.!?…]+|\n+', plain_text)
                 if vi_text.count_syllables(s) >= 2]
        return [vi_text.count_syllables(s) for s in parts]
    parts = re.split(r'(?<=[.!?])\s+', plain_text)
    return [len(s.split()) for s in parts if len(s.split()) > 2]


def is_title_case(text: str) -> bool:
    """Every-word capitalisation, a machine tell in Vietnamese titles.

    The first word is always capitalised; acronyms and numbers are ignored.
    """
    words = [w for w in re.findall(r"[^\W\d_]+", text, re.UNICODE)]
    rest = [w for w in words[1:] if len(w) >= 2 and not w.isupper()]
    if len(rest) < 3:
        return False
    capitalised = sum(1 for w in rest if w[0].isupper())
    return capitalised / len(rest) >= 0.75


_TITLE_HOOKS_VI = re.compile(
    r'(?:^\s*\d+\s|\?\s*$|\bcó\s+tốt\s+không\b|\blà\s+gì\b|\bcách\b|\bnên\s+(?:mua|chọn|dùng)\b|'
    r'\bcó\s+nên\b|\bvì\s+sao\b|\btại\s+sao\b|\bkinh\s+nghiệm\b|\bhướng\s+dẫn\b)',
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------


def legal_disclosure_p0(frontmatter: dict[str, Any], body: str, language: str) -> list[dict[str, Any]]:
    """Missing legal disclosure on sponsored/affiliate/health posts (Phase K).

    Delegates to ``vi_compliance.check``, the same implementation Gate 5 in
    ``blog_preflight.py`` uses, so the two gates cannot disagree. Rules:
    ``sponsored: true`` and ``affiliate: true`` need a disclosure block;
    ``topic_class: health`` mentioning thực phẩm chức năng needs the
    Circular 09/2015/TT-BYT disclaimer. Posts without those keys return no
    findings. Each finding ({'code', 'message'}) becomes a P0. The message is
    Vietnamese whatever ``language`` is: the sentence to add is Vietnamese.
    """
    return vi_compliance.check(frontmatter, body)


# ---------------------------------------------------------------------------
# Evidence discipline
# ---------------------------------------------------------------------------


def evidence_findings(body: str, language: str) -> dict[str, Any]:
    """Classify every percentage claim as sourced, illustrative or unsourced.

    * sourced: a link or a (source, year) reference in the same paragraph;
    * illustrative: an illustrative marker ("ví dụ", "giả sử", "nếu" ...) in the
      same sentence or earlier in the same paragraph;
    * first-hand: the sentence says the author measured it ("mình đo", "chúng
      tôi khảo sát") and gives the number itself;
    * unsourced: none of the above.

    An unsourced number attributed to an outside authority ("theo một nghiên
    cứu", "khảo sát cho thấy") is a suspected fabricated statistic (P0): the
    reader is told someone else said it and cannot check.
    """
    profile = vi_profile.VI_PROFILE
    markers = tuple(profile['illustrative_markers']) if language == 'vi' else (
        'for example', 'for instance', 'suppose', 'assume', 'imagine',
    )
    conditional = 'nếu' if language == 'vi' else 'if '
    attribution = [re.compile(p, re.IGNORECASE) for p in profile['attribution_patterns']] if language == 'vi' else [
        re.compile(r'(?:according\s+to|a\s+(?:recent\s+)?(?:study|survey|report)\s+(?:by|from|found|shows))', re.IGNORECASE),
    ]
    first_hand = re.compile(
        r'(?:mình|tôi|chúng\s+tôi|chúng\s+mình)\s+(?:đã\s+)?(?:đo|khảo\s+sát|thống\s+kê|tính|thử|'
        r'phát\s+hiện|thu\s+thập|phân\s+tích|ghi\s+nhận|quan\s+sát|đếm|so\s+sánh|theo\s+dõi)|'
        r'dữ\s+liệu\s+(?:do\s+|của\s+)?(?:mình|tôi|chúng\s+tôi|chúng\s+mình)|'
        r'\b(?:i|we)\s+(?:measured|surveyed|counted|tested|analy[sz]ed|found)\b',
        re.IGNORECASE,
    )

    sourced = illustrative = own = 0
    unsourced: list[dict[str, Any]] = []
    fabricated: list[dict[str, Any]] = []

    line_of = _line_index(body)
    for paragraph in _paragraphs(body):
        if not _is_prose_paragraph(paragraph):
            continue
        has_ref = bool(_LINK_RE.search(paragraph) or _REF_RE.search(paragraph))
        seen_marker = False
        for sentence in _SENT_SPLIT.split(paragraph):
            low = sentence.lower()
            if any(mk in low for mk in markers):
                seen_marker = True
            stat = _STAT_RE.search(sentence)
            if not stat:
                continue
            entry = {'sentence': re.sub(r'\s+', ' ', sentence).strip()[:160], 'line': line_of(paragraph)}
            hypothetical = conditional in low[:stat.start()]
            if has_ref:
                sourced += 1
            elif seen_marker:
                illustrative += 1
            elif any(p.search(sentence) for p in attribution):
                # Attributed to an authority the reader cannot check.
                fabricated.append(entry)
            elif hypothetical:
                illustrative += 1
            elif first_hand.search(sentence):
                own += 1
            else:
                unsourced.append(entry)
    return {
        'sourced': sourced,
        'illustrative': illustrative,
        'first_hand': own,
        'unsourced': unsourced,
        'fabricated': fabricated,
        'total': sourced + illustrative + own + len(unsourced) + len(fabricated),
    }


def _line_index(body: str):
    def line_of(paragraph: str) -> int:
        pos = body.find(paragraph[:60])
        return body.count('\n', 0, pos) + 1 if pos >= 0 else 0
    return line_of


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def _band(value: float, bands: tuple[tuple[float, int], ...], floor: int = 0) -> int:
    for limit, points in bands:
        if value <= limit:
            return points
    return floor


def calculate_draft_score(analysis: dict[str, Any]) -> dict[str, Any]:
    language = analysis.get('language', 'en')
    vi = language == 'vi'
    fm = analysis['frontmatter']
    body = analysis.get('_body_text', '')
    plain = analysis.get('_plain_text', '')
    headings = analysis['headings']
    issues: list[dict[str, Any]] = []
    p0: list[dict[str, Any]] = []
    items: dict[str, dict[str, Any]] = {}

    units = vi_text.count_syllables(plain) if vi else len(plain.split())
    short_post = units < SHORT_POST_UNITS

    def add(name: str, score: float, detail: str, applicable: bool = True) -> None:
        items[name] = {
            'score': int(round(score)) if applicable else 0,
            'max': WEIGHTS[name],
            'applicable': applicable,
            'detail': detail,
        }

    def issue(category: str, severity: str, text: str) -> None:
        issues.append({'category': category, 'severity': severity, 'issue': text})

    # 1. Register (vi only) ------------------------------------------------
    reg = analysis.get('vi_register')
    if vi and reg is not None:
        if not reg['consistent']:
            lines = sorted({r['line'] for r in reg['off_register']})
            shown = ', '.join(str(n) for n in lines[:10])
            msg = (f'Xưng hô không nhất quán: bài chủ yếu dùng ngôi "{reg["dominant_register"]}", '
                   f'nhưng dòng {shown} dùng ngôi khác '
                   f'({", ".join(reg["drift_registers"])}). Chọn một cách xưng hô cho cả bài.')
            p0.append({'code': 'register_drift', 'message': msg, 'lines': lines})
            issue('voice', 'high', msg)
            add('register', 0, msg)
        elif reg['tolerated']:
            add('register', 9, f'{len(reg["tolerated"])} câu lạc ngôi nhưng dưới ngưỡng '
                               f'{reg["drift_threshold"]} câu, chỉ ghi nhận.')
        else:
            add('register', 12, 'Nhất quán.')
    else:
        add('register', 0, 'Chỉ áp dụng cho tiếng Việt.', applicable=False)

    # 2. Lexical tells -----------------------------------------------------
    tells = analysis['lexical_tells']
    density = tells['density_per_1000']
    pts = _band(density, ((0.0, 16), (1.0, 13), (2.0, 10), (4.0, 6), (8.0, 3)))
    if density > 0:
        sample = ', '.join(f'"{i["match"].strip()}"' for i in tells['items'][:4])
        if density > 2.0:
            issue('voice', 'high', _m(
                language,
                f'Mật độ cụm từ sáo rỗng {density}/1000 (ngưỡng 2.0): {sample}. Viết lại bằng chi tiết cụ thể.',
                f'AI-phrase density {density}/1000 (threshold 2.0): {sample}. Rewrite with concrete detail.'))
        else:
            issue('voice', 'low', _m(
                language, f'Có cụm từ sáo rỗng ({density}/1000): {sample}.',
                f'Stock phrases present ({density}/1000): {sample}.'))
    add('lexical_tells', pts, f'{tells["count"]} cụm, {density}/1000 {tells["unit"]}.')

    # 3. Structural cluster ------------------------------------------------
    struct = analysis['ai_structure']
    cluster = struct['cluster_score']
    pts = {0: 12, 1: 10, 2: 7, 3: 3}.get(cluster, 0)
    if cluster >= 2:
        where = ', '.join(f'"{s["section"]}" ({", ".join(s["tells"])})' for s in struct['cluster_sections'][:3])
        issue('voice', 'medium', _m(
            language,
            f'Nhiều dấu hiệu cấu trúc máy viết cùng một mục (điểm cụm {cluster}): {where}.',
            f'Several structural AI tells share a section (cluster {cluster}): {where}.'))
    add('structure_cluster', pts, f'cluster_score={cluster}, {struct["finding_count"]} dấu hiệu.')
    residue = [f for f in struct['findings'] if f['check'] == 'chatbot_residue']
    for f in residue:
        msg = _m(language,
                 f'Dòng {f["line"]}: còn sót câu của chatbot ("{f["excerpt"].strip()[:60]}"). Xóa câu này.',
                 f'Line {f["line"]}: chatbot residue left in the text ("{f["excerpt"].strip()[:60]}"). Delete it.')
        p0.append({'code': 'chatbot_residue', 'message': msg, 'line': f['line']})
        issue('voice', 'high', msg)

    # 4. Sentence length ---------------------------------------------------
    lengths = sentence_lengths(plain, language)
    threshold = vi_profile.VI_PROFILE['long_sentence_syllables'] if vi else 20
    if lengths:
        over = sum(1 for n in lengths if n > threshold)
        ratio = over / len(lengths)
        extreme = sum(1 for n in lengths if n > 2 * threshold)
        pts = _band(ratio, ((0.30, 8), (0.40, 7), (0.50, 5), (0.65, 3)), floor=1)
        if extreme and pts > 6:
            pts = 6
        unit = _m(language, 'âm tiết', 'words')
        if ratio > 0.5 or extreme:
            issue('voice', 'medium', _m(
                language,
                f'{over}/{len(lengths)} câu dài hơn {threshold} {unit} ({ratio:.0%}), '
                f'{extreme} câu dài hơn {2 * threshold}. Tách bớt câu.',
                f'{over}/{len(lengths)} sentences longer than {threshold} {unit} ({ratio:.0%}), '
                f'{extreme} longer than {2 * threshold}. Split some.'))
        add('sentence_length', pts, f'{ratio:.0%} câu > {threshold} {unit}.')
    else:
        add('sentence_length', 0, 'Không có câu để đo.', applicable=False)

    # 5. Evidence discipline ----------------------------------------------
    ev = evidence_findings(body, language)
    if ev['fabricated']:
        for e in ev['fabricated']:
            msg = _m(language,
                     f'Dòng {e["line"]}: số liệu dẫn "nghiên cứu/khảo sát" nhưng không có liên kết hay nguồn: '
                     f'"{e["sentence"]}". Thêm nguồn kiểm chứng được hoặc bỏ.',
                     f'Line {e["line"]}: attributed statistic with no link or source: "{e["sentence"]}". '
                     'Add a verifiable source or remove it.')
            p0.append({'code': 'fabricated_statistic', 'message': msg, 'line': e['line']})
            issue('evidence', 'high', msg)
    for e in ev['unsourced']:
        issue('evidence', 'medium', _m(
            language,
            f'Dòng {e["line"]}: con số chưa có nguồn hoặc chưa ghi rõ là ví dụ: "{e["sentence"]}".',
            f'Line {e["line"]}: number with no source and not marked illustrative: "{e["sentence"]}".'))
    orig = analysis['originality']
    if orig.get('unsupported_experience_claims', 0) > 0:
        issue('evidence', 'medium', _m(
            language, 'Có câu kể kinh nghiệm cá nhân nhưng thiếu số đo hoặc chi tiết đi kèm.',
            'First-hand claims without supporting measurements or detail.'))
    penalty = 14 if ev['fabricated'] else 4 * len(ev['unsourced'])
    penalty += 3 if orig.get('unsupported_experience_claims', 0) else 0
    add('evidence', max(0, 14 - penalty),
        f'{ev["total"]} con số: {ev["sourced"]} có nguồn, {ev["illustrative"]} ví dụ, '
        f'{ev["first_hand"]} tự đo, {len(ev["unsourced"])} thiếu nguồn, {len(ev["fabricated"])} nghi bịa.')

    # 6. Title convention --------------------------------------------------
    title = fm.get('title', '')
    if not title:
        issue('search', 'high', _m(language, 'Thiếu tiêu đề trong frontmatter.', 'Missing title in frontmatter.'))
        add('title_convention', 0, 'Thiếu tiêu đề.')
    else:
        pts = 2
        notes = []
        if vi:
            if is_title_case(title):
                issue('search', 'medium', _m(
                    language,
                    f'Tiêu đề viết hoa từng chữ ("{title}"). Tiếng Việt chỉ viết hoa chữ đầu câu và tên riêng.',
                    ''))
                notes.append('Title Case')
            else:
                pts += 2
            h2s = [h['text'] for h in headings['headings'] if h['level'] == 2]
            if len(h2s) >= 3 and sum(1 for h in h2s if is_title_case(h)) / len(h2s) > 0.6:
                issue('search', 'low', 'Các tiêu đề mục viết hoa từng chữ. Viết hoa như một câu bình thường.')
                notes.append('H2 Title Case')
            else:
                pts += 1
            if _TITLE_HOOKS_VI.search(title):
                pts += 1
            has_diacritics = vi_text.is_vietnamese(plain)
            if has_diacritics and title == vi_text.to_ascii(title) and re.search(r'[A-Za-z]{3}', title):
                issue('search', 'medium', 'Tiêu đề không có dấu trong khi bài viết có dấu.')
                pts = max(pts - 2, 0)
                notes.append('không dấu')
        else:
            pts += 4
        add('title_convention', min(pts, 6), ', '.join(notes) or 'Đạt.')

    # 7. Snippet lengths ---------------------------------------------------
    desc = fm.get('description', fm.get('meta_description', ''))
    pts = 0
    notes = []
    if desc:
        pts += 2
        if 70 <= len(desc) <= 160:
            pts += 2
        else:
            notes.append(f'mô tả {len(desc)} ký tự (nên 70-160)')
            issue('search', 'low', _m(
                language, f'Mô tả dài {len(desc)} ký tự, nên trong khoảng 70-160.',
                f'Meta description is {len(desc)} characters; aim for 70-160.'))
    else:
        issue('search', 'high', _m(language, 'Thiếu mô tả (description) trong frontmatter.',
                                   'Missing meta description in frontmatter.'))
        notes.append('thiếu mô tả')
    if title and 25 <= len(title) <= 65:
        pts += 2
    elif title:
        notes.append(f'tiêu đề {len(title)} ký tự (nên 25-65)')
        issue('search', 'low', _m(
            language, f'Tiêu đề dài {len(title)} ký tự, nên trong khoảng 25-65.',
            f'Title is {len(title)} characters; aim for 25-65.'))
    add('snippet_length', pts, '; '.join(notes) or 'Đạt.')

    # 8. Headings ----------------------------------------------------------
    if short_post:
        add('headings', 0, 'Bài ngắn, không yêu cầu tiêu đề mục.', applicable=False)
    else:
        needed = 1 if units < 900 else 2 if units < 1500 else 3
        h2 = headings['h2_count']
        pts = 3 if h2 >= needed else (1 if h2 >= 1 else 0)
        if h2 < needed:
            issue('content', 'medium', _m(
                language, f'Bài dài nhưng chỉ có {h2} tiêu đề mục H2 (cần ít nhất {needed}).',
                f'Long post with {h2} H2 sections (need at least {needed}).'))
        if headings['hierarchy_clean']:
            pts += 2
        else:
            issue('content', 'medium', _m(language, 'Thứ bậc tiêu đề bị nhảy cấp (ví dụ H2 sang H4).',
                                          'Heading hierarchy skips a level.'))
        if headings['h1_count'] == 1 or (headings['h1_count'] == 0 and title):
            pts += 2
        values = [h['text'].strip().lower() for h in headings['headings']]
        if values and len(values) == len(set(values)):
            pts += 1
        add('headings', pts, f'{h2} H2.')

    # 9. Reader utility ----------------------------------------------------
    if short_post:
        add('reader_utility', 0, 'Bài ngắn, không yêu cầu.', applicable=False)
    else:
        eng = analysis['engagement']
        sd = analysis['structured_data']
        pts = 4 if eng['example_count'] >= 2 else 2 if eng['example_count'] >= 1 else 0
        if sd['table_count'] >= 1 or sd['unordered_list_items'] + sd['ordered_list_items'] >= 3:
            pts += 2
        if analysis['ai_citation_readiness'].get('has_tldr'):
            pts += 1
        if headings['h2_count'] >= 3:
            pts += 1
        if pts < 4:
            issue('content', 'low', _m(
                language, 'Thiếu ví dụ cụ thể, danh sách hoặc bảng giúp người đọc áp dụng.',
                'Add a concrete example, list or table the reader can apply.'))
        add('reader_utility', min(pts, 8), f'{eng["example_count"]} ví dụ.')

    # 10. Frontmatter ------------------------------------------------------
    pts = 0
    author = fm.get('author', fm.get('authors', ''))
    generic = {a.lower() for a in vi_profile.VI_PROFILE['generic_authors']} | {'admin', 'administrator', 'staff', 'team'}
    if author and author.strip().lower() not in generic:
        pts += 2
    elif author:
        pts += 1
        issue('hygiene', 'medium', _m(
            language, f'Tác giả "{author}" không phải tên người thật. Dùng tên tác giả cụ thể.',
            f'Generic author "{author}". Use a real person.'))
    else:
        issue('hygiene', 'high', _m(language, 'Thiếu tác giả (author) trong frontmatter.',
                                    'No author in frontmatter.'))
    if fm.get('date') or fm.get('datePublished'):
        pts += 1
    else:
        issue('hygiene', 'medium', _m(language, 'Thiếu ngày (date) trong frontmatter.', 'No date in frontmatter.'))
    if fm.get('slug'):
        pts += 1
    else:
        issue('hygiene', 'medium', _m(language, 'Thiếu slug trong frontmatter.', 'No slug in frontmatter.'))
    if fm.get('canonical'):
        pts += 1
    else:
        issue('hygiene', 'medium', _m(language, 'Thiếu canonical trong frontmatter.', 'No canonical in frontmatter.'))
    if (not vi) or fm.get('lang') or fm.get('language'):
        pts += 1
    else:
        issue('hygiene', 'high', 'Thiếu "lang: vi" trong frontmatter. Bài sẽ bị chấm theo mẫu tiếng Anh.')
    add('frontmatter', pts, f'{pts}/6.')

    # 11. Trust boilerplate inside the body --------------------------------
    patterns = vi_profile.VI_PROFILE['trust_boilerplate_patterns'] if vi else (
        r'reviewed\s+and\s+(?:edited|fact.?checked)\s+by', r'about\s+us', r'contact\s+us',
    )
    hits = [m for pat in patterns for m in re.finditer(pat, plain, re.IGNORECASE)]
    if hits:
        issue('hygiene', 'medium', _m(
            language,
            f'Thân bài có đoạn giới thiệu/kiểm chứng/liên hệ ("{hits[0].group(0)}"). '
            'Chuyển phần này xuống chân trang của website, đừng để trong bài.',
            f'Trust/contact boilerplate inside the post body ("{hits[0].group(0)}"). '
            'It belongs once in the site footer.'))
        add('no_trust_boilerplate', 0, f'{len(hits)} chỗ.')
    else:
        add('no_trust_boilerplate', 4, 'Đạt.')

    # Legal disclosure (Phase K, shared with Gate 5) --------------------------------
    for finding in legal_disclosure_p0(fm, body, language):
        p0.append({'code': finding.get('code', 'legal_disclosure'), 'message': finding['message']})
        issue('compliance', 'high', finding['message'])

    # Total ----------------------------------------------------------------
    applicable_max = sum(v['max'] for v in items.values() if v['applicable'])
    earned = sum(v['score'] for v in items.values() if v['applicable'])
    total = int(round(earned / applicable_max * 100)) if applicable_max else 0
    capped = None
    if units < STUB_UNITS:
        capped = f'stub:{units}'
        issue('content', 'high', _m(
            language,
            f'Bài chỉ có {units} {"âm tiết" if vi else "words"}, quá ít để chấm điểm có nghĩa. '
            'Viết thêm nội dung thật trước khi chấm.',
            f'Only {units} words: too little text to score meaningfully. Write the substance first.'))
        total = min(total, STUB_SCORE_CAP)

    categories: dict[str, int] = {}
    category_details: dict[str, dict[str, Any]] = {}
    for group, names in GROUPS.items():
        mx = sum(items[n]['max'] for n in names if items[n]['applicable'])
        sc = sum(items[n]['score'] for n in names if items[n]['applicable'])
        categories[group] = sc
        category_details[group] = {
            'score': sc, 'max': mx,
            'breakdown': {n: items[n]['score'] for n in names if items[n]['applicable']},
        }

    severity_order = {'high': 0, 'medium': 1, 'low': 2}
    issues.sort(key=lambda x: severity_order.get(x['severity'], 3))
    return {
        'mode': 'draft',
        'total': total,
        'rating': rating_for(total),
        'methodology': 'draft_prose_rubric',
        'calibrated_probability': False,
        'gate4': {
            'min_score': GATE4_MIN_SCORE,
            'p0_count': len(p0),
            'ready': total >= GATE4_MIN_SCORE and not p0,
        },
        'p0': p0,
        'capped': capped,
        'items': items,
        'applicable_max': applicable_max,
        'excluded_from_denominator': [n for n, v in items.items() if not v['applicable']],
        'categories': categories,
        'category_details': category_details,
        'issues': issues,
        'prepublish_checklist': prepublish_checklist(analysis),
    }


def rating_for(total: int) -> str:
    if total >= 90:
        return 'Exceptional'
    if total >= 80:
        return 'Strong'
    if total >= 70:
        return 'Acceptable'
    if total >= 60:
        return 'Below Standard'
    return 'Rewrite'


# ---------------------------------------------------------------------------
# Pre-publish checklist: site-level items, outside the score
# ---------------------------------------------------------------------------


def prepublish_checklist(analysis: dict[str, Any]) -> list[dict[str, str]]:
    """Site-level items a draft cannot have. Reported, never scored."""
    lang = analysis.get('language', 'en')
    links = analysis['links']
    images = analysis['images']
    fm = analysis['frontmatter']

    def row(key: str, ok: bool | None, vi: str, en: str) -> dict[str, str]:
        status = 'ok' if ok else ('todo' if ok is False else 'unknown')
        return {'item': key, 'status': status, 'note': _m(lang, vi, en)}

    return [
        row('internal_links', links['internal_count'] >= 3 or None,
            f'Liên kết nội bộ: {links["internal_count"]}. Khi đăng, thêm 3-10 liên kết tới bài liên quan trên site.',
            f'Internal links: {links["internal_count"]}. When published, add 3-10 links to related posts.'),
        row('about_contact', None,
            'Trang giới thiệu và liên hệ: đặt một lần ở chân trang website, không đặt trong bài.',
            'About and contact pages: place once in the site footer, not in the post.'),
        row('schema_jsonld', None,
            'JSON-LD BlogPosting: được tạo khi render HTML (blog_render.py), kiểm tra ở Gate 3.',
            'JSON-LD BlogPosting: emitted at render time (blog_render.py), checked at Gate 3.'),
        row('open_graph', None,
            'Thẻ Open Graph và Twitter Card: được tạo khi render, kiểm tra ở Gate 5.',
            'Open Graph and Twitter Card tags: emitted at render time, checked at Gate 5.'),
        row('crawler_access', None,
            'robots.txt và quyền cho trình thu thập AI: kiểm tra trên site thật sau khi đăng.',
            'robots.txt and AI-crawler access: check on the live site after publishing.'),
        row('canonical_live', (bool(fm.get('canonical')) and 'example.' not in fm.get('canonical', '')) or False,
            'Canonical phải trỏ đúng URL thật của bài (hiện là địa chỉ mẫu hoặc chưa có).'
            if 'example.' in fm.get('canonical', '') or not fm.get('canonical')
            else 'Canonical đã có; xác nhận nó trỏ đúng URL thật sau khi đăng.',
            'Canonical must point at the real published URL (currently a placeholder or missing).'
            if 'example.' in fm.get('canonical', '') or not fm.get('canonical')
            else 'Canonical is set; confirm it matches the live URL after publishing.'),
        row('images_alt', (images['without_alt_text'] == 0) if images['count'] else None,
            'Ảnh có mô tả thay thế (alt) đầy đủ.', 'All images have alt text.'),
        row('legal_disclosure', None,
            'Khai báo quảng cáo/tiếp thị liên kết/khuyến cáo thực phẩm chức năng: đã kiểm tra tự động '
            'ở Gate 4 (P0) và Gate 5 khi có sponsored/affiliate/topic_class.',
            'Sponsored/affiliate/functional-food disclosure: checked automatically as a Gate 4 P0 and '
            'in Gate 5 when sponsored/affiliate/topic_class are set.'),
    ]
