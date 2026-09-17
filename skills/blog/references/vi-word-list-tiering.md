# Vietnamese word list tiering: the bar for the scored lists

`scripts/vi_profile.py` carries three Vietnamese word lists used by
`analyze_blog.py`: `ai_phrases`, `ai_trigger_words`, and `transition_words`,
plus one unscored list, `ai_advisory_phrases`. This note is for whoever next
adds, removes, or translates an entry, so the lists do not rot the way the
original English-only `AI_PHRASES` / `AI_TRIGGER_WORDS` did (Phase G's
finding: they ran on every post, including Vietnamese ones, and Vietnamese
always scored zero because none of the entries were Vietnamese).

## The bar for the scored tiers

An entry in `ai_phrases` or `ai_trigger_words` must be a phrase a careful
Vietnamese writer would rarely choose on purpose. Concretely, ask:

1. Would a competent human writer, editing their own draft, cut this phrase
   as filler, or leave it because it is doing real work in the sentence?
2. Does the phrase read as inflated register, a stock transition into a
   conclusion, or a template opener, rather than a specific claim?
3. Is the phrase specific and multi-word enough that it is unlikely to
   appear in ordinary prose by coincidence?

If the answer to (1) is "cut it" and (2) is "yes," the phrase belongs in a
scored tier. If a phrase is common in ordinary, human-written formal
Vietnamese (news writing, textbooks, official notices) at least as often as
it appears in AI-assisted drafts, it fails the bar even if it sounds a
little stiff. Scoring a merely-common phrase turns the checker into noise a
writer learns to ignore, which defeats the purpose of Phase G.

## The advisory tier

`ai_advisory_phrases` exists for exactly that merely-common case: a phrase
worth surfacing for awareness, but not counted into `trigger_count`,
`per_1k`, or `ai_phrase_count`. `analyze_ai_trigger_words` reports these
under a separate `advisory_found` key. Nothing in the scoring pipeline reads
that key; it is for a human skimming the report, not the score.

Examples of the reasoning, not an exhaustive list:

| Phrase | Tier | Why |
|---|---|---|
| `không thể phủ nhận rằng` | scored (`ai_phrases`) | A stock hedge-into-claim opener; a specific claim rarely needs it. |
| `hy vọng bài viết đã mang đến` | scored (`ai_phrases`) | A template sign-off, not a claim about the content. |
| `vai trò quan trọng` | advisory | True and common in ordinary Vietnamese writing about almost any subject; only the inflated variants (`đóng vai trò vô cùng quan trọng`, `vai trò không thể thay thế`) clear the bar. |
| `đã và đang` | advisory | A normal grammatical construction ("has been and is") used constantly in Vietnamese journalism; not itself a tell. |
| `không chỉ ... mà còn` | excluded entirely | Ordinary correlative grammar ("not only ... but also"), used throughout human Vietnamese writing. The structural version of this pattern (see `humanizer/SKILL.md`'s "Not X but Y") belongs to the structural detector in `scripts/ai_structure.py`, not a lexical list; a fixed lexical entry here would fire on normal sentences constantly. |

## Extending the lists

- Write the phrase with full Vietnamese diacritics. `lint_prose.py` forbids
  the em-dash, en-dash, and ASCII double-hyphen in this repository's source,
  not diacritics; there is no reason to fold them away in data.
- Prefer a phrase over a single word. Vietnamese does not have as clean a
  set of single inflated words as English's `delve` / `tapestry`; most
  Vietnamese AI tells are multi-word constructions, so a short, specific
  phrase (2 to 4 syllables) gives fewer false positives than one word.
- Run it past the three questions above with a native or fluent Vietnamese
  reader before committing. This document records the bar, not a
  certification that every current entry meets it perfectly; if a working
  writer flags an existing entry as too common, move it to the advisory
  tier rather than deleting the observation entirely.
- Keep English (`en`) and Turkish (`tr`) untouched when editing this file.
  `LANGUAGE_PROFILES['en']` carries the original `AI_PHRASES` /
  `AI_TRIGGER_WORDS` / `TRANSITION_WORDS` module constants unchanged, so
  English scoring stays byte-identical; `tr` falls back to the same English
  constants it always has, which was already the case before this file
  existed. Neither language's list is what this note is about.

## Where the lists are consumed

- `analyze_ai_signals` reads `ai_phrases` (scored, feeds `ai_phrase_count`,
  advisory-only, not converted into an authorship verdict).
- `analyze_ai_trigger_words` reads `ai_trigger_words` (scored, feeds
  `trigger_count` / `per_1k`) and `ai_advisory_phrases` (reported under
  `advisory_found`, never summed into the scored fields).
- `analyze_transition_words` reads `transition_words` (scored, feeds
  `transition_pct`, which does affect the Content Quality grammar
  sub-score when it exceeds 50%).

See `scripts/vi_profile.py` for the current lists and
`scripts/analyze_blog.py`'s `LANGUAGE_PROFILES` dict for how a profile is
selected per post language.
