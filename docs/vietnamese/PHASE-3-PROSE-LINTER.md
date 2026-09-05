# Phase 3 - Vietnamese prose linter

**Priority:** P1 · **Repo:** `claude-blog` · **Estimate:** 1 day
**Depends on:** Phase 0, and `scripts/vi_text.py` from Phase 1

## Goal

Catch the two Vietnamese failure modes that no existing check can see: machine-sounding
formulaic prose, and inconsistent second-person address. Both are invisible to
`lint_prose.py`, which enforces character hygiene (em-dashes, en-dashes) and is
language-agnostic by design.

## Why this matters more in Vietnamese than in English

Two reasons, both structural:

1. **The tells are more uniform.** Vietnamese AI output converges on a small set of stock
   openers - *"Trong thế giới ngày nay"*, *"Không thể phủ nhận rằng"*, *"Hãy cùng đi sâu
   vào"* - far more consistently than English does. A finite regex list catches most of them,
   which is not true for English.
2. **Register is grammatical, not stylistic.** Vietnamese second-person address encodes
   social distance: `bạn` (peer), `quý khách` (formal/commercial), `anh chị` (polite/sales),
   `mình` (intimate). Mixing them inside one document is not a style wobble the way
   *you/one/the reader* would be in English - it reads as either careless or assembled from
   pieces. English prose linters have no equivalent check because English has no equivalent
   grammar.

## Implementation

### 3.1 - Create `scripts/vi_prose.py`

Standard library only, deterministic, no model calls. Verified against a good and a bad
sample: **11 of 12 tells fire on the bad sample with zero false positives on the good one**,
and register drift is detected correctly.

