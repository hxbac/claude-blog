# Phase 6 - End-to-end test and self-review

**Priority:** verification · **Repo:** `claude-blog` · **Estimate:** 0.5 day
**Depends on:** Phases 0-5

## Goal

Write one real Vietnamese blog post through Claude Code, run it through all five delivery
gates, then review the result critically and write down what actually happened - including
what did not work.

Unit tests prove each fix in isolation. This phase is the only one that answers the question
that matters: **can a Vietnamese marketer open Claude Code, type one command, and get a
publishable post?**

## Preconditions

```bash
cd /home/bachx/workspace/Hien/ai/claude-blog
git log --oneline -8                       # Phases 0-5 present
../.venv/bin/python -m pytest tests/ -q    # green apart from the documented baseline
```

### What this phase can and cannot exercise

`claude-blog` is not installed into `~/.claude/` in this environment, so `/blog write` is not
invokable as a slash command. Installing it would write into the user's home directory, which
is beyond the scope of implementing these phases.

So this phase drives **the same machinery the orchestrator drives**, directly:

| Exercised | Not exercised |
|---|---|
| Writing a Vietnamese post against `skills/blog-write/SKILL.md` | The `/blog` orchestrator's routing |
| `scripts/blog_render.py` (slug, HTML, PDF) | Automatic subagent dispatch |
| `scripts/blog_preflight.py --gate 1..5` | The 3-attempt iteration loop firing on its own |
| `scripts/analyze_blog.py` scoring under `vi` | |
| `scripts/vi_prose.py` | |
| A reviewer pass following `agents/blog-reviewer.md` | |

Everything the six phases changed is in the left column. Say so plainly in the review; do not
write it up as if `/blog write` ran end to end.

## 6.1 - The topic

Use one topic, fixed, so results are comparable across runs:

> **`Cách tối ưu Core Web Vitals cho website tiếng Việt`**

Chosen deliberately:

- **Genuinely Vietnamese** - not an English topic translated. Vietnamese mobile networks are
  slower than European or US ones, so field CrUX data diverges from lab data in a way that
  gives the post something real to say.
- **Technical enough to need citations**, so E-E-A-T and citation scoring are exercised
  rather than skipped.
- **Contains `đ`, `ơ`, `ư` and tone marks** in the natural title, so the slug path is
  exercised without contriving it.
- **Has a real Vietnamese search audience**, so keyword data comes back non-empty.

## 6.2 - The run

Work in a scratch directory outside the repository, for example
`/tmp/vi-e2e/<slug>/`. Do not commit the draft.

1. Read `skills/blog-write/SKILL.md` and follow it as the orchestrator would. Write the post
   in Vietnamese. **Do not consult `tests/fixtures/blog_vi_good.md`** - reusing it would
   test nothing.
2. **Do not hand-write `lang: vi` unless the template you are following tells you to.** Phase 2
   added that field to the template; whether it survives into the draft is part of what is
   being tested. If detection has to be told, it is not fixed.
3. Render: `python scripts/blog_render.py --md <draft>.md --out-dir <dir>`
4. Run each gate: `python scripts/blog_preflight.py --draft <dir> --gate N --json`
5. For Gate 4, read `agents/blog-reviewer.md` and apply it yourself, then cross-check against
   `python scripts/analyze_blog.py <draft>.md --json`.
6. If a gate fails, do exactly what the contract says the iteration loop would do, by hand,
   and count the iterations.

Record, at each gate:

| Gate | Record |
|---|---|
| 1. Capability Discovery | Which capabilities were found; whether `lang` resolved to `vi` and where that is visible |
| 2. Format Completeness | The four artifacts; **the exact slug/filename produced** |
| 3. Visual Verification | Screenshots; whether Vietnamese diacritics render correctly in HTML and PDF |
| 4. Content Review | Full scorecard, every category, the reviewer's P0/P1 list |
| 5. Asset + Link Integrity | Broken links; whether the hero image is appropriate for a Vietnamese audience |

Also record **the number of iterations**. One or two is healthy. Three followed by
escalation means Phase 2 did not fully land.

## 6.3 - Checks that only this phase can make

Run after the post is delivered:

```bash
DRAFT=<path to the draft folder>

# Slug: must be readable Vietnamese transliteration
ls "$DRAFT"
# Expect something like cach-toi-uu-core-web-vitals-cho-website-tieng-viet.md
# NOT cch-ti-u-core-web-vitals-cho-website-ting-vit.md

# Language actually resolved
grep -n "^lang:" "$DRAFT"/*.md

# Score and model
../.venv/bin/python scripts/analyze_blog.py "$DRAFT"/*.md --json | python3 -c "
import json,sys
d=json.load(sys.stdin)
print('score       :', d.get('total_score'))
print('model       :', d.get('readability',{}).get('reading_model'))
print('avg syll/sen:', d.get('readability',{}).get('avg_sentence_length'))
print('breakdown   :', json.dumps(d.get('breakdown'), ensure_ascii=False, indent=2))
"

# Prose linter
../.venv/bin/python scripts/vi_prose.py "$DRAFT"/*.md

# Anchors agree with the rendered HTML
grep -o 'id="[^"]*"' "$DRAFT"/*.html | head -20

# Diacritics survived the PDF
../.venv/bin/python -c "
import re,sys
html=open(sys.argv[1],encoding='utf-8').read()
print('has Vietnamese chars:', bool(re.search(r'[ăâêôơưđáàảãạếềểễệốồổỗộ]', html)))
" "$DRAFT"/*.html
```

