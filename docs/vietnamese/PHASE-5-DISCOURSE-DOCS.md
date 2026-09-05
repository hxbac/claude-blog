# Phase 5 - Vietnamese discourse sources and documentation

**Priority:** P2 · **Repo:** `claude-blog` · **Estimate:** 0.5 day
**Depends on:** Phase 0

## Goal

Research reaches where Vietnamese users actually talk, and a Vietnamese writer can find out
what the tool supports without reading Python.

Small phase, high leverage. `blog-discourse` is the cheapest research capability in the
repository - it needs **no API key at all** - and it currently cannot see Vietnam.

## 5.1 - Vietnamese platforms in `blog-discourse`

`skills/blog-discourse/SKILL.md:63-75` composes 4-8 WebSearch queries using `site:`
operators. The table lists exactly nine platforms:

| Platform | Operator |
|---|---|
| Reddit | `site:reddit.com/r/<sub>` |
| Hacker News | `site:news.ycombinator.com` |
| X / Twitter | `site:x.com` |
| YouTube | `site:youtube.com` |
| dev.to | `site:dev.to` |
| Medium | `site:medium.com` |
| GitHub | `site:github.com` |
| StackOverflow | `site:stackoverflow.com` |
| Substack | `site:substack.com` |

All nine are Western. For a Vietnamese topic, Reddit and Hacker News return almost nothing,
so the skill produces a thin brief and the writer has no voice-of-customer material.

Add:

| Platform | Operator | Use for |
|---|---|---|
| Voz | `site:voz.vn` | Technology, consumer goods, personal finance. Highest-signal Vietnamese forum. |
| Tinh tế | `site:tinhte.vn` | Technology, product reviews, hands-on impressions |
| Webtretho | `site:webtretho.com` | Parenting, family, health, household |
| OtoFun | `site:otofun.net` | Cars, motorbikes |
| Spiderum | `site:spiderum.com` | Long-form opinion, career, self-development |
| VnExpress comments | `site:vnexpress.net` | Mainstream reaction to news topics |

Then add a selection rule to the skill so it does not spend all its queries on the wrong
half of the table:

> When the topic or the requested output language is Vietnamese, use the Vietnamese
> platform rows for at least half of the composed searches. Facebook groups are where much
> Vietnamese discussion happens but are not indexed and cannot be reached with a `site:`
> operator - state this as a known coverage gap in the brief rather than omitting it
> silently.

`after:YYYY-MM-DD` and `before:` are Google operators and work unchanged for Vietnamese
queries - no recency change is needed.

## 5.2 - Vietnamese output language for the brief

Check whether `discourse_research.py` and the skill emit `DISCOURSE.md` with English section
headers. If the brief will feed a Vietnamese writer, the quoted material must stay in
Vietnamese verbatim - do not translate quotes. Translating a user's own words defeats the
purpose of voice-of-customer research.

Add to the skill:

> Quotes are reproduced in their original language, always. Section headers follow the
> language of the target post.

## 5.3 - `docs/VIETNAMESE.md`

One page in `claude-blog/docs/`, written in English (repository language) with Vietnamese
examples. Sections:

1. **What is supported** - table of `lang: vi` behavior: profile, slug, readability model,
   prose linter
2. **Quick start** - write a Vietnamese post in three commands
3. **What is different from English** - Flesch does not apply; `đ` needs special handling;
   register consistency is enforced; Labs data is country-level only
4. **Known limitations** - no Vietnamese CMS integration; stock photo libraries are thin on
   Vietnamese imagery; AI image generation cannot render Vietnamese diacritics correctly;
   Google Cloud NLP entity extraction is weaker for Vietnamese than English
5. **Reference tables** - Vietnamese location codes, register sets, the AI-tell list

Keep it to one screen per section. Link to the code for detail rather than restating it.

## 5.4 - Vietnamese examples in existing skill docs

`blog-write`, `blog-brief`, `blog-outline` and `blog-cluster` all carry English examples.
A model given only English examples will produce English-shaped Vietnamese - sentence
rhythm, heading style and CTA phrasing all carry over.

Add one Vietnamese example to each, next to the English one. Not a translation of the
English example: a genuinely Vietnamese one, on a Vietnamese topic, with Vietnamese heading
conventions.

## 5.5 - Image guidance for Vietnamese

Add to `skills/blog-image/SKILL.md`:

> **Vietnamese text in generated images.** Every current image model renders Vietnamese
> diacritics incorrectly - missing tone marks, marks on the wrong vowel, `đ` rendered as
> `d`. Never ask a model to draw Vietnamese text inside an image. Generate the image
> without text and overlay it with HTML/CSS, where the text stays selectable, translatable
> and correct.

