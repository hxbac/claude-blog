# Vietnamese Support Implementation Plan

Implementation documentation for adding first-class Vietnamese-language support to
`claude-blog` and `claude-seo`.

## Why this exists

The four repositories in this workspace are high-quality English/Turkish SEO tooling. A
grep across all four for `vietnam|vi-VN|tiếng việt` returns **zero hits**. Vietnamese
content does not fail loudly - it fails **silently**, scoring as if it were English, with
mangled URLs and an unreachable quality gate.

This plan fixes that in seven phases, each independently shippable and independently
testable.

## Documents

| Document | Purpose |
|---|---|
| [`00-OVERVIEW.md`](00-OVERVIEW.md) | Problem statement, verified evidence, architectural principle, phase dependency graph |
| [`PHASE-0-TEST-HARNESS.md`](PHASE-0-TEST-HARNESS.md) | Vietnamese fixtures + failing tests that prove every defect before any fix |
| [`PHASE-1-SLUG.md`](PHASE-1-SLUG.md) | **P0** - Vietnamese-safe slug generation (currently destroys every Vietnamese URL) |
| [`PHASE-2-LANGUAGE-PROFILE.md`](PHASE-2-LANGUAGE-PROFILE.md) | **P0** - Vietnamese `LANGUAGE_PROFILES` entry (currently ~30/100 points lost silently) |
| [`PHASE-3-PROSE-LINTER.md`](PHASE-3-PROSE-LINTER.md) | **P1** - Vietnamese AI-writing-tell linter and register checker |
| [`PHASE-4-DATAFORSEO-VN.md`](PHASE-4-DATAFORSEO-VN.md) | **P1** - Vietnam market defaults + the missing DataForSEO wrapper |
| [`PHASE-5-DISCOURSE-DOCS.md`](PHASE-5-DISCOURSE-DOCS.md) | **P2** - Vietnamese discourse platforms, skill docs, frontmatter template |
| [`PHASE-6-E2E-REVIEW.md`](PHASE-6-E2E-REVIEW.md) | End-to-end test: write one real Vietnamese post in Claude Code, run all five gates, self-review |

## Reading order

Read `00-OVERVIEW.md` first. Phases are ordered by dependency, not by size:

```
PHASE-0 (harness)
   │
   ├──> PHASE-1 (slug)          ─┐
   ├──> PHASE-2 (lang profile)  ─┤
   ├──> PHASE-3 (prose linter)  ─┼──> PHASE-6 (E2E test + review)
   ├──> PHASE-4 (DataForSEO VN) ─┤
   └──> PHASE-5 (discourse/docs)─┘
```

Phases 1-5 are mutually independent once Phase 0 lands. They can be implemented in
parallel by separate agents. Phase 6 requires all of them.

## Ground rules for implementers

1. **Phase 0 first, always.** Every fix must have a test that fails before the fix and
   passes after. No exceptions.
2. **All Vietnamese logic goes in `scripts/vi_*.py`.** Never inline Vietnamese regexes into
   an existing analyzer. Python ports to Codex CLI for free; SKILL.md wrappers do not.
   See `00-OVERVIEW.md` § Architectural principle.
3. **Never break English or Turkish.** The existing suite must stay green. Run it before
   and after.
4. **Stdlib only in `scripts/`.** `analyze_blog.py` and its siblings are stdlib-only by
   design. Do not add a dependency to fix a Vietnamese problem.
5. **Write commits in English.** Repository language is English.
6. **The prose-hygiene linter scans `.py` as well as `.md`.** `scripts/lint_prose.py` forbids
   em-dash (U+2014), en-dash (U+2013) and ASCII ` -- ` in every file under `scripts/`,
   `tests/`, `skills/`, `agents/` and `docs/`, including inside comments, docstrings and
   string literals. Code fences in these planning documents are exempt while they are
   Markdown but stop being exempt the moment you paste them into a `.py` file. Run
   `python scripts/lint_prose.py --root .` before every commit.

## Baseline

Recorded on the working tree at the time this plan was written, `claude-blog` on `main`
at `84f7abf`:

```
claude-blog:  346 passed, 1 skipped   (with python-markdown installed)
claude-seo :  439 passed, 2 failed
```

`claude-seo`'s two failures are pre-existing and unrelated: `test_sync_flow.py::test_dry_run_exits_zero`
and `::test_dry_run_produces_valid_json` reach the network to pull FLOW references and fail
without it. Do not fix them as part of a phase.

**Correction.** Earlier revisions of this file recorded `claude-blog`'s
`test_markdown_body_html_is_sanitized` as a pre-existing failure with an over-strict
assertion, and four implementing agents were told to ignore it on that basis. That diagnosis
was wrong. The test fails only when **python-markdown is not installed**: `blog_render.py`
falls back to a stdlib markdown implementation that escapes raw HTML blocks wholesale, so the
literal string the test looks for really does survive into the output. Installing `markdown`
makes it pass, and it now passes at every commit on this branch when the dependency is
present, including the first.

The library was not declared in `requirements.txt` at all. It is now, as a core dependency,
because Gate 2 of the delivery contract requires a rendered `.html` and the fallback also
drops tables, footnotes and definition lists (`blog_render.py` warns loudly on stderr when it
takes that path with those constructs present, but not for raw HTML).

## Environment

`pytest` is not installed system-wide on this machine and `pip3` is absent from `PATH`.
Create one venv at the workspace root and use it for both repositories:

```bash
cd /home/bachx/workspace/Hien/ai
python3 -m venv .venv
.venv/bin/pip install pytest requests pillow pyyaml \
                      google-api-python-client google-auth-oauthlib \
                      beautifulsoup4 lxml
cd claude-blog && ../.venv/bin/python -m pytest tests/ -q
```

Without `google-api-python-client`, `bs4` and `lxml`, `claude-seo`'s suite cannot even be
collected and `claude-blog` reports 5 collection errors. Those are missing optional
dependencies, not defects.

**Executable bits.** These repositories were copied into place as root and lost the
executable bit on 80 files that git records as `100755`, while `core.fileMode` is `false`
so git does not report the difference. That alone caused 7 spurious `claude-seo` failures.
Already restored; if you see `test_extension_install_script_is_executable` failing, run:

```bash
git ls-files -s | awk '$1=="100755"{$1="";$2="";$3="";sub(/^ +/,"");print}' | xargs -r chmod +x
```
