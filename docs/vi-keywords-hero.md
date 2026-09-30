# Vietnamese keyword research and hero query

## Keyword research

`python3 scripts/vi_keywords.py "<seed>" [--format markdown|json] [--limit N] [--no-volumes]`

- Emits the seed with and without diacritics, Bắc/Nam synonyms from a short
  curated table (only well-known pairs: heo/lợn, ly/cốc, thìa/muỗng,
  ngô/bắp, bát/chén, mũ/nón, dứa/thơm/khóm, lạc/đậu phộng, vừng/mè, quả/trái,
  ô tô/xe hơi, điều hòa/máy lạnh, xà phòng/xà bông, túi/bịch, kính/kiếng,
  dù/ô) and intent variants (là gì, cách, giá, review, có tốt không, nên mua,
  top 10, so sánh, ở đâu).
- Volumes come from `dataforseo_labs.py search-volume` at location 2704,
  language `vi`, through the rotating key wrapper. One live request, about
  $0.01 plus $0.0001 per keyword; `--limit` (default 40, ceiling 200) caps
  what is sent. Variants past the cap show `n/a`.
- Without a DataForSEO key the table still prints, volumes read `n/a` and a
  Vietnamese one-line note says so. Nothing secret is ever printed.
- A seed typed without accents cannot be turned back into accents reliably
  (ma / má / mà / mả / mã / mạ), so give the seed with diacritics.
- Seeds with no regional word (for example "mỹ phẩm") correctly get no
  Bắc/Nam rows; the table does not invent synonyms.

## Hero query for Vietnamese posts

Stock APIs index English tags. Before `generate_hero.py`, translate the topic
yourself (no API) into 2 to 4 concrete English words and pass it:

```
python3 scripts/generate_hero.py --topic "máy pha cà phê" --query "coffee machine" --out blog-results/<slug>/
```

`--query` replaces topic plus tags as the search text for Unsplash, Pexels,
Pixabay and Openverse. Gemini still receives `--topic` as written.

## Pixabay with a Vietnamese query

Not tested: no `PIXABAY_API_KEY` was configured when Phase L was built
(`python3 scripts/env_file.py --check` showed 0 slots). Until someone runs it,
treat Vietnamese queries on Pixabay as unproven and use the English `--query`.
