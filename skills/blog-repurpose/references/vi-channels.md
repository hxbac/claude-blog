# Vietnamese channels: Zalo OA, Facebook, TikTok

Read before writing any of the three. Scaffolds come from
`scripts/repurpose_vi.py`; the writer fills them with content from the post.

```bash
python3 scripts/repurpose_vi.py render --channel facebook --register peer \
  --title "..." --hook "..." --point "..." --point "..." --cta "..." --link URL
python3 scripts/repurpose_vi.py check repurposed/<slug>-facebook.md
```

## Register (xưng hô) comes first

Pick one register for the whole piece and keep it, the same rule as the post.
`peer`: bạn, mình. `polite`: anh chị. `formal`: quý khách. Default to the
register of the source post (`scripts/vi_register.py` reports it). A hook in
`bạn` and a call to action in `quý khách` is a grammatical defect that
Vietnamese readers notice at once. Run `check` on the finished piece; it
reports register drift and AI-writing tells with line numbers.

## AI-writing tells

The scaffolds are written to avoid them. The fields the writer adds must avoid
them too. Read `skills/blog/references/ai-writing-tells-vi.md` first. On
social copy the ones that show most: the "không chỉ ... mà còn" opener, a
one-line closer that repeats the post ("Đó chính là điều quan trọng nhất"),
rhetorical questions stacked three deep, and decorative emoji on every line.

## Facebook

- The hook must sit in the first 125 characters, the part visible before
  "Xem thêm".
- Open with a concrete situation or a source-backed number. "Bạn có biết...?"
  is the weakest opener.
- Link: first comment or end of post. Which one performs better is a
  hypothesis to test, not a rule.
- At most two emoji and three hashtags.

## Zalo OA

- Read on a phone in a chat-like feed: short paragraphs, one idea each,
  greeting line first (`Chào bạn` / `Chào anh chị` / `Kính chào quý khách`).
- Title, cover image and the link to the full post are the three fields that
  matter. Check Zalo OA's current character limits and article format before
  sending; the numbers in the scaffold are editorial targets, not Zalo's
  limits.

## TikTok script outline

- Hook in the first 3 seconds, with the same line as on-screen text.
- 30 to 60 seconds, spoken sentences short enough to say in one breath.
- One beat per point, each with a visual cue.
- Vietnamese captions on; many viewers watch muted.
- Statistics only from the post and only with a source.
