# Phase 1 - Vietnamese-safe slugs

**Priority:** P0 · **Repo:** `claude-blog` · **Estimate:** 0.5 day
**Depends on:** Phase 0 · **Blocks:** nothing

## Goal

Every Vietnamese title produces a correct, readable, ASCII URL slug - and heading anchors
agree with file names.

## The defect

Two slug functions exist, both wrong for Vietnamese, and wrong in *different* ways, so they
also disagree with each other.

### `scripts/blog_render.py:161` - used at line 566 to name the published file

```python
def _slugify(text: str) -> str:
    s = text.lower().strip()
    s = re.sub(r"[^a-z0-9\s\-]", "", s)     # deletes every accented character
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-") or "post"
```

No normalization at all. Verified output:

| Title | Produced | Correct |
|---|---|---|
| `Hướng dẫn đặt hàng online` | `hng-dn-t-hng-online` | `huong-dan-dat-hang-online` |
| `Đánh giá sản phẩm 2026` | `nh-gi-sn-phm-2026` | `danh-gia-san-pham-2026` |
| `Top 10 quán cà phê Hà Nội` | `top-10-qun-c-ph-h-ni` | `top-10-quan-ca-phe-ha-noi` |

### `scripts/blog_hygiene.py:39` - used at line 107 for heading anchors

```python
text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
```

Better, but `đ` (U+0111) and `Đ` (U+0110) have **no canonical decomposition** - the stroke is
part of the glyph, not a combining mark - so they are deleted:

| Heading | Produced | Correct |
|---|---|---|
| `Hướng dẫn đặt hàng online` | `huong-dan-at-hang-online` | `huong-dan-dat-hang-online` |
| `Bí quyết để thành công` | `bi-quyet-e-thanh-cong` | `bi-quyet-de-thanh-cong` |

`đ` is one of the most common letters in Vietnamese (`đã`, `được`, `đến`, `đó`, `để`,
`đặt`, `đánh`…). This is not an edge case.

### Why it matters more than the scoring bug

A scoring bug blocks publication - annoying, recoverable. A slug bug **ships**. The URL is
the one artifact you cannot revise later without a redirect, and it is what users and
search engines see. Fix it before the first Vietnamese post goes live.

## Implementation

### 1.1 - Create `scripts/vi_text.py`

Standard library only. This module is the single home for every Vietnamese text primitive;
Phases 2 and 3 import from it. The code below is **tested and verified** - 6/6 slug cases,
NFC/NFD stability, English unchanged, Turkish improved.

