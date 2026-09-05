# Phase 0 - Test harness and Vietnamese fixtures

**Priority:** must run first · **Repo:** `claude-blog` · **Estimate:** 0.5 day
**Blocks:** every other phase

## Goal

Land a Vietnamese test corpus and a set of tests that **fail today**, each one pinned to a
specific defect. No production code changes in this phase. When Phase 0 is complete the
suite must be red in a controlled, documented way - that red is the specification for
Phases 1-5.

## Why this comes first

Three of the defects in this plan are silent: wrong output that looks plausible. A wrong
readability score does not raise. A mangled slug is still a valid slug. A missing E-E-A-T
marker just lowers a number. Without a failing test to anchor each one, "fixed" is an
opinion. Additionally, two of the bugs found while writing this plan were found *only*
by executing the code rather than reading it.

## Prerequisites

`pytest` is not installed system-wide and `pip3` is absent from `PATH`. Create a venv once:

```bash
cd /home/bachx/workspace/Hien/ai
python3 -m venv .venv
.venv/bin/pip install -q pytest requests pillow pyyaml
echo ".venv/" >> .git/info/exclude 2>/dev/null || true
```

Run the suite:

```bash
cd claude-blog && ../.venv/bin/python -m pytest tests/ -q
```

Record the baseline before touching anything. Expected at `main` = `84f7abf`:

```
341 passed, 1 failed, 1 skipped, 5 errors
```

Both the failure and the errors are pre-existing and unrelated - see `README.md` § Baseline.
**If your baseline differs from this, stop and investigate before proceeding.**

## Deliverables

### 0.1 - `tests/fixtures/blog_vi_good.md`

A realistic, genuinely good Vietnamese blog post that *should* score ≥ 90 once Phases 1-2
land. This fixture is the single most important artifact in the plan: it is what proves the
gate becomes reachable.

Requirements - it must contain, in natural Vietnamese:

- YAML frontmatter with `lang: vi`, a title using diacritics **and at least one `đ`**,
  `description`, `author`, `datePublished`, `dateModified`, `tags`
- A `## Tóm tắt` (TL;DR) section near the top
- At least one first-person evidence claim: e.g. *"Chúng tôi đã thử nghiệm trên 40 website
  trong 3 tháng"*
- An explicit methodology sentence containing a number: e.g. *"Cỡ mẫu: 40 website, đo từ
  01/2026 đến 03/2026"*
- A bold entity definition in Vietnamese form: `**Core Web Vitals** là …`
- Links to `/gioi-thieu` (about) and `/lien-he` (contact)
- An editorial signal: *"Bài viết đã được kiểm chứng bởi …"*
- 3+ inline citations to real authoritative sources
- At least one table and one list
- 1,200+ words so word-count thresholds are not the limiting factor
- `coverImage`, `coverImageAlt` and `ogImage` in frontmatter. Without them
  `technical_elements.social_meta` and `images` score near zero, which has nothing to do
  with language and would otherwise be mistaken for a Vietnamese defect.
- An `[ORIGINAL DATA]` marker and a `[PERSONAL EXPERIENCE]` marker. These are literal,
  language-independent tags that `analyze_blog.py` reads as author-declared evidence.
  Without them `content_quality.originality` is capped at 1 out of 5 no matter how good the
  Vietnamese is. Only add them where they are factually true of the fixture.

