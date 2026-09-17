# Vietnamese Language Support

Vietnamese (`lang: vi`) publishing is tracked as a phased plan, not a single
change. Full detail lives in `docs/vietnamese/`:

- `docs/vietnamese/00-OVERVIEW.md` - the problem statement and verified evidence
  for every defect (slug destruction, silent language fallback, hardcoded
  English patterns in the scoring engine).
- `docs/vietnamese/PHASE-0-TEST-HARNESS.md` through `PHASE-6-E2E-REVIEW.md` -
  one document per phase.

## Phase status

| Phase | Title | Status |
|---|---|---|
| 0 | Test harness and Vietnamese fixtures | Done - fixtures and failing tests landed, no production code changed |
| 1 | Vietnamese-safe slugs | Not started |
| 2 | Vietnamese language profile | Not started |
| 3 | Vietnamese prose linter | Not started |
| 4 | DataForSEO Vietnam defaults + wrapper | Not started |
| 5 | Discourse platforms, skill docs, frontmatter | Not started |
| 6 | End-to-end Vietnamese post + self-review | Not started (needs 0-5) |

## Why the tests fail today

`tests/test_vietnamese_slug.py`, `tests/test_vietnamese_analysis.py`, and
`tests/test_vietnamese_text.py` are the specification for Phases 1-3. They
are expected to fail until the corresponding phase lands; a passing test
that was never seen to fail proves nothing about the fix. See
`docs/vietnamese/PHASE-0-TEST-HARNESS.md` for the exact failing-test list
recorded at the time each fixture and test file was added.

## Architectural rule

All Vietnamese-specific logic belongs in `scripts/vi_*.py` (normalization,
slug transliteration, syllable counting, the language profile, prose
linting), never inline in a script that also serves other languages and
never restated as prose in a `SKILL.md`. See `docs/vietnamese/00-OVERVIEW.md`
§ 3 for the reasoning.