Expected: `reading_model` is `vi_syllable`, not `flesch`. If it is `flesch`, detection
failed and everything downstream is invalid regardless of the score.

## 6.4 - Self-review

Write `docs/VI-E2E-REVIEW-<YYYY-MM-DD>.md` in the repository. Structure:

### 1. What was run
Command, date, commit SHA, plugin version, which capabilities were available.

### 2. Result
Final score, per-category breakdown, iteration count, wall-clock time.

### 3. Read the post as a Vietnamese reader
Not as a scorer. Judge honestly:

- Does it sound like a Vietnamese person wrote it, or like a translation? Be specific -
  quote the sentences that give it away.
- Is the register consistent, and is the chosen register right for the audience?
- Are the examples Vietnamese, or American examples with Vietnamese words?
- Would you publish this on a client's site without editing? If not, what would you change?

**This section is the point of the phase.** A 92/100 post that reads like machine
translation means the scorer is measuring the wrong thing, and that finding is worth more
than the score.

### 4. What the gates caught
Which gate failed, what the iteration prompt was, whether the fix was the right one.

### 5. What the gates missed
Defects you can see that no gate flagged. Each one is a candidate rule for a future phase.

### 6. Where the phases fell short
Per phase, honestly:

| Phase | Worked | Did not work |
|---|---|---|
| 1 Slug | | |
| 2 Language profile | | |
| 3 Prose linter | | |
| 4 DataForSEO | | |
| 5 Discourse/docs | | |

### 7. Next
Ranked list of what to fix, with the evidence for each.

## 6.5 - Second run: the negative control

Run the same command with `--no-strict` (or the documented bypass) and compare. This
answers whether the gates are doing anything, or whether the model would have produced the
same output regardless. If the two drafts are equivalent, the gates are theatre and the
review should say so.

## 6.6 - Third run: a different domain

One more topic, deliberately unlike the first:

> **`Kinh nghiệm chọn quán cà phê làm việc ở Hà Nội`**

Consumer, local, informal register, needs local imagery, no technical citations. This
exercises the paths the technical topic never touches: local SEO, `bạn` register, the
Vietnamese stock-photo gap. Add a short section to the review comparing the two.

## Pitfalls

1. **Do not hand-edit the draft before scoring it.** The number you want is what the system
   produced, not what you could produce.
2. **Do not pick a topic you already have keyword data for.** The point is a cold start.
3. **A high score is not the pass condition.** The pass condition is a post a Vietnamese
   marketer would publish. If those two disagree, write that down - it is the most valuable
   output of the phase.
4. **Do not skip the negative control.** It is the only evidence that the gates matter.
5. **Record failures verbatim.** Paste the actual error text and scorecard into the review,
   not a summary of it. Summaries lose the detail that makes a bug findable.
6. **Do not fix things during the run.** Note them and finish the run. Fixing mid-run makes
   the result unreproducible.

## Acceptance criteria

- [ ] `/blog write <Vietnamese topic>` completes without manual intervention
- [ ] `lang` resolved to `vi` **without** being declared by hand
- [ ] `reading_model` is `vi_syllable`
- [ ] Slug is a correct Vietnamese transliteration - `đ` present as `d`, no dropped letters
- [ ] All five gates pass in ≤ 2 iterations
- [ ] Diacritics correct in `.md`, `.html` and `.pdf`
- [ ] `vi_prose.py` reports 0 P0 findings on the generated post
- [ ] `docs/VI-E2E-REVIEW-<date>.md` exists with all seven sections
- [ ] Negative control run and compared
- [ ] Second topic run and compared
- [ ] Section 5 ("what the gates missed") is **not empty** - if it is, the review was not
      critical enough

## Verification

The run itself is the verification; section 6.3 lists the checks. Confirm before closing
the phase:

```bash
cd claude-blog
../.venv/bin/python -m pytest tests/ -q          # still green
../.venv/bin/python scripts/lint_prose.py .      # the review doc is under docs/, which CI lints
test -f docs/VI-E2E-REVIEW-*.md && echo "review written"
grep -c "^### " docs/VI-E2E-REVIEW-*.md          # expect 7 sections
```

The review document lives in `docs/`, which `lint_prose.py` scans. Em-dashes, en-dashes and
spaced double-hyphens will fail CI - write it with plain hyphens.

## Commit

```
test(vi): end-to-end Vietnamese blog run and review

Runs /blog write on a Vietnamese topic with no manual hints, through all
five delivery gates, and records the result.

- docs/VI-E2E-REVIEW-<date>.md: full scorecard, gate-by-gate record, a
  reader-level critique of the generated Vietnamese, what the gates
  caught, what they missed, and where each phase fell short
- Includes a --no-strict negative control and a second topic in a
  different register for comparison

Findings are recorded, not fixed, in this commit.
```