```python
#!/usr/bin/env python3
"""Vietnamese text primitives. Standard library only.

Every Vietnamese-specific text operation in this repository routes through this
module. Keeping the logic here (rather than inline in analyzers) means it ports
to other harnesses unchanged and can be tested in isolation.
"""

from __future__ import annotations

import re
import unicodedata

__all__ = ["normalize", "to_ascii", "slugify", "count_syllables", "is_vietnamese"]

# Characters NFD/NFKD cannot decompose: the mark is part of the glyph, not a
# combining character. Without this map, unicodedata + ASCII-encode deletes them.
_UNDECOMPOSABLE = {
    "Đ": "D",   # Vietnamese D with stroke
    "đ": "d",
    "Ð": "D",   # U+00D0 ETH, visually identical, occasionally pasted in
    "ð": "d",
    "ı": "i",   # Turkish dotless i (U+0131), also undecomposable
    "İ": "I",
    "ø": "o",
    "Ø": "O",
    "ß": "ss",
    "æ": "ae",
    "Æ": "AE",
    "œ": "oe",
    "Œ": "OE",
}

# Precomposed Vietnamese letters, for the detection heuristic. Tone marks stacked
# on horn/breve vowels are the strongest single signal that Latin text is
# Vietnamese rather than any other language.
_VI_MARKERS = (
    "ăâêôơưđ"
    "áàảãạ" "ắằẳẵặ" "ấầẩẫậ"
    "éèẻẽẹ" "ếềểễệ"
    "íìỉĩị"
    "óòỏõọ" "ốồổỗộ" "ớờởỡợ"
    "úùủũụ" "ứừửữự"
    "ýỳỷỹỵ"
)
_VI_MARKER_RE = re.compile(f"[{_VI_MARKERS}]", re.IGNORECASE)

# Frequent Vietnamese function words. Used only to break ties on short input
# where the diacritic ratio is statistically unreliable.
_VI_STOPWORDS = frozenset(
    "và của là có cho các một những được với trong khi này đó người "
    "không như để từ về theo tại cũng đã sẽ nhưng nếu thì mà bạn".split()
)


def normalize(text: str) -> str:
    """Return NFC-normalized text.

    Vietnamese arrives in both NFC (Windows, most CMSes) and NFD (macOS
    filesystems, some editors). The two are visually identical and compare
    unequal. Normalize at every boundary.
    """
    return unicodedata.normalize("NFC", text)


def to_ascii(text: str) -> str:
    """Strip Vietnamese diacritics, preserving đ/Đ as d/D.

    ``unicodedata.normalize("NFD", ...).encode("ascii", "ignore")`` alone deletes
    đ (U+0111) and Đ (U+0110) because neither has a canonical decomposition.
    """
    for src, dst in _UNDECOMPOSABLE.items():
        text = text.replace(src, dst)
    decomposed = unicodedata.normalize("NFD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return unicodedata.normalize("NFC", stripped)


def slugify(text: str, *, fallback: str = "post") -> str:
    """Return a lowercase, hyphen-separated, ASCII-only URL slug.

    Handles Vietnamese, English and Turkish input identically: transliterate,
    then reduce to ``[a-z0-9-]``.
    """
    ascii_text = to_ascii(normalize(text)).lower()
    ascii_text = ascii_text.encode("ascii", "ignore").decode("ascii")
    ascii_text = re.sub(r"[^a-z0-9\s\-]", "", ascii_text)
    ascii_text = re.sub(r"[\s_]+", "-", ascii_text)
    ascii_text = re.sub(r"-+", "-", ascii_text).strip("-")
    return ascii_text or fallback


def count_syllables(text: str) -> int:
    """Count Vietnamese syllables.

    Vietnamese orthography writes one syllable per whitespace-separated token, so
    syllable counting is tokenization. This is why English syllable-based
    readability formulas produce meaningless results on Vietnamese: they estimate
    syllables from vowel clusters and always land near 1.0.
    """
    return len(re.findall(r"[^\W\d_]+", normalize(text), re.UNICODE))


def is_vietnamese(text: str, *, min_ratio: float = 0.015, min_markers: int = 3) -> bool:
    """Heuristic Vietnamese detection.

    Mirrors the shape of the existing Turkish heuristic in ``analyze_blog.py``:
    count language-specific characters, require both an absolute floor and a
    ratio against total letters. Falls back to a stopword check for short input
    where the ratio is unstable.
    """
    text = normalize(text)
    markers = len(_VI_MARKER_RE.findall(text))
    letters = len(re.findall(r"[^\W\d_]", text, re.UNICODE))
    if letters == 0:
        return False
    if markers >= min_markers and markers / letters >= min_ratio:
        return True
    tokens = re.findall(r"[^\W\d_]+", text.lower(), re.UNICODE)
    if len(tokens) >= 8:
        hits = sum(1 for t in tokens if t in _VI_STOPWORDS)
        return hits / len(tokens) >= 0.08
    return False
```

### 1.2 - Rewire `blog_render.py`

```python
# near the other imports
from vi_text import slugify as _vi_slugify


def _slugify(text: str) -> str:
    return _vi_slugify(text, fallback="post")
```

Keep the function name and signature. Callers at line 566 and elsewhere must not change.
`scripts/` is already on `sys.path` for sibling imports - confirm the pattern used by the
other scripts in the directory and follow it exactly rather than inventing a new one.

### 1.3 - Rewire `blog_hygiene.py`

```python
from vi_text import slugify as _vi_slugify


def slugify(text: str) -> str:
    """Convert heading text to a GitHub-style anchor slug (ASCII, lowercase)."""
    return _vi_slugify(text, fallback="")
```

Note the **different fallback**: the current `blog_hygiene.slugify` returns `""` for
unsluggable input (it ends in `.strip("-")`), while `blog_render._slugify` returns
`"post"`. Preserve both behaviors exactly - a shared fallback would be a silent regression
in one of them.

## Verified behavior

Run against the real module:

