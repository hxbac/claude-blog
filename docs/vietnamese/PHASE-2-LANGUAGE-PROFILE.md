# Phase 2 - Vietnamese language profile

**Priority:** P0 · **Repo:** `claude-blog` · **Estimate:** 1 day
**Depends on:** Phase 0 (Phase 1 optional but recommended first - same module)

## Goal

A well-written Vietnamese post scores what it deserves, so Gate 4's 90-point threshold
becomes reachable, and the iteration loop stops sending `blog-writer` to fix categories
that are not broken.

## The defect

See `00-OVERVIEW.md` § 2.2 and § 2.3 for the full chain. In one line: `_detect_language()`
returns `'en'` for Vietnamese input - with no warning - and six scoring signals then search
Vietnamese prose for English strings.

Two of the six signals are not even in the profile; they are hardcoded English at
`analyze_blog.py:1291` and `:1751`. **Adding a `'vi'` key alone does not fix those.** This
phase therefore also promotes them into the profile, adding the same keys to `'en'` and
`'tr'` so behavior for those languages is byte-identical.

## Implementation

### 2.1 - Add `lang` to the frontmatter template

`skills/blog-write/SKILL.md:224-234` - the template the writer follows has no `lang:` field,
so `_detect_language` never sees a declaration.

```yaml
---
title: "..."
description: "..."
lang: "vi"          # ISO 639-1. Required. Drives language-aware quality scoring.
coverImage: "..."
coverImageAlt: "..."
ogImage: "..."
date: "..."
lastUpdated: "..."
author: "..."
tags: [...]
---
```

Add the same field to `blog-rewrite`, `blog-translate`, `blog-localize` and
`blog-multilingual` templates if they carry their own copies - grep for `coverImageAlt:` to
find them all.

### 2.2 - Create `scripts/vi_profile.py`

Standard library only. Verified: **31/31 positive cases match, 0 false positives**.

> **The `\b` trap.** Python's `\b` is defined over `[A-Za-z0-9_]`, so it does **not** fire
> between a space and `ư`, or between `đ` and a space. Vietnamese patterns must use explicit
> `\s+` or lookarounds, never `\b` around accented words. Every pattern below follows this.
> A `\b`-based Vietnamese regex silently matches nothing.

```python
#!/usr/bin/env python3
"""Vietnamese LANGUAGE_PROFILES payload for analyze_blog.py. Stdlib only.

Kept out of analyze_blog.py so the Vietnamese rules can be reviewed, tested and
ported independently of the analyzer.
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
    # match (tôi/mình/chúng tôi all appear in ordinary prose), so match the
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

    # --- NEW KEYS: these do not exist in 'en'/'tr' yet. Add them there too. ---
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
```

### 2.3 - Wire it into `analyze_blog.py`

**a) Register the profile** - after the `LANGUAGE_PROFILES` literal at line ~204:

```python
from vi_profile import VI_PROFILE

LANGUAGE_PROFILES['vi'] = VI_PROFILE
```

Prefer this over pasting the dict inline: it keeps `analyze_blog.py` readable and lets the
Vietnamese rules be tested, reviewed and ported on their own.

**b) Backfill the two new keys into `en` and `tr`** so no profile has a missing key. Use the
*exact current hardcoded regexes* so behavior does not shift:

```python
LANGUAGE_PROFILES['en']['entity_definition_patterns'] = (
    r'\*\*[^*]+\*\*\s*(?:is|are|refers to|means)',
)
LANGUAGE_PROFILES['en']['editorial_patterns'] = (
    r'(?i)\b(?:editorial|reviewed by|fact.?check|editor)\b',
)
LANGUAGE_PROFILES['tr']['entity_definition_patterns'] = (
    r'\*\*[^*]+\*\*\s*(?:bir|olarak|demektir|anlamına gelir)',
)
LANGUAGE_PROFILES['tr']['editorial_patterns'] = (
    r'(?i)(?:editör|yayın kurulu|doğrulama|teyit)',
)
```

> The `tr` values are new content, not a refactor - Turkish previously fell through to the
> English hardcoded regexes and scored 0 on both signals. Flag this in the PR description as
> a Turkish behavior change, and get it reviewed by someone who reads Turkish, or ship
> `tr` with the English patterns unchanged and open a separate issue. **Do not silently
> guess at Turkish.**

**c) Add Vietnamese detection** - `_detect_language()` at line 528:

