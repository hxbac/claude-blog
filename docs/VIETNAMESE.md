# Vietnamese Language Support

claude-blog can write, score, slug, and lint Vietnamese blog content. This page
covers what that support does and does not include. Written in English (this
repository's documentation language); the worked examples inside it are
genuine Vietnamese, not translations of an English original.

## 1. What is supported

Setting `lang: "vi"` in a post's frontmatter routes it through the Vietnamese
profile end to end. Language is also auto-detected from body text (see
`_detect_language` in `scripts/analyze_blog.py`) when the field is absent or
unrecognized, so an undeclared Vietnamese post still scores correctly.

| Behavior | What happens | Code |
|---|---|---|
| Quality profile | Vietnamese-specific summary labels, about/contact patterns, first-person and methodology detection, entity-definition and editorial patterns | `scripts/vi_profile.py` (`VI_PROFILE`), registered as `LANGUAGE_PROFILES['vi']` in `scripts/analyze_blog.py` |
| Slug generation | Transliterates diacritics (`đ` -> `d`, tone marks stripped) to an ASCII, hyphenated slug | `vi_text.slugify()` in `scripts/vi_text.py`, wired into `scripts/blog_render.py` and `scripts/blog_hygiene.py` |
| Readability model | `vi_syllable`: a syllable-count heuristic (Vietnamese is monosyllabic per whitespace token), not Flesch | `analyze_readability()` in `scripts/analyze_blog.py`, syllable counting in `vi_text.count_syllables()` |
| Prose linter | Detects formulaic AI-writing openers/connectives and register drift. Owns no list of its own: tells come from `vi_profile.py`, register from `vi_register.py` | `scripts/vi_prose.py` |
| Register (xưng hô) | The one register checker. Ignores frontmatter, code, quotes and bare `anh`/`chị`; drift only when a minority register holds at least `max(15% of marked sentences, 3 sentences)` | `scripts/vi_register.py` |
| Lexical tells | One list (`VI_TELLS`) read by `vi_prose.py`, `analyze_blog.py`, `ai_structure.py`; claude-seo's `content_humanize.py --lang vi` uses a generated copy (`python3 scripts/sync_vi_tells.py --write`, verified by a test in both repositories) | `scripts/vi_profile.py`, `scripts/sync_vi_tells.py` |
| Structural tells | `ai_structure.py` runs inside `analyze_blog.py` (key `ai_structure`), language read from the frontmatter | `scripts/ai_structure.py` |
| Draft-mode score | `analyze_blog.py --mode draft` (default for `.md`): prose rubric out of 100, site-level items in a pre-publish checklist and outside the denominator. Gate 4 = draft score at least 85 and zero P0 | `scripts/draft_rubric.py` |

## 2. Quick start

Write, score, and lint a Vietnamese post in three commands:

```bash
# 1. Write the post. During Phase 5a frontmatter, set lang: "vi".
/blog write "cách tiết kiệm điện mùa hè cho gia đình"

# 2. Score it. The vi profile is auto-selected from frontmatter lang: vi, and a
#    .md file is scored with the draft rubric (--mode draft is the default).
python3 scripts/analyze_blog.py bai-viet.md

# 3. Check prose hygiene: AI-writing tells and register drift.
python3 scripts/vi_prose.py bai-viet.md
```

`/blog write` has no `--lang` flag; language is a frontmatter field the writer
sets, not a CLI argument. See `skills/blog-write/SKILL.md` Phase 5a.

## 3. What is different from English

- **Flesch does not apply.** Flesch Reading Ease is calibrated on English
  syllable-per-word statistics that are meaningless for a monosyllabic
  language. Vietnamese posts get a sentence-length heuristic instead
  (`vi_syllable` model, see section 1).
- **`đ` needs special handling.** It has no Unicode decomposition that
  separates the stroke from the letter, so a naive NFKD-then-ASCII-encode
  silently drops it. `vi_text.py`'s `_UNDECOMPOSABLE` map handles it (and a
  few other non-decomposable Latin letters) explicitly.
- **Register consistency is enforced.** Vietnamese second-person address
  encodes social distance (`bạn`/`mình` peer-informal vs. `quý khách`/`quý
  vị` formal-commercial vs. `anh/chị` polite-sales). Mixing sets in one
  document reads as careless or machine-assembled; `scripts/vi_register.py`
  flags it, `scripts/vi_prose.py` reuses it, and drift above the ratio rule is
  a P0 at Gate 4.
- **Labs data is country-level only.** DataForSEO Labs covers Vietnam at the
  country level (`location_code=2704`); province/city-level data (Hanoi,
  Ho Chi Minh City, Da Nang) requires the SERP API instead. See the "Default
  market" section of this repository's `CLAUDE.md`.

## 4. Known limitations

- **No Vietnamese CMS integration.** Output is generic Markdown/HTML; there
  is no purpose-built connector for a Vietnamese-market CMS or publishing
  platform.
- **Stock photo libraries are thin on Vietnamese imagery.** Unsplash, Pexels,
  Pixabay and Openverse have little coverage of Vietnamese people, streets,
  products, or signage. See `skills/blog-image/SKILL.md`, "Vietnamese-Market
  Image Guidance."
- **AI image generation cannot render Vietnamese diacritics correctly.**
  Every current image model gets tone marks, vowel placement, or `đ` wrong.
  Generate images without text and overlay Vietnamese text with HTML/CSS
  instead. Same reference as above.
- **Google Cloud Natural Language entity extraction is weaker for
  Vietnamese than English.** The API supports Vietnamese, but as with most
  non-English languages, confidence and entity coverage are lower than for
  English text. Treat its Vietnamese output as a starting point to verify,
  not a final answer.

## 5. Reference tables

- **Vietnamese location codes**: country `2704`, Hanoi `1028580`, Ho Chi
  Minh City `1028581`, Da Nang `1028809`. Full context in this repository's
  `CLAUDE.md`, "Default market" section.
- **Register sets** (second-person address, do not mix within one document):
  peer (`bạn`, `các bạn`, `mình`, `chúng mình`), polite (`anh chị`, `các anh
  chị`), formal (`quý khách`, `quý vị`, `quý công ty`, `quý khách hàng`).
  Bare `anh` and `chị` are kinship nouns, not markers. Full list in
  `REGISTER_MARKERS`, `scripts/vi_register.py`.
- **AI-tell list**: formulaic openers and connectives Vietnamese AI-generated
  prose overuses (hollow scene-setting like "trong thời đại số," empty
  transitions, stock closings), scored phrases and triggers, advisory
  phrases, chatbot residue, and the humanizer rewrites. One list:
  `VI_TELLS` in `scripts/vi_profile.py`.
- **Vietnamese discourse platforms**: `skills/blog-discourse/SKILL.md`,
  operator table.
- **Vietnamese-market E-E-A-T trust signals** (MST, Bộ Công Thương, Nghị
  định 13/2023/NĐ-CP, address plus hotline): `skills/blog/references/eeat-signals.md`,
  "Vietnamese-Market Trust Signals."