| Input | Output |
|---|---|
| `Hướng dẫn đặt hàng online` | `huong-dan-dat-hang-online` |
| `Đánh giá sản phẩm 2026` | `danh-gia-san-pham-2026` |
| `Cách viết nội dung chuẩn SEO` | `cach-viet-noi-dung-chuan-seo` |
| `Bí quyết để thành công` | `bi-quyet-de-thanh-cong` |
| `Top 10 quán cà phê Hà Nội` | `top-10-quan-ca-phe-ha-noi` |
| `Dịch vụ đăng ký kinh doanh` | `dich-vu-dang-ky-kinh-doanh` |
| `How to Optimize Your Blog` | `how-to-optimize-your-blog` (unchanged) |
| `What Are AI Citations?` | `what-are-ai-citations` (unchanged) |
| `Türkçe içerik nasıl yazılır` | `turkce-icerik-nasil-yazilir` (**improved** - `ı` was being dropped) |
| `İstanbul'da SEO` | `istanbulda-seo` (**improved**) |
| `""` / `"---"` / `"!!!"` | `post` (render) / `""` (hygiene) |
| `"2026"` | `2026` |

NFC and NFD forms of the same title produce identical slugs.

## Pitfalls

1. **Do not use `NFKD`.** `NFKD` is *compatibility* decomposition: it rewrites `①`→`1`,
   `ﬁ`→`fi`, full-width forms, and superscripts. `NFD` is the canonical form and is what you
   want. The existing `blog_hygiene` code uses `NFKD`, which is a second, separate bug.
2. **Order matters in `to_ascii`.** The `_UNDECOMPOSABLE` replacement must run *before*
   `normalize("NFD", ...)`, not after - after decomposition the `đ` is still `đ` but you are
   iterating a different string and the mapping silently no-ops on some inputs.
3. **Do not `.strip()` before `to_ascii`.** Leading/trailing combining marks are legitimate
   in decomposed input.
4. **The Turkish change is a behavior change.** It is an improvement (`ı` was being deleted),
   but it *is* a change. Say so in the commit message so it is not mistaken for an accident.
5. **Do not add a dependency.** `unidecode` and `python-slugify` both solve this. `scripts/`
   is deliberately stdlib-only; `analyze_blog.py` and friends run in environments where
   `pip install` has not happened. Adding one would break that contract for a 30-line function.

## Acceptance criteria

- [ ] `scripts/vi_text.py` exists, is stdlib-only, has module and function docstrings
- [ ] `tests/test_vietnamese_slug.py` - all tests pass
- [ ] `tests/test_vietnamese_text.py` - all tests pass
- [ ] Both slugifiers produce identical output for every case in `VI_SLUG_CASES`
- [ ] English regression guards still pass
- [ ] Full suite: still `341 passed` plus the new tests; the pre-existing failure and 5
      errors unchanged
- [ ] `grep -rn "NFKD" scripts/` returns nothing

## Verification

```bash
cd claude-blog
../.venv/bin/python -m pytest tests/test_vietnamese_slug.py tests/test_vietnamese_text.py -v
../.venv/bin/python -m pytest tests/ -q
../.venv/bin/python -m pytest tests/test_blog_hygiene.py -v      # existing anchor tests
grep -rn "NFKD" scripts/                                          # must be empty
```

Then render a real Vietnamese post end to end and inspect the emitted filename:

```bash
../.venv/bin/python scripts/blog_render.py tests/fixtures/blog_vi_good.md --out /tmp/vi-render
ls /tmp/vi-render
```

## Commit

```
fix(vi): transliterate Vietnamese characters in slug generation

blog_render._slugify deleted every non-ASCII character without
normalizing, so "Hướng dẫn đặt hàng online" became
"hng-dn-t-hng-online". blog_hygiene.slugify normalized with NFKD but
NFKD cannot decompose đ (U+0111), so the letter was dropped:
"huong-dan-at-hang-online". Anchors and filenames therefore disagreed
and both were wrong.

Adds scripts/vi_text.py with the shared text primitives and routes both
slug functions through it. Vietnamese titles now produce readable ASCII
slugs; English output is byte-identical; Turkish improves, as dotless ı
(U+0131) was previously dropped for the same undecomposable-glyph reason.

Standard library only, per the scripts/ contract.
```