Write it as a real article on a real topic (suggested: *"Cách tối ưu Core Web Vitals cho
website tiếng Việt"*). Do not write filler - the fixture must be defensible as a genuinely
good post, otherwise a low score is ambiguous.

### 0.2 - `tests/fixtures/blog_vi_bad.md`

The mirror image: Vietnamese prose exhibiting the failure patterns Phase 3 must catch.

- AI-writing tells in Vietnamese: *"Trong thế giới ngày nay"*, *"Không thể phủ nhận rằng"*,
  *"Điều quan trọng cần lưu ý là"*, *"Hãy cùng đi sâu vào"*, *"Tóm lại, có thể thấy rằng"*
- Register drift: mixes `bạn` / `quý khách` / `các bạn` / `anh chị` in the same document
- No citations, no methodology, no TL;DR, no about/contact
- At least one NFD-encoded (decomposed) heading - see 0.4
- Short, ~400 words

### 0.3 - `tests/test_vietnamese_slug.py`

Tests that **must fail now**. Import the real functions; do not re-implement them.

```python
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import blog_render
import blog_hygiene

# (input, expected) — expected is the correct Vietnamese transliteration
VI_SLUG_CASES = [
    ("Hướng dẫn đặt hàng online",     "huong-dan-dat-hang-online"),
    ("Đánh giá sản phẩm 2026",        "danh-gia-san-pham-2026"),
    ("Cách viết nội dung chuẩn SEO",  "cach-viet-noi-dung-chuan-seo"),
    ("Bí quyết để thành công",        "bi-quyet-de-thanh-cong"),
    ("Top 10 quán cà phê Hà Nội",     "top-10-quan-ca-phe-ha-noi"),
    ("Dịch vụ đăng ký kinh doanh",    "dich-vu-dang-ky-kinh-doanh"),
]


@pytest.mark.parametrize("title,expected", VI_SLUG_CASES)
def test_render_slugify_preserves_vietnamese(title, expected):
    """blog_render._slugify must transliterate, not delete, Vietnamese characters."""
    assert blog_render._slugify(title) == expected


@pytest.mark.parametrize("heading,expected", VI_SLUG_CASES)
def test_hygiene_slugify_preserves_d_stroke(heading, expected):
    """blog_hygiene.slugify must map đ/Đ to d; NFKD alone deletes it."""
    assert blog_hygiene.slugify(heading) == expected


def test_both_slugifiers_agree():
    """Anchors and filenames must not disagree."""
    for title, _ in VI_SLUG_CASES:
        assert blog_render._slugify(title) == blog_hygiene.slugify(title)


def test_slug_is_stable_across_nfc_and_nfd():
    """Same visible text in NFC and NFD must produce the same slug."""
    import unicodedata
    title = "Hướng dẫn đặt hàng"
    nfc, nfd = unicodedata.normalize("NFC", title), unicodedata.normalize("NFD", title)
    assert nfc != nfd                                   # sanity: they really differ in bytes
    assert blog_render._slugify(nfc) == blog_render._slugify(nfd)


def test_english_slugs_unchanged():
    """Regression guard: English behavior must not shift."""
    assert blog_render._slugify("How to Optimize Your Blog") == "how-to-optimize-your-blog"
    assert blog_hygiene.slugify("What Are AI Citations?") == "what-are-ai-citations"
```

Expected result now: the first three test groups fail, the English guard passes.

### 0.4 - `tests/test_vietnamese_analysis.py`

Tests pinned to each profile-driven signal from `00-OVERVIEW.md` § 2.3.

```python
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
    ("about_patterns",        "Xem thêm tại [Về chúng tôi](/gioi-thieu)"),
    ("contact_patterns",      "[Liên hệ](/lien-he) với chúng tôi"),
    ("first_person_patterns", "Chúng tôi đã thử nghiệm trên 40 website"),
    ("methodology_patterns",  "Phương pháp: cỡ mẫu 40 website, đo trong 3 tháng"),
])
def test_vi_profile_patterns_match_real_vietnamese(key, sample):
    import re
    profile = analyze_blog.LANGUAGE_PROFILES["vi"]
    assert any(re.search(p, sample, re.IGNORECASE) for p in profile[key]), \
        f"no pattern in {key} matched: {sample!r}"


def test_vietnamese_entity_definition_detected():
    """analyze_blog.py:1291 is hardcoded English; a vi profile alone will not fix it."""
    content = "**Core Web Vitals** là bộ chỉ số đo trải nghiệm người dùng."
    result = analyze_blog.analyze_ai_citation_readiness(content, language="vi")
    assert result["entity_definitions"] >= 1


def test_vietnamese_tldr_detected(vi_good):
    result = analyze_blog.analyze_ai_citation_readiness(vi_good, language="vi")
    assert result["has_tldr"] is True


def test_good_vietnamese_post_can_reach_gate_threshold(vi_good):
    """The headline test: Gate 4 requires >= 90. Today this is unreachable for vi."""
    report = analyze_blog.analyze(vi_good)          # confirm the real entry point name first
    assert report["total_score"] >= 90, (
        f"scored {report['total_score']}; breakdown: {report.get('breakdown')}"
    )
```

> **Implementer note.** `analyze_blog.py` is ~2,000 lines. The exact public function names
> (`analyze`, `analyze_ai_citation_readiness`, `total_score`, `breakdown`) must be confirmed
> against the file before writing these tests - adjust the calls, never the assertions.
> Read `tests/test_analyze_blog.py` and `tests/test_ai_citation_score.py` first and follow
> their conventions.

### 0.5 - `tests/test_vietnamese_text.py`

Placeholder tests for the `scripts/vi_text.py` module Phase 1 creates. These fail with
`ModuleNotFoundError` until Phase 1 lands - that is intended and correct.

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


def test_module_exists():
    import vi_text                                   # noqa: F401


def test_nfc_normalization():
    import unicodedata, vi_text
    nfd = unicodedata.normalize("NFD", "Hướng dẫn")
    assert vi_text.normalize(nfd) == unicodedata.normalize("NFC", "Hướng dẫn")


def test_d_stroke_maps_to_d():
    import vi_text
    assert vi_text.to_ascii("đặt") == "dat"
    assert vi_text.to_ascii("Đảng") == "Dang"


def test_syllable_count_is_whitespace_based():
    """Vietnamese is monosyllabic: syllables == whitespace-separated tokens."""
    import vi_text
    assert vi_text.count_syllables("Cách viết nội dung chuẩn SEO") == 6
```

### 0.6 - `docs/` note in the repo

Add `claude-blog/docs/VIETNAMESE-SUPPORT.md` - a short pointer explaining that Vietnamese
support is tracked in this plan, listing the phases and their status. One screen, no more.

## Pitfalls

1. **Do not fix anything in this phase.** The temptation to fix a one-line slug bug while
   writing its test is strong. Resist it: a test that has never been seen to fail proves
   nothing about the fix.
2. **Do not write the fixture by translating an English one.** A translated post carries
   English sentence rhythm and heading conventions, which is exactly the failure mode
   Phase 3 exists to catch. If the fixture is a translation, `blog_vi_good.md` will not be
   a fair test of anything.
3. **Confirm function names before writing assertions.** `analyze_blog.py` is roughly 2,000
   lines. Adjust the calls in the test skeletons to the real API; never adjust the
   assertions to whatever the current code happens to return.
4. **Do not commit the venv.** Add `.venv/` to `.git/info/exclude` rather than to
   `.gitignore` - the ignore file is part of the upstream repository.
5. **Record the exact failing-test list.** Phases 1 to 3 are measured by which of these
   turn green. A vague "several tests fail" makes that impossible to check later.

## Acceptance criteria

- [ ] Baseline recorded and matches `341 passed, 1 failed, 1 skipped, 5 errors`
- [ ] `blog_vi_good.md` exists, is ≥ 1,200 words, is genuinely good Vietnamese prose, and
      contains every element in 0.1
- [ ] `blog_vi_bad.md` exists and contains at least 5 distinct AI-tell phrases
- [ ] `tests/test_vietnamese_slug.py` - 4 tests fail, English guard passes
- [ ] `tests/test_vietnamese_analysis.py` - most tests fail; `test_unknown_language_still_falls_back_to_en` passes
- [ ] `tests/test_vietnamese_text.py` - all fail with `ModuleNotFoundError`
- [ ] **No production file modified.** `git diff --stat scripts/ skills/` is empty.
- [ ] The 341 pre-existing passes are still passing

## Verification

```bash
cd claude-blog
../.venv/bin/python -m pytest tests/ -q                       # existing suite unchanged
../.venv/bin/python -m pytest tests/test_vietnamese_*.py -v   # new tests, expected red
git diff --stat scripts/ skills/                              # must be empty
```

Record the exact failing-test list in the commit message. Phases 1-3 will turn them green
one group at a time, and that list is how progress is measured.

## Commit

```
test(vi): add Vietnamese fixtures and failing specification tests

Adds a Vietnamese test corpus and tests pinned to each known
Vietnamese-language defect. All new tests fail by design; they are the
specification for the language-support work that follows.

- tests/fixtures/blog_vi_good.md: 1,200-word reference post, lang: vi
- tests/fixtures/blog_vi_bad.md: AI-tell and register-drift corpus
- tests/test_vietnamese_slug.py: slug transliteration (P0)
- tests/test_vietnamese_analysis.py: LANGUAGE_PROFILES coverage (P0)
- tests/test_vietnamese_text.py: scripts/vi_text.py contract

No production code is modified in this commit.
```