And to the stock photo path:

> Unsplash, Pexels, Pixabay and Openverse are all thin on Vietnamese subjects - people,
> streets, products, signage. For a post that needs local imagery, say so rather than
> shipping a generic stock photo of a Western office.

## 5.6 - Vietnamese trust signals in E-E-A-T guidance

Vietnamese commercial sites carry trust signals that have no English equivalent, and the
E-E-A-T reference does not mention them:

| Signal | What it is | Why it matters |
|---|---|---|
| MST / mã số thuế | Tax identification number | Standard proof of a registered business |
| Bộ Công Thương | Ministry of Industry and Trade registration badge | Legally required for e-commerce sites; its absence is conspicuous |
| Nghị định 13/2023/NĐ-CP | Personal data protection decree | The Vietnamese equivalent of a GDPR reference in a privacy policy |
| Địa chỉ + hotline | Physical address and phone number | Vietnamese readers expect both; an email-only contact reads as unserious |

Add these to the E-E-A-T reference as *Vietnamese-market trust signals*, clearly scoped to
Vietnam. Do not add them to the scorer in this phase - they are guidance for the writer,
not a scored rule, and scoring them would need care about false positives on non-commercial
posts.

## Pitfalls

1. **Do not remove the English platforms.** Bilingual and technical Vietnamese topics still
   get real signal from Hacker News and GitHub. Add, do not replace.
2. **Do not promise Facebook coverage.** A large share of Vietnamese discussion happens in
   Facebook groups that are not indexed and cannot be reached by `site:`. Naming the gap is
   honest; implying coverage is not.
3. **Do not translate quotes.** Voice-of-customer research is worthless once paraphrased
   through another language.
4. **Do not add Vietnamese trust signals to the scorer here.** Guidance now; scoring is a
   separate decision that needs its own false-positive analysis.
5. **Verify each forum still matters before adding it.** Vietnamese forum traffic shifts.
   Check that a site is live and active rather than copying this list on faith.

## Acceptance criteria

- [ ] 6 Vietnamese platforms added to the `blog-discourse` operator table
- [ ] Selection rule present: Vietnamese topics use Vietnamese platforms for ≥ half the searches
- [ ] Facebook coverage gap stated explicitly
- [ ] Quote-preservation rule added
- [ ] `docs/VIETNAMESE.md` exists with all five sections
- [ ] One Vietnamese example added to each of `blog-write`, `blog-brief`, `blog-outline`,
      `blog-cluster`
- [ ] Image guidance added - no Vietnamese text inside generated images
- [ ] Vietnamese trust signals added to the E-E-A-T reference, scoped to Vietnam
- [ ] `tests/test_discourse_research.py` still passes
- [ ] No change to scoring behavior in this phase

## Verification

```bash
cd claude-blog
grep -n "voz.vn\|tinhte.vn\|webtretho" skills/blog-discourse/SKILL.md
grep -rn "tiếng Việt\|Vietnamese" skills/blog-write/SKILL.md skills/blog-brief/SKILL.md
test -f docs/VIETNAMESE.md && echo "docs present"
../.venv/bin/python -m pytest tests/ -q
../.venv/bin/python scripts/lint_prose.py .          # prose hygiene, CI-enforced
```

`lint_prose.py` matters here: this phase edits many Markdown files, and the repository
enforces character hygiene (no em-dashes, no en-dashes, no spaced double-hyphens) in CI.

## Commit

```
docs(vi): add Vietnamese discourse sources and language documentation

blog-discourse composes site:-scoped searches across nine platforms, all
Western, so Vietnamese topics returned almost nothing from the cheapest
research path in the repository -- it needs no API key at all.

- 6 Vietnamese platforms added (Voz, Tinh te, Webtretho, OtoFun,
  Spiderum, VnExpress) with a rule to weight them for Vietnamese topics
- Facebook groups named as a known coverage gap: not indexed, not
  reachable by site:
- Quotes are preserved in their original language
- docs/VIETNAMESE.md: what is supported, quick start, what differs from
  English, known limitations, reference tables
- Vietnamese examples added to blog-write, blog-brief, blog-outline,
  blog-cluster
- Image guidance: no image model renders Vietnamese diacritics
  correctly; overlay text with HTML/CSS instead
- Vietnamese-market trust signals documented for E-E-A-T (MST, Bo Cong
  Thuong, Nghi dinh 13/2023, address plus hotline) as writer guidance,
  not as scored rules

No scoring behavior changes in this commit.
```