```python
def _detect_language(frontmatter: dict[str, Any], body: str) -> str:
    """Resolve a supported language profile without broad language guessing."""
    declared = str(
        frontmatter.get('lang') or frontmatter.get('language')
        or frontmatter.get('inLanguage') or ''
    ).strip().lower()
    if declared:
        primary = re.split(r'[-_]', declared, maxsplit=1)[0]
        if primary in LANGUAGE_PROFILES:
            return primary
        # Declared but unsupported: fall through to heuristics rather than
        # silently assuming English. The old code returned 'en' here.
    if vi_text.is_vietnamese(body):
        return 'vi'
    strong_turkish_markers = len(re.findall(r'[ığşİĞŞ]', body))
    letters = len(re.findall(r'[^\W\d_]', body, re.UNICODE))
    if strong_turkish_markers >= 2 and strong_turkish_markers / max(letters, 1) >= 0.002:
        return 'tr'
    return 'en'
```

Note the deliberate change: an *unsupported* declaration (`lang: de`) now falls through to
heuristics instead of hard-returning `'en'`. For German the heuristics still land on `'en'`,
so `test_unknown_language_still_falls_back_to_en` keeps passing - but a post declared
`lang: vi-VN` now resolves correctly through the `re.split` on `-`.

Order matters: check Vietnamese **before** Turkish. Vietnamese `ữ` and Turkish `ş` do not
overlap, but running the cheap explicit test first is clearer.

**d) Route the two de-hardcoded signals through the profile**

`analyze_blog.py:1291`:

```python
# before
entity_definitions = len(re.findall(r'\*\*[^*]+\*\*\s*(?:is|are|refers to|means)', content))
# after
profile = LANGUAGE_PROFILES.get(language, LANGUAGE_PROFILES['en'])
entity_definitions = sum(
    len(re.findall(p, content, re.IGNORECASE))
    for p in profile['entity_definition_patterns']
)
```

`analyze_blog.py:1751`:

```python
# before
if re.search(r'(?i)\b(?:editorial|reviewed by|fact.?check|editor)\b', body):
    trust_score += 1
# after
if any(re.search(p, body, re.IGNORECASE) for p in profile['editorial_patterns']):
    trust_score += 1
```

`profile` is already bound at line 1744 in that function - reuse it, do not re-fetch.

### 2.4 - Vietnamese readability model

`analyze_blog.py:864` currently branches only on `'atesman'`, so any other model falls
through to Flesch. Add a `vi_syllable` branch.

**Why not port Flesch.** Vietnamese orthography writes one syllable per whitespace token,
so syllables-per-word is ≈ 1.0 for every text, and the syllable term in Flesch becomes a
constant. Every Vietnamese document then scores as "very easy" regardless of how it reads.
Published Vietnamese readability work exists - Nguyen & Henkin, *A Readability Formula for
Vietnamese*, Journal of Reading 26(3), 1982, and a second-generation formula in 1985; more
recently Luong, Nguyen & Dinh, *A New Formula for Vietnamese Text Readability Assessment*,
KSE 2018 - but **none of these publish coefficients openly**, so this implementation does
not claim to be any of them.

What it is instead: a transparent, documented heuristic over sentence length, reported
alongside the raw inputs so a human can judge it. Do not label it as a validated formula
anywhere in output or documentation.

```python
if profile["readability_model"] == 'vi_syllable':
    # Vietnamese is monosyllabic: one syllable per whitespace token, so
    # "syllables per word" carries no signal and Flesch is meaningless here.
    # Sentence length and the tail of very long sentences do carry signal.
    # This is a documented heuristic, not a published formula.
    # Split on terminal punctuation OR a line break. Markdown headings, list
    # items and table rows carry no full stop, so a punctuation-only split
    # merges each one into the following sentence and inflates the average.
    # Measured on the Vietnamese fixture: 27.1 syllables/sentence without the
    # newline term, 22.8 with it.
    sentences_text = [s for s in re.split(r'[.!?…]+|\n+', text)
                      if vi_text.count_syllables(s) >= 2]
    lengths = [vi_text.count_syllables(s) for s in sentences_text] or [0]
    avg_syllables = sum(lengths) / len(lengths)
    long_ratio = sum(1 for n in lengths if n > 30) / max(len(lengths), 1)
    score = 100.0 - 3.0 * max(0.0, avg_syllables - 10) - 15.0 * long_ratio
    score = max(0.0, min(100.0, score))
    return {
        'reading_model': 'vi_syllable',
        'reading_ease': round(score, 1),
        'vi_reading_ease': round(score, 1),
        'reading_time_minutes': round(word_count / 200, 1),   # ~200 syl/min for vi
        'avg_sentence_length': round(avg_syllables, 1),
        'long_sentence_ratio': round(long_ratio, 3),
        'sentence_count': len(lengths),
    }
```