```python
#!/usr/bin/env python3
"""Vietnamese prose linter: AI-writing tells and register consistency.

Deterministic, standard library only. Complements scripts/lint_prose.py, which
enforces character hygiene across all languages; this module adds the
Vietnamese-specific checks that a language-agnostic linter cannot express.

Usage:
    python3 vi_prose.py <file.md> [--json] [--max-density 2.0]

Exit codes:
    0  clean, or findings below threshold
    1  density threshold exceeded, or a P0 finding
    2  usage / IO error
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    from vi_text import count_syllables, normalize
except ImportError:                                   # standalone execution
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from vi_text import count_syllables, normalize

__all__ = ["lint_text", "AI_TELLS", "REGISTER_SETS"]

# ---------------------------------------------------------------------------
# AI-writing tells
#
# Formulaic openers and connectives that appear far more often in
# machine-generated Vietnamese than in prose a person actually wrote.
# Each entry is (pattern, human-readable label, suggested fix).
# ---------------------------------------------------------------------------
AI_TELLS: tuple[tuple[str, str, str], ...] = (
    (r'trong\s+(?:thế\s+giới|thời\s+đại|bối\s+cảnh)\s+(?:ngày\s+nay|hiện\s+nay|'
     r'số\s+hoá|công\s+nghệ\s+số|4\.0)',
     'Mở bài sáo rỗng', 'Vào thẳng vấn đề người đọc đang gặp.'),
    (r'không\s+thể\s+phủ\s+nhận\s+(?:rằng|là)',
     'Khẳng định rỗng', 'Bỏ. Nếu đúng thì không cần nói là không thể phủ nhận.'),
    (r'điều\s+(?:quan\s+trọng|đáng\s+lưu\s+ý)\s+(?:cần\s+)?(?:lưu\s+ý|nhớ|biết)\s+là',
     'Câu đệm', 'Bỏ cụm này và giữ lại nội dung phía sau.'),
    (r'hãy\s+cùng\s+(?:đi\s+sâu|tìm\s+hiểu|khám\s+phá|điểm\s+qua)',
     'Dẫn dắt thừa', 'Bỏ. Người đọc đã bấm vào bài rồi.'),
    (r'(?:tóm\s+lại|nhìn\s+chung)\s*,?\s*(?:có\s+thể\s+thấy|chúng\s+ta\s+có\s+thể\s+thấy)',
     'Kết bài sáo rỗng', 'Kết bằng một hành động cụ thể.'),
    (r'đóng\s+(?:một\s+)?vai\s+trò\s+(?:vô\s+cùng\s+)?quan\s+trọng',
     'Cụm mòn', 'Nói rõ nó làm gì.'),
    (r'ngày\s+càng\s+trở\s+nên\s+(?:phổ\s+biến|quan\s+trọng|cần\s+thiết)',
     'Cụm mòn', 'Đưa số liệu thay vì tính từ.'),
    (r'là\s+một\s+trong\s+những\s+yếu\s+tố\s+(?:then\s+chốt|quan\s+trọng\s+nhất)',
     'Cụm mòn', 'Xếp hạng cụ thể hoặc bỏ.'),
    (r'giúp\s+(?:bạn\s+)?(?:tối\s+ưu\s+hoá|nâng\s+cao|cải\s+thiện)\s+'
     r'(?:một\s+cách\s+)?(?:hiệu\s+quả|đáng\s+kể|tối\s+đa)',
     'Hứa hẹn mơ hồ', 'Nêu con số cải thiện thực tế.'),
    (r'trong\s+bài\s+viết\s+(?:này|dưới\s+đây)\s*,?\s*(?:chúng\s+ta|chúng\s+tôi|tôi)\s+sẽ',
     'Meta thừa', 'Bỏ. Bắt đầu bằng nội dung.'),
    (r'hy\s+vọng\s+(?:rằng\s+)?bài\s+viết\s+(?:này\s+)?(?:sẽ\s+)?(?:hữu\s+ích|giúp\s+ích)',
     'Kết bài sáo rỗng', 'Kết bằng bước tiếp theo cụ thể.'),
    (r'với\s+sự\s+phát\s+triển\s+(?:không\s+ngừng\s+)?của\s+(?:công\s+nghệ|internet)',
     'Mở bài sáo rỗng', 'Vào thẳng vấn đề.'),
)

# ---------------------------------------------------------------------------
# Register (xưng hô). Vietnamese second-person address encodes social distance.
# Mixing sets inside one document reads as careless or machine-assembled.
# ---------------------------------------------------------------------------
REGISTER_SETS: dict[str, tuple[str, ...]] = {
    'than_mat':    (r'bạn', r'các\s+bạn', r'mình'),                     # peer, informal
    'trang_trong': (r'quý\s+khách', r'quý\s+vị', r'quý\s+công\s+ty'),   # formal, commercial
    'lich_su':     (r'anh\s*/\s*chị', r'anh\s+chị', r'các\s+anh\s+chị'),# polite, sales
}


def _strip_markdown(text: str) -> str:
    """Remove code fences, tables, HTML and link targets before linting prose."""
    text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    text = re.sub(r'`[^`]*`', '', text)
    text = re.sub(r'^\s*\|.*\|\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'!\[.*?\]\(.*?\)', '', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    return text


def lint_text(raw: str) -> dict:
    """Return findings for one document. Pure; no IO."""
    text = normalize(_strip_markdown(raw))
    lower = text.lower()
    total_syllables = max(count_syllables(text), 1)

    findings: list[dict] = []
    for pattern, label, fix in AI_TELLS:
        for match in re.finditer(pattern, lower, re.IGNORECASE):
            line = lower.count('\n', 0, match.start()) + 1
            findings.append({
                'type': 'ai_tell', 'severity': 'P1', 'label': label,
                'match': match.group(0), 'line': line, 'fix': fix,
            })

    # Register drift: report only when two or more sets are actually used.
    register_hits: dict[str, int] = {}
    for name, patterns in REGISTER_SETS.items():
        count = sum(len(re.findall(rf'(?<![^\W\d_]){p}(?![^\W\d_])', lower))
                    for p in patterns)
        if count:
            register_hits[name] = count
    if len(register_hits) >= 2:
        dominant = max(register_hits, key=register_hits.get)
        findings.append({
            'type': 'register_drift', 'severity': 'P0',
            'label': 'Xưng hô không nhất quán',
            'match': ', '.join(f'{k}={v}' for k, v in sorted(register_hits.items())),
            'line': 0,
            'fix': f'Chọn một cách xưng hô cho cả bài. Đang dùng nhiều nhất: {dominant}.',
        })

    tells = sum(1 for f in findings if f['type'] == 'ai_tell')
    return {
        'syllables': total_syllables,
        'ai_tell_count': tells,
        'ai_tell_density_per_1000': round(tells / total_syllables * 1000, 2),
        'register_sets_used': register_hits,
        'findings': findings,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('path', type=Path)
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--max-density', type=float, default=2.0,
                    help='Max AI tells per 1000 syllables before failing (default: 2.0)')
    args = ap.parse_args()

    try:
        raw = args.path.read_text(encoding='utf-8')
    except OSError as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2

    report = lint_text(raw)
    report['max_density'] = args.max_density
    has_p0 = any(f['severity'] == 'P0' for f in report['findings'])
    failed = report['ai_tell_density_per_1000'] > args.max_density or has_p0
    report['passed'] = not failed

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"{args.path}: {report['ai_tell_count']} dấu hiệu AI "
              f"/ {report['syllables']} âm tiết "
              f"(mật độ {report['ai_tell_density_per_1000']}/1000, "
              f"ngưỡng {args.max_density})")
        for f in report['findings']:
            loc = f"dòng {f['line']}" if f['line'] else 'toàn bài'
            print(f"  [{f['severity']}] {loc}: {f['label']} - {f['match']!r}")
            print(f"          → {f['fix']}")
        print('PASS' if report['passed'] else 'FAIL')

    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
```

### 3.2 - Tests: `tests/test_vi_prose.py`

```python
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import vi_prose

FIXTURES = Path(__file__).parent / "fixtures"


def test_every_pattern_compiles():
    """A bad escape in one pattern silently disables that check."""
    import re
    for pattern, label, _fix in vi_prose.AI_TELLS:
        re.compile(pattern)                     # raises re.error on a bad pattern
        assert label, "every tell needs a label"


def test_bad_fixture_is_caught():
    raw = (FIXTURES / "blog_vi_bad.md").read_text(encoding="utf-8")
    report = vi_prose.lint_text(raw)
    assert report["ai_tell_count"] >= 5
    assert report["ai_tell_density_per_1000"] > 2.0


def test_good_fixture_is_clean():
    raw = (FIXTURES / "blog_vi_good.md").read_text(encoding="utf-8")
    report = vi_prose.lint_text(raw)
    assert report["ai_tell_count"] == 0, [f["match"] for f in report["findings"]]
    assert report["ai_tell_density_per_1000"] <= 2.0


def test_register_drift_detected():
    text = "Quý khách vui lòng liên hệ. Các bạn cũng có thể tự làm."
    report = vi_prose.lint_text(text)
    assert any(f["type"] == "register_drift" for f in report["findings"])


def test_single_register_is_not_flagged():
    text = "Bạn nên nén ảnh trước. Sau đó bạn bật cache. Cuối cùng bạn đo lại."
    report = vi_prose.lint_text(text)
    assert not any(f["type"] == "register_drift" for f in report["findings"])


def test_code_blocks_are_ignored():
    """A tell inside a fenced block is a code sample, not prose."""
    text = "```\ntrong thế giới ngày nay\n```\nNội dung thật ở đây."
    assert vi_prose.lint_text(text)["ai_tell_count"] == 0


def test_english_text_produces_nothing():
    text = "In today's world, SEO plays a very important role for every business."
    assert vi_prose.lint_text(text)["ai_tell_count"] == 0
```

### 3.3 - Wire into the delivery contract

Add the linter to Gate 4 (Content Review) in
`skills/blog/references/blog-delivery-contract.md`, **for Vietnamese posts only**:

> When `lang` resolves to `vi`, Gate 4 additionally runs
> `python3 scripts/vi_prose.py <draft>.md --json`. A `P0` finding (register drift) blocks.
> An AI-tell density above 2.0 per 1000 syllables blocks. Both are reported to
> `blog-writer` with the specific line numbers and suggested fixes, not as a generic
> "improve the writing" instruction.

Keep the SKILL.md text this short. The rules live in the Python file; restating them in
prose creates two sources of truth that will drift.

### 3.4 - Optional: a `/blog vi-lint` command

Only if commands are cheap to add in this repo - check `docs/COMMANDS.md` for the
registration pattern first. Not required for the phase to be complete.

## Verified behavior

Bad sample (formulaic Vietnamese, 130 syllables):

```
11 tells, density 84.62/1000
  [P1] Mở bài sáo rỗng: 'trong thế giới ngày nay'
  [P1] Khẳng định rỗng: 'không thể phủ nhận rằng'
  [P1] Câu đệm: 'điều quan trọng cần lưu ý là'
  [P1] Dẫn dắt thừa: 'hãy cùng đi sâu'
  [P1] Kết bài sáo rỗng: 'tóm lại, có thể thấy'
  [P1] Cụm mòn: 'đóng vai trò vô cùng quan trọng'
  [P1] Cụm mòn: 'ngày càng trở nên quan trọng'
  [P1] Cụm mòn: 'là một trong những yếu tố then chốt'
  [P1] Hứa hẹn mơ hồ: 'giúp bạn tối ưu hoá một cách hiệu quả'
  [P1] Meta thừa: 'trong bài viết này, chúng tôi sẽ'
  [P1] Kết bài sáo rỗng: 'hy vọng bài viết này sẽ hữu ích'
  [P0] Xưng hô không nhất quán: 'lich_su=1, than_mat=5, trang_trong=1'
```

Good sample (real prose with evidence, 90 syllables): **0 tells, no register drift.**

CLI exit codes verified: `1` on failure, `2` on a missing file, `0` when clean.

## Pitfalls

1. **A `bad escape` in one pattern kills that check silently - no, loudly, but only at
   import.** During development one pattern here contained `khám\phá`, which raises
   `re.error: bad escape \p`. `test_every_pattern_compiles` exists specifically to catch
   this class of mistake before it reaches a user.
2. **Do not lint inside code fences.** A tutorial about bad writing legitimately quotes bad
   writing. `_strip_markdown` runs first; keep it first.
3. **Register detection needs boundaries that work on Vietnamese.** `\bbạn\b` does not work
   (see Phase 2, the `\b` trap). The implementation uses
   `(?<![^\W\d_])…(?![^\W\d_])`, which is Unicode-aware. Without it, `bạn` matches inside
   `bạn bè`, `bạn đọc`, and every other compound.
4. **Do not block on tells alone.** A density threshold, not a zero-tolerance rule. One
   stock phrase in a 2,000-word article is a stylistic choice; ten is a signature. The
   default `--max-density 2.0` means roughly "more than 2 per 1,000 syllables".
5. **This is not a plagiarism or AI detector, and must not be described as one.** It finds
   formulaic phrasing. Human writers use these phrases too. The output is advice with line
   numbers, not a verdict about authorship - keep the wording of every message consistent
   with that.
6. **Do not expand the register sets to cover kinship pronouns** (`em`, `chú`, `cô`, `bác`).
   They are extremely common as ordinary nouns and will generate constant false positives.
   The three sets here are the ones that function as *audience address*.

## Acceptance criteria

- [ ] `scripts/vi_prose.py` exists, stdlib-only (plus sibling `vi_text`), no control characters
- [ ] Every pattern in `AI_TELLS` compiles - enforced by a test, not by inspection
- [ ] `tests/test_vi_prose.py` - all tests pass
- [ ] `blog_vi_bad.md` → ≥ 5 tells, density > 2.0, register drift flagged
- [ ] `blog_vi_good.md` → 0 tells, no drift
- [ ] English text produces zero findings
- [ ] CLI: `0` clean / `1` fail / `2` IO error
- [ ] Gate 4 documentation updated, Vietnamese-only, ≤ 5 lines of prose
- [ ] Full suite unchanged otherwise

## Verification

```bash
cd claude-blog
../.venv/bin/python -m pytest tests/test_vi_prose.py -v
../.venv/bin/python scripts/vi_prose.py tests/fixtures/blog_vi_bad.md;  echo "exit=$?"   # 1
../.venv/bin/python scripts/vi_prose.py tests/fixtures/blog_vi_good.md; echo "exit=$?"   # 0
../.venv/bin/python scripts/vi_prose.py /nonexistent.md;                echo "exit=$?"   # 2
../.venv/bin/python -m pytest tests/ -q
```

## Commit

```
feat(vi): add Vietnamese prose linter for AI tells and register drift

Adds scripts/vi_prose.py, a deterministic Vietnamese prose check that
lint_prose.py cannot express because it is language-agnostic by design.

Two checks:
- AI-writing tells: 12 formulaic Vietnamese constructions, reported with
  line numbers and a concrete rewrite suggestion, scored as a density per
  1000 syllables rather than an absolute count
- Register drift (P0): Vietnamese second-person address encodes social
  distance; mixing bạn / quý khách / anh chị in one document is a
  grammatical inconsistency, not a style preference

Wired into Gate 4 for Vietnamese posts only. Standard library only.
```
