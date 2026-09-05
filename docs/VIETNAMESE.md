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
| Prose linter | Detects formulaic AI-writing openers/connectives and inconsistent second-person register (`bạn` vs. `quý khách` vs. `anh/chị` mixed in one document) | `scripts/vi_prose.py` |

## 2. Quick start

Write, score, and lint a Vietnamese post in three commands:

```bash
# 1. Write the post. During Phase 5a frontmatter, set lang: "vi".
/blog write "cách tiết kiệm điện mùa hè cho gia đình"

# 2. Score it. The vi profile is auto-selected from frontmatter lang: vi.
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
  document reads as careless or machine-assembled; `scripts/vi_prose.py`
  flags it. See `REGISTER_SETS` in that file.
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
  `than_mat` (peer/informal: `bạn`, `các bạn`, `mình`), `trang_trong`
  (formal/commercial: `quý khách`, `quý vị`, `quý công ty`), `lich_su`
  (polite/sales: `anh/chị`, `anh chị`, `các anh chị`). Full pattern list in
  `REGISTER_SETS`, `scripts/vi_prose.py`.
- **AI-tell list**: formulaic openers and connectives Vietnamese AI-generated
  prose overuses (hollow scene-setting like "trong thời đại số," empty
  transitions, stock closings). Full pattern list with suggested fixes in
  `AI_TELLS`, `scripts/vi_prose.py`.
- **Vietnamese discourse platforms**: `skills/blog-discourse/SKILL.md`,
  operator table.
- **Vietnamese-market E-E-A-T trust signals** (MST, Bộ Công Thương, Nghị
  định 13/2023/NĐ-CP, address plus hotline): `skills/blog/references/eeat-signals.md`,
  "Vietnamese-Market Trust Signals."