**Scoring bands.** The if/elif chain at line 1472 gives `atesman` its own bands and lets
everything else fall into Flesch's. Add a `vi_syllable` branch **before** the Flesch cases:

```python
elif reading_model == 'vi_syllable' and reading_ease >= 70:
    read_score = 7
elif reading_model == 'vi_syllable' and reading_ease >= 55:
    read_score = 5
elif reading_model == 'vi_syllable' and reading_ease >= 40:
    read_score = 3
elif reading_model == 'vi_syllable':
    read_score = 1
    issues.append({'category': 'content', 'severity': 'medium',
                   'issue': f'Câu quá dài (trung bình {readability.get("avg_sentence_length")} '
                            f'âm tiết/câu). Chia nhỏ các câu trên 30 âm tiết.'})
```

The bands are monotone - easier is better - unlike the English band, which penalizes
scores above 70 because Flesch >70 means grade-school English. Vietnamese has no equivalent
mapping, so importing that penalty would be a false transfer.

Also fix the hardcoded message at line 1487, which says "Flesch reading ease" regardless of
model:

```python
'issue': f'{reading_model} reading ease ({reading_ease}) outside acceptable range'
```

### Calibration

Measured against real Vietnamese prose:

Measured through the real `_plain_text_for_analysis` pipeline, with the newline-aware
splitter and the constants above:

| Sample | Sentences | Avg syllables/sentence | >30 syll | Score | Points |
|---|---:|---:|---:|---:|---:|
| `tests/fixtures/blog_vi_good.md` | 57 | 22.8 | 35.1% | 56.3 | 5/7 |
| `tests/fixtures/blog_vi_bad.md` | 24 | 15.2 | 8.3% | 83.1 | 7/7 |
| Technical documentation (long-form) | 340 | 10.5 | 2.6% | 98.2 | 7/7 |
| Ordinary blog prose | 4 | 11.5 | 0% | 95.5 | 7/7 |
| Vietnamese news copy | 3 | 16.7 | 0% | 80.0 | 7/7 |
| Academic run-on sentences | 1 | 79.0 | 100% | 0.0 | 1/7 |

The model discriminates where it should - convoluted academic prose is caught, ordinary
good writing is not penalized - and it does not saturate at the top for a single style.

Two calibration notes worth keeping:

- **The good fixture scores 5/7, not 7/7.** That is correct. It averages 22.8 syllables per
  sentence with 35% of sentences over 30, which is dense even for Vietnamese technical
  writing. The model is telling the truth about it.
- **The bad fixture scores 7/7 on readability.** Also correct, and a useful separation of
  concerns: `blog_vi_bad.md` is formulaic, not unreadable. Formulaic prose is what
  `scripts/vi_prose.py` catches in Phase 3. Readability and authenticity are different
  measurements and must not be collapsed into one number.

An earlier draft of this document used `3.5` and `25.0` with a punctuation-only splitter.
Measured against the real fixture that scored 28.8 and awarded 1/7 to a competently written
post, which was too harsh and would have pushed a Phase 2 implementer to weaken the profile
chasing points. The constants above were re-derived from measurement.

## Pitfalls

1. **`\b` does not work on Vietnamese.** Repeated because it is the single most likely way
   to ship a Vietnamese regex that silently matches nothing. Test every pattern against a
   real sample string.
2. **Normalize before matching.** Text arriving in NFD will not match NFC patterns. Call
   `vi_text.normalize()` on `body` before the profile is applied, or normalize at read time.
   Pick one place and document it.
3. **Do not match bare pronouns.** `tôi`, `mình`, `bạn` are ordinary Vietnamese words.
   Matching `tôi` alone as first-person evidence gives every post a free E-E-A-T point.
   Always pair pronoun with evidence verb.
4. **`re.IGNORECASE` on Vietnamese** works correctly with precomposed characters but is a
   no-op on combining marks. Another reason to normalize to NFC first.
5. **Do not touch the `en` bands.** The English chain is load-bearing for 341 passing tests.
   Insert the `vi_syllable` branches *before* the bare `60 <= reading_ease <= 70` case, never
   by modifying it.
6. **Keep `analyze_blog.py` stdlib-only.** `vi_profile` and `vi_text` are local sibling
   modules, not packages. Follow the existing sibling-import pattern in `scripts/`.

## Acceptance criteria

- [ ] `scripts/vi_profile.py` exists, stdlib-only, no control characters
      (`python3 -c "print([c for c in open('scripts/vi_profile.py','rb').read() if c<9 or 13<c<32])"` → `[]`)
- [ ] `'vi'` present in `LANGUAGE_PROFILES` with all 8 keys
- [ ] `'en'` and `'tr'` also carry `entity_definition_patterns` and `editorial_patterns`
- [ ] `lang: "vi"` present in the `blog-write` frontmatter template
- [ ] `tests/test_vietnamese_analysis.py` - all tests pass, including every
      `test_language_gated_signal_scores` case and
      `test_good_vietnamese_post_clears_markdown_only_floor`
- [ ] English and Turkish scores for the existing fixtures are **byte-identical** to the
      pre-change values - capture them first (see Verification)
- [ ] Full suite still `341 passed` plus new tests
- [ ] `grep -n "is\\\\|are\\\\|refers to" scripts/analyze_blog.py` shows no hardcoded
      English entity regex remaining

## Verification

Capture English/Turkish baselines **before** editing:

```bash
cd claude-blog
for f in tests/fixtures/blog_pass.md tests/fixtures/blog_fail.md; do
  ../.venv/bin/python scripts/analyze_blog.py "$f" --json > "/tmp/before-$(basename $f).json"
done
```

After the change, they must be identical:

```bash
for f in tests/fixtures/blog_pass.md tests/fixtures/blog_fail.md; do
  ../.venv/bin/python scripts/analyze_blog.py "$f" --json > "/tmp/after-$(basename $f).json"
  diff "/tmp/before-$(basename $f).json" "/tmp/after-$(basename $f).json" && echo "$f unchanged"
done

../.venv/bin/python -m pytest tests/ -q
../.venv/bin/python scripts/analyze_blog.py tests/fixtures/blog_vi_good.md --json | \
  python3 -c "import json,sys; d=json.load(sys.stdin); print(d['total_score'], d.get('readability',{}).get('reading_model'))"
```

Expected: `vi_syllable`, and a total of **75** on `blog_vi_good.md` (60 before this phase).

**The total is not 90 and must not be pushed to 90 here.** Measured breakdown after this
phase:

| Category | Score | Note |
|---|---|---|
| content_quality | 23/30 | readability 5, originality 5 |
| seo_optimization | 20/25 | unaffected by language |
| eeat_signals | 13/15 | trust 4, experience 3 |
| technical_elements | **7/15** | schema 0, images 1, page speed 1 |
| ai_citation_readiness | 12/15 | entity_clarity 2, extraction 2 |

The 8 missing points in `technical_elements` need JSON-LD schema, a real hero image file and
measured page speed. `/blog write` produces all three during rendering; a bare `.md` fixture
cannot carry them. Gate 4's 90-point threshold is verified end to end in Phase 6, against a
real delivered post. If you find yourself editing the fixture or the profile to reach 90
here, stop: you are measuring the delivery pipeline, not language support.

> Confirm the `--json` flag and the JSON key names against the actual CLI before relying on
> these commands. Adjust the commands, never the criteria.

## Commit

```
feat(vi): add Vietnamese language profile to blog quality scoring

analyze_blog.py gates six scoring signals behind LANGUAGE_PROFILES,
which contained only 'en' and 'tr'. Vietnamese posts resolved to 'en'
with no warning, so readability was inflated (Flesch is meaningless for
a monosyllabic language) while E-E-A-T trust, experience, methodology
and AI-citation readiness were deflated -- roughly 30 of 100 points lost
to language mismatch, putting the delivery contract's 90-point gate out
of reach and sending the iteration loop to fix a category that was not
broken.

- scripts/vi_profile.py: Vietnamese patterns for all six signals
- LANGUAGE_PROFILES['vi'] registered; detection added to _detect_language
- entity_definition_patterns and editorial_patterns promoted out of
  hardcoded English into the profile, with 'en' keeping its exact
  previous regexes
- vi_syllable readability model: a documented sentence-length heuristic,
  not a published formula. Flesch cannot be ported because Vietnamese
  writes one syllable per whitespace token.
- lang: field added to the blog-write frontmatter template
- an unsupported declared lang now falls through to heuristics instead
  of hard-returning 'en'

English and Turkish output is unchanged; fixture scores verified
identical before and after.
```
