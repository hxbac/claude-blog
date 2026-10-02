#!/usr/bin/env python3
"""Internal and product links inside the writing pipeline (Phase Q).

Reads the site inventory (``site_inventory.py``) and turns it into real links
in a Vietnamese draft. Nothing here touches the live site.

Usage:
    python3 scripts/internal_links.py candidates --topic "..." [--site d] [--top 25] [--json]
    python3 scripts/internal_links.py products --query "balo nam" [--site d] [--top N] [--in-stock] [--price-min X --price-max Y] [--json]
    python3 scripts/internal_links.py suggest  --draft blog-results/<slug>/ [--site d] [--plan-out f] [--json]
    python3 scripts/internal_links.py apply    --draft blog-results/<slug>/ [--site d] [--plan f] [--dry-run]
    python3 scripts/internal_links.py reverse  --draft blog-results/<slug>/ [--site d] [--top 8] [--json]

``candidates`` runs BEFORE drafting. It returns the only URLs the writer may
link to, and a ``duplicates`` list: live posts whose title, h1 or focus keyword
overlap the topic. Overlap is a recall-weighted F-score (beta 2) of the
diacritic-stripped content words (stopwords, years, the brand and filler such as
"cach" and "la gi" removed; see ``dup_score``); a post is flagged at
``DUP_THRESHOLD`` (0.7) and above.

``suggest`` scores every body paragraph against the inventory (IDF-weighted
overlap of diacritic-stripped syllable unigrams and bigrams; field weights
focus_keyword 3, anchors 3, title and h1 2, description 1; times priority) and,
for each target, finds an anchor: a 2 to 6 word span that exists in the
paragraph and matches the target's keyword, anchor or title phrases
diacritic-insensitively. Insertion uses the paragraph's own spelling.

``apply`` inserts the links of a plan and resolves ``[INTERNAL-LINK: ...]``
placeholders the plan names. It refuses an anchor that does not occur exactly
once in its paragraph, sits in a heading, code, quote, table, image alt or an
existing link, and anything that breaks the policy below.

Search Console (Phase U, optional): when ``site_inventory.py gsc-sync`` has filled
``gsc_*``, a row ranked at positions 5 to 20 with 10+ impressions is a striking
distance target and its link weight is multiplied by ``STRIKING_BOOST`` (1.25),
never above the weight of a hand-set priority of 5. Its ``gsc_top_query`` is also
an anchor candidate, but only where a paragraph contains that exact text (the
anchor rules above still apply). Without ``gsc_*`` data nothing changes.

Policy (shared by ``suggest``, ``apply`` and the Gate 5 / rubric summary):

* Density by word count (skills/blog/references/internal-linking.md):
  under 1,000 words 3-5; 1,000-2,000 5-7; 2,000-3,000 7-10; 3,000+ 8-12.
  ``suggest`` aims at the middle of the band.
* One link per target URL; at most one link per paragraph.
* Never link the post to itself; skip ``exclude=yes`` and ``type=gone``.
* No product link inside the first sentence of the introduction.
* Products are at most 40% of the internal links, unless the post is a buying
  guide. A buying guide is a post whose frontmatter ``content_type``, ``type``
  or ``template`` is buying-guide, product-review, comparison or roundup, or
  whose title says so ("cach chon", "huong dan mua", "kinh nghiem mua",
  "nen mua", "tot nhat", "top N", "review", "so sanh", "best", "buying guide").
* Exact-match anchors (equal to the focus keyword or a listed anchor) are at
  most 1 in 10 links, and never fewer than one allowed.

Standard library only. Messages are Vietnamese.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import tempfile
import urllib.parse
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from site_inventory import (  # noqa: E402
    InventoryError, find_site_for_host, host_key, idf_table, list_sites,
    load_inventory, load_site_config, norm_url, resolve_site, row_weights,
    search, short_name, sites_root, tokenize,
)
from vi_text import normalize, to_ascii  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DUP_THRESHOLD = 0.7
#: Recall weight of the duplicate score: how much of the new topic an old title
#: covers matters more than how much extra the old title says (SEO titles carry
#: a long tail such as "... nền tảng Self-Hosted PaaS").
DUP_BETA = 2.0
PRODUCT_SHARE_MAX = 0.4
MIN_SPAN_WORDS, MAX_SPAN_WORDS = 2, 6
#: Thresholds are multiples of ``Site.rare``, the IDF of a word that occurs in a
#: single row, so they mean the same on a 30-page site and a 3,000-page one.
#: Minimum IDF mass of an anchor's words inside the target row. Keeps generic
#: spans ("mau den", "cho ban") from becoming anchors.
MIN_ANCHOR_X = 0.9
#: Minimum paragraph-to-target relevance (same units as the search score).
MIN_PARA_X = 1.2
#: Relevance that must remain once the anchor's own words are taken out of the
#: paragraph. An anchor in an unrelated paragraph ("bat dau" in a closing line)
#: has none, which is how a coincidental phrase is told from a real topic match.
MIN_CONTEXT_X = 1.2

#: (upper word bound exclusive, min, max). The last row is the pillar band.
DENSITY_BANDS = ((1000, 3, 5), (2000, 5, 7), (3000, 7, 10), (10 ** 9, 8, 12))

BUYING_TYPES = {"buying-guide", "buying_guide", "product-review", "comparison", "roundup"}
_BUYING_TITLE = re.compile(
    r"\b(cach chon|huong dan chon|huong dan mua|kinh nghiem (?:chon|mua)|nen mua|mua gi|"
    r"mua o dau|tot nhat|top \d+|review|danh gia|so sanh|buying guide|best)\b")

#: Function words, in their own spelling. Folded forms collide with content words
#: ("da" is both "đã" and "da" leather, "den" is "đến" and "đen" black), so a word is
#: judged by its original spelling; only text written without any diacritics falls
#: back to the short list of folded forms that are never content words.
STOP_VI = frozenset(
    "và của là có cho các những một được với trong khi này đó thì mà không nên cũng như hay "
    "tại từ về theo đã sẽ nếu để ra vào lên xuống đến rồi rất quá hơn bị bởi nào gì sao đâu ai "
    "thế kia lại vẫn còn cả mỗi mọi người cần phải nhé ạ ơi".split())
STOP_PLAIN = frozenset("va cua nhung mot cac duoc voi nay thi khong nhu trong cho la co".split())
#: Extra words dropped when comparing a topic with an existing title (original spelling).
DUP_FILLER = frozenset("cách hướng dẫn là gì tốt nhất top mới review".split())
DUP_FILLER_PLAIN = frozenset("cach huong dan la gi tot nhat top moi review".split())


def is_stop(word: str) -> bool:
    w = normalize(word).lower()
    return w in STOP_VI or (w == fold(w) and w in STOP_PLAIN)

_WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)
_PLACEHOLDER_RE = re.compile(r"\[INTERNAL-LINK:\s*([^\]]*?)\s*\]")
_LINK_RE = re.compile(r"(?<!!)\[([^\]]+)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_MASK_RES = (
    re.compile(r"!\[[^\]]*\]\([^)]*\)"),            # image (alt text included)
    re.compile(r"\[[^\]]*\]\([^)]*\)"),             # inline link
    re.compile(r"\[[^\]]+\]\[[^\]]*\]"),            # reference link
    re.compile(r"\[INTERNAL-LINK:[^\]]*\]"),         # placeholder
    re.compile(r"`[^`\n]*`"),                       # inline code
    re.compile(r"<[^>\n]+>"),                       # autolink or html tag
    re.compile(r"https?://\S+|www\.\S+"),            # bare url
)
_FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
_LIST_RE = re.compile(r"^\s{0,3}(?:[-*+]|\d{1,3}[.)])\s+")
_SENT_END = re.compile(r"[.!?…]+(?=\s)")


def fold(text: str) -> str:
    return to_ascii(normalize(text or "")).lower()


def fold_words(text: str) -> list:
    return [fold(w) for w in _WORD_RE.findall(normalize(text or ""))]


#: Folded function words that glue a phrase together. An extra word of this kind
#: never counts as a natural lead-in to a listed anchor.
_STOP_FOLDED_RISKY = frozenset(fold(w) for w in STOP_VI)


def _msg_site_missing() -> str:
    return "Chưa có web nào được cấu hình trong sites/. Chạy: python3 scripts/site_inventory.py init <địa chỉ web>"


# ---------------------------------------------------------------------------
# Draft parsing
# ---------------------------------------------------------------------------

def find_draft_md(draft: str) -> Path:
    p = Path(draft)
    if p.is_file():
        if p.is_symlink():
            raise InventoryError("File bài là liên kết tượng trưng (symlink), không sửa.")
        return p
    if not p.is_dir():
        raise InventoryError(f"Không thấy bài: {draft}")
    mds = sorted(x for x in p.glob("*.md")
                 if x.is_file() and not x.is_symlink() and x.name.lower() not in ("review.md", "readme.md"))
    if not mds:
        raise InventoryError(f"Không có file .md của bài trong {draft}")
    if len(mds) > 1:
        named = [x for x in mds if x.stem == p.resolve().name]
        if len(named) != 1:
            raise InventoryError(f"Có nhiều file .md trong {draft}; chỉ rõ file bằng --draft <file.md>")
        return named[0]
    return mds[0]


def parse_frontmatter(text: str) -> tuple:
    """Flat ``key: value`` frontmatter. Returns (dict, offset where the body starts)."""
    m = re.match(r"^﻿?---[ \t]*\n(.*?)\n---[ \t]*(?:\n|$)", text, re.DOTALL)
    if not m:
        return {}, 0
    fm: dict = {}
    for line in m.group(1).split("\n"):
        if ":" in line and not line.startswith((" ", "\t", "#", "-")):
            key, _, value = line.partition(":")
            value = value.strip()
            if len(value) > 1 and value[0] in "\"'" and value[-1] == value[0]:
                value = value[1:-1]
            fm[key.strip()] = value
    return fm, m.end()


def frontmatter_list(text: str, key: str) -> list:
    """Values of a list key in the frontmatter, block form (``key:`` then ``- item``
    lines, indented or not) or inline form (``key: [a, b]``). Quotes are removed."""
    m = re.match(r"^﻿?---[ \t]*\n(.*?)\n---[ \t]*(?:\n|$)", text, re.DOTALL)
    if not m:
        return []
    out: list = []
    inside = False
    for line in m.group(1).split("\n"):
        stripped = line.strip()
        if not inside:
            head, sep, rest = line.partition(":")
            if sep and head.strip() == key and not line.startswith((" ", "\t")):
                rest = rest.strip()
                if rest.startswith("["):
                    return [v.strip().strip("\"'") for v in rest.strip("[]").split(",") if v.strip().strip("\"'")]
                if rest:
                    return [rest.strip("\"'")]
                inside = True
            continue
        if stripped.startswith("- "):
            val = stripped[2:].strip().strip("\"'")
            if val:
                out.append(val)
        elif stripped and not stripped.startswith("#"):
            break
    return out


def is_roundup(fm: dict) -> bool:
    return fold(fm.get("content_type", "")).strip() == "roundup"


def listed_products(text: str, fm: dict) -> list:
    """Product URLs a roundup lists (frontmatter ``products:``), in order; an empty
    list for any other post, whatever else the frontmatter holds."""
    return frontmatter_list(text, "products") if is_roundup(fm) else []


@dataclass
class Block:
    index: int
    start: int          # offset in the whole file text
    end: int
    kind: str           # paragraph|list|heading|code|quote|table|html|image|faq|other
    text: str
    line: int           # 1-based line of the first line

    @property
    def eligible(self) -> bool:
        return self.kind in ("paragraph", "list")


def _classify(lines: list) -> str:
    first = lines[0].strip()
    if first.startswith("#"):
        return "heading"
    if len(lines) >= 2 and re.fullmatch(r"=+|-+", lines[1].strip() or "x") and len(first) > 0:
        return "heading"                                    # setext
    if re.fullmatch(r"(-\s*){3,}|(\*\s*){3,}|(_\s*){3,}", first):
        return "other"
    if lines[0].startswith(("    ", "\t")) and not _LIST_RE.match(lines[0]):
        return "code"
    if first.startswith(">"):
        return "quote"
    if first.startswith("|") or (len(lines) > 1 and re.fullmatch(r"\|?[\s:|-]+\|[\s:|-]*", lines[1].strip() or "x")):
        return "table"
    if first.startswith("<") or first.startswith("{{") or first.startswith("{%"):
        return "html"
    if re.match(r"^\[\^?[^\]]+\]:\s", first):
        return "other"
    if re.fullmatch(r"!\[[^\]]*\]\([^)]*\)(\{[^}]*\})?", first) and len(lines) == 1:
        return "image"
    if re.fullmatch(r"\*\*[^*]+\?\*\*|__[^_]+\?__", first) and len(lines) == 1:
        return "faq"
    if re.match(r"^(\*\*)?(q|hỏi|câu hỏi)\s*[:.]", first, re.IGNORECASE) and first.rstrip("*").endswith("?"):
        return "faq"
    if _LIST_RE.match(lines[0]):
        return "list"
    return "paragraph"


def parse_blocks(text: str, body_start: int = 0) -> list:
    """Split the body into blocks separated by blank lines. Fenced code is one
    block; a heading line is always its own block."""
    blocks: list = []
    cur: list = []          # (offset, line)
    fence: Optional[str] = None
    pos = body_start
    line_no = text.count("\n", 0, body_start) + 1
    cur_line_no = line_no

    def flush():
        nonlocal cur
        if not cur:
            return
        lines = [l for _, l in cur]
        start = cur[0][0]
        raw = "".join(lines)
        kind = "code" if fence_block else _classify([l.rstrip("\n") for l in lines])
        blocks.append(Block(len(blocks), start, start + len(raw.rstrip("\n")), kind,
                            raw.rstrip("\n"), cur_line_no))
        cur = []

    fence_block = False
    for line in text[body_start:].splitlines(keepends=True):
        m = _FENCE_RE.match(line)
        if fence is None and m:
            flush()
            fence, fence_block = m.group(1)[0] * 3, True
            cur_line_no = line_no
            cur.append((pos, line))
        elif fence is not None:
            cur.append((pos, line))
            if m and m.group(1)[0] == fence[0] and line.strip().strip(fence[0]) == "":
                flush()
                fence, fence_block = None, False
        elif not line.strip():
            flush()
        else:
            if not cur:
                cur_line_no = line_no
            if line.lstrip().startswith("#") and re.match(r"^\s{0,3}#{1,6}(\s|$)", line):
                flush()
                cur_line_no = line_no
                cur.append((pos, line))
                flush()
            else:
                cur.append((pos, line))
        pos += len(line)
        line_no += 1
    if fence is not None:
        flush()
    else:
        flush()
    return blocks


def body_word_count(blocks: list) -> int:
    return sum(len(_WORD_RE.findall(b.text)) for b in blocks if b.kind not in ("code", "html", "other"))


def is_buying_guide(fm: dict) -> bool:
    for key in ("content_type", "type", "template"):
        if fold(fm.get(key, "")).replace(" ", "-") in BUYING_TYPES:
            return True
    return bool(_BUYING_TITLE.search(fold(fm.get("title", ""))))


def density_band(words: int) -> tuple:
    """(min, max, target) internal links for a post of ``words`` words."""
    for bound, lo, hi in DENSITY_BANDS:
        if words < bound:
            return lo, hi, (lo + hi) // 2
    return DENSITY_BANDS[-1][1:] + ((DENSITY_BANDS[-1][1] + DENSITY_BANDS[-1][2]) // 2,)


def max_exact(total: int) -> int:
    return max(1, total // 10)


def _masked(text: str) -> list:
    spans = []
    for rx in _MASK_RES:
        spans.extend((m.start(), m.end()) for m in rx.finditer(text))
    return spans


def _overlaps(a0: int, a1: int, spans: list) -> bool:
    return any(a0 < e and s < a1 for s, e in spans)


# ---------------------------------------------------------------------------
# Site context
# ---------------------------------------------------------------------------

@dataclass
class Site:
    dir: Path
    cfg: dict
    rows: list
    by_url: dict = field(default_factory=dict)
    index: dict = field(default_factory=dict)
    docs: list = field(default_factory=list)
    idf: dict = field(default_factory=dict)
    brand_tokens: frozenset = frozenset()
    host: str = ""

    @property
    def rare(self) -> float:
        """IDF of a word found in exactly one row (the scale of every threshold)."""
        return math.log(1 + (max(len(self.rows), 1) - 0.5) / 1.5)

    @property
    def name(self) -> str:
        return self.dir.name


def load_site(site_dir: Path) -> Site:
    cfg = load_site_config(site_dir)
    rows = load_inventory(site_dir)
    site = Site(dir=site_dir, cfg=cfg, rows=rows)
    for i, r in enumerate(rows):
        site.by_url.setdefault(norm_url(r["url"]), r)
        site.index.setdefault(norm_url(r["url"]), i)
    site.docs = [row_weights(r) for r in rows]
    site.idf = idf_table(site.docs)
    host = urllib.parse.urlparse(cfg.get("base_url", "")).hostname or site_dir.name
    site.host = host_key(host)
    brand = " ".join([cfg.get("brand", ""), site.host.split(".")[0]])
    site.brand_tokens = frozenset(w for w in fold_words(brand) if w)
    return site


def site_for_canonical(canonical: str, root: Optional[Path] = None) -> Optional[Path]:
    """Folder of the configured site whose host equals the canonical's host."""
    host = urllib.parse.urlparse(canonical or "").hostname or ""
    if not host:
        return None
    try:
        return find_site_for_host(host, root)
    except Exception:
        return None


def row_eligible(row: dict) -> Optional[str]:
    """None when the row may be a link target, else the Vietnamese reason."""
    if row.get("type") == "gone":
        return "trang đã gỡ khỏi web (type=gone)"
    if (row.get("exclude") or "").strip().lower() in ("yes", "y", "true", "1", "x"):
        return "đã đánh dấu exclude trong inventory.csv"
    return None


def _priority(row: dict) -> float:
    try:
        p = int(float(row.get("priority") or 3))
    except ValueError:
        p = 3
    return max(1, min(5, p)) / 3.0


#: Striking distance (Phase U). A row that Search Console ranks between
#: positions 5 and 20 with at least ``STRIKING_MIN_IMPRESSIONS`` impressions is a
#: better link target: a few internal links can push it onto page one. Its link
#: weight is multiplied by ``STRIKING_BOOST`` (1.25), but never beyond the weight of
#: a hand-set priority of 5 (5/3), so the marketer's own priority still wins.
#: Rows without ``gsc_*`` data get exactly 1.0, so ranking is unchanged.
STRIKING_BOOST = 1.25
STRIKING_MIN_POS, STRIKING_MAX_POS = 5.0, 20.0
STRIKING_MIN_IMPRESSIONS = 10


def is_striking(row: dict) -> bool:
    try:
        pos = float(row.get("gsc_position") or 0)
        imp = float(row.get("gsc_impressions") or 0)
    except (TypeError, ValueError):
        return False
    return STRIKING_MIN_POS <= pos <= STRIKING_MAX_POS and imp >= STRIKING_MIN_IMPRESSIONS


def striking_boost(row: dict) -> float:
    """Multiplier for a link target: 1.0 unless the row is in striking distance."""
    if not is_striking(row):
        return 1.0
    return max(1.0, min(STRIKING_BOOST, (5 / 3) / _priority(row)))


def is_self(row_or_url, canonical: str, slug: str = "") -> bool:
    url = row_or_url["url"] if isinstance(row_or_url, dict) else row_or_url
    if canonical and norm_url(url) == norm_url(canonical):
        return True
    if slug and urllib.parse.urlparse(url).path.rstrip("/").rsplit("/", 1)[-1] == slug and not canonical:
        return True
    return False


# ---------------------------------------------------------------------------
# Anchor forms
# ---------------------------------------------------------------------------

_CHUNK_SPLIT = re.compile(r"\s[\u2013\u2014|/\-]\s|[,:;()?!\[\]\"\u201c\u201d\u2026]")


def title_chunks(title: str, brand_tokens: frozenset) -> list:
    """Phrases of a title with separators, punctuation and the brand removed.
    Each chunk is a list of (folded word, original word)."""
    out = []
    for chunk in _CHUNK_SPLIT.split(normalize(title or "")):
        words = _WORD_RE.findall(chunk)
        pairs = [(fold(w), w) for w in words]
        if not pairs or all(f in brand_tokens or f in ("vn", "com") for f, _ in pairs):
            continue
        out.append(pairs)
    return out


class RowForms:
    """Anchor phrases one target accepts, in folded-token form."""

    def __init__(self, row: dict, site: Site):
        self.row = row
        self._rare = site.rare
        self.exact: list = []                # tuples
        self.cover: dict = {}                # tuple -> share of its title chunk it spans
        self.partial: dict = {}              # tuple -> 'partial' | 'branded'
        for key in ("focus_keyword", "anchors"):
            for part in (row.get(key) or "").split("|"):
                t = tuple(fold_words(part))
                if t and t not in self.exact:
                    self.exact.append(t)
        # Search Console's top query for the page: an anchor candidate, but only
        # where a paragraph spells it out (find_candidates checks), 2 to 6 words.
        self.gsc_text = normalize(row.get("gsc_top_query") or "").strip().lower()
        gt = tuple(fold_words(self.gsc_text))
        self.gsc = gt if MIN_SPAN_WORDS <= len(gt) <= MAX_SPAN_WORDS and gt not in self.exact else ()
        i = site.index.get(norm_url(row["url"]))
        weights = site.docs[i] if i is not None else row_weights(row)
        self._weights = weights
        self.hints: list = []
        seen: set = set()
        for field_name in ("title", "h1"):
            for pairs in title_chunks(row.get(field_name, ""), site.brand_tokens):
                toks = [f for f, _ in pairs]
                for n in range(MIN_SPAN_WORDS, min(MAX_SPAN_WORDS, len(toks)) + 1):
                    for i in range(len(toks) - n + 1):
                        t = tuple(toks[i:i + n])
                        if t in seen:
                            continue
                        seen.add(t)
                        kind = "branded" if any(w in site.brand_tokens for w in t) else "partial"
                        self.partial[t] = kind
                        self.cover[t] = max(self.cover.get(t, 0.0), n / len(toks))
                        orig = " ".join(w for _, w in pairs[i:i + n])
                        o_t = tuple(w for _, w in pairs[i:i + n])
                        self.hints.append((anchor_quality(t, weights, site.idf, o_t), orig, o_t))
        for t in self.exact:
            for n in range(MIN_SPAN_WORDS, min(MAX_SPAN_WORDS, len(t)) + 1):
                for i in range(len(t) - n + 1):
                    self.partial.setdefault(t[i:i + n], "partial")

    def match(self, span: tuple) -> Optional[str]:
        if span in self.exact:
            return "exact"
        for f in self.exact:
            if len(f) >= MIN_SPAN_WORDS and len(span) > len(f) and _contains(span, f):
                # a natural lead-in ("chọn ví da nam"), not words that are only glue
                i = next(k for k in range(len(span)) if span[k:k + len(f)] == f)
                extras = span[:i] + span[i + len(f):]
                if len(extras) <= 2 and not any(w in STOP_PLAIN or w in _STOP_FOLDED_RISKY for w in extras):
                    return "partial"
        kind = self.partial.get(span)
        if kind is None and self.gsc and span == self.gsc:
            return "gsc"
        return kind

    def anchor_hints(self, n: int = 3) -> list:
        """Phrases a writer can use as a natural anchor, best first."""
        out = []
        for t in self.exact:
            if MIN_SPAN_WORDS <= len(t) <= MAX_SPAN_WORDS:
                out.append(" ".join(t))
        orig_by_fold: dict = {}
        for q, orig, t in sorted(self.hints, key=lambda x: -(x[0] - 1.5 * max(0, len(x[2]) - 3))):
            if q < MIN_ANCHOR_X * self._rare or not _valid_edges(t) or any(any(c.isdigit() for c in w) for w in t):
                continue
            ft = set(fold_words(orig))
            if not any(ft <= set(fold_words(o)) or set(fold_words(o)) <= ft for o in out):
                out.append(" ".join(w if w.isupper() else w.lower() for w in orig.split())
                           if all(w[:1].isupper() for w in orig.split()) else orig)
            if len(out) >= n:
                break
        # explicit forms were stored folded; show the original spelling
        shown = []
        for o in out[:n]:
            shown.append(o)
        return self._respell(shown)

    def _respell(self, phrases: list) -> list:
        res = []
        raw_forms = [(self.row.get("focus_keyword") or "")] + (self.row.get("anchors") or "").split("|")
        for p in phrases:
            for raw in raw_forms:
                if raw.strip() and fold(raw).split() == p.split():
                    p = raw.strip()
                    break
            res.append(p)
        return res


def _contains(big: tuple, small: tuple) -> bool:
    n = len(small)
    return any(big[i:i + n] == small for i in range(len(big) - n + 1))


def anchor_quality(span: tuple, weights: dict, idf: dict, orig: Optional[tuple] = None) -> float:
    orig = orig or span
    return round(sum(idf.get(t, 0.0) for t, o in zip(span, orig) if t in weights and not is_stop(o)), 4)


def _valid_edges(orig: tuple) -> bool:
    """An anchor never starts or ends with a function word and has a real word."""
    if is_stop(orig[0]) or is_stop(orig[-1]):
        return False
    return any(not w.isdigit() and not is_stop(w) for w in orig)


# ---------------------------------------------------------------------------
# Spans inside a paragraph
# ---------------------------------------------------------------------------

@dataclass
class Span:
    start: int          # offset inside the block text
    end: int
    words: tuple        # folded
    text: str           # original spelling
    orig: tuple = ()    # original words


def block_words(text: str) -> list:
    return [(m.start(), m.end(), fold(m.group(0)), m.group(0)) for m in _WORD_RE.finditer(text)]


def iter_spans(text: str, masks: Optional[list] = None):
    """Every 2 to 6 word span joined by single spaces and clear of masked text."""
    masks = _masked(text) if masks is None else masks
    words = block_words(text)
    for i in range(len(words)):
        for n in range(MIN_SPAN_WORDS, MAX_SPAN_WORDS + 1):
            j = i + n - 1
            if j >= len(words):
                break
            if text[words[j - 1][1]:words[j][0]] != " ":
                break
            s, e = words[i][0], words[j][1]
            if _overlaps(s, e, masks):
                continue
            yield Span(s, e, tuple(w[2] for w in words[i:j + 1]), text[s:e],
                       tuple(w[3] for w in words[i:j + 1]))


def find_occurrences(text: str, anchor: str) -> list:
    """Offsets (start, end) where ``anchor`` occurs as whole words, comparing
    folded words (diacritics and case ignored). Ignores masks."""
    want = fold_words(anchor)
    if not want:
        return []
    words = block_words(text)
    out = []
    n = len(want)
    for i in range(len(words) - n + 1):
        if tuple(w[2] for w in words[i:i + n]) != tuple(want):
            continue
        ok = all(text[words[k - 1][1]:words[k][0]] == " " for k in range(i + 1, i + n))
        if ok:
            out.append((words[i][0], words[i + n - 1][1]))
    return out


def first_sentence_end(text: str) -> int:
    m = _SENT_END.search(text)
    return m.end() if m else len(text)


# ---------------------------------------------------------------------------
# Existing links
# ---------------------------------------------------------------------------

def _resolve(href: str, site: Site) -> Optional[str]:
    """Absolute URL for an internal href, or None when it is external or not a page."""
    href = href.strip()
    if not href or href.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
        return None
    if href.startswith("//"):
        href = "https:" + href
    parsed = urllib.parse.urlparse(href)
    if parsed.scheme in ("http", "https"):
        return href if host_key(parsed.hostname or "") == site.host else None
    if parsed.scheme:
        return None
    return urllib.parse.urljoin(site.cfg.get("base_url", "").rstrip("/") + "/", href)


@dataclass
class Found:
    block: int
    anchor: str
    href: str
    url: str            # resolved absolute url
    row: Optional[dict]
    kind: str           # type of the target row, or "unknown"
    anchor_type: str    # exact | partial | branded | other


def existing_links(blocks: list, site: Site) -> list:
    out = []
    forms_cache: dict = {}
    for b in blocks:
        if b.kind in ("code", "html"):
            continue
        for m in _LINK_RE.finditer(b.text):
            url = _resolve(m.group(2), site)
            if url is None:
                continue
            row = site.by_url.get(norm_url(url))
            atype = "other"
            if row is not None:
                forms = forms_cache.setdefault(row["url"], RowForms(row, site))
                atype = forms.match(tuple(fold_words(m.group(1)))) or "other"
                if tuple(fold_words(m.group(1))) in forms.exact:
                    atype = "exact"
            out.append(Found(b.index, m.group(1), m.group(2), url, row,
                             row.get("type", "other") if row else "unknown", atype))
    return out


def placeholders(blocks: list) -> list:
    out = []
    for b in blocks:
        if b.kind in ("code",):
            continue
        for m in _PLACEHOLDER_RE.finditer(b.text):
            inner = m.group(1)
            parts = re.split(r"\s*(?:→|->|=>)\s*", inner, maxsplit=1)
            anchor = parts[0].strip()
            desc = parts[1].strip() if len(parts) > 1 else ""
            out.append({"block": b.index, "line": b.line + b.text.count("\n", 0, m.start()),
                        "text": m.group(0), "anchor": anchor, "description": desc,
                        "kind": b.kind})
    return out


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------

@dataclass
class Policy:
    """Running totals while links are added to a post."""
    canonical: str
    slug: str
    buying_guide: bool
    lo: int
    hi: int
    target: int
    intro_block: Optional[int]
    intro_end: int
    urls: set = field(default_factory=set)
    variants: set = field(default_factory=set)
    blocks_linked: set = field(default_factory=set)
    total: int = 0
    products: int = 0
    exact: int = 0
    #: Roundup only: normalised URLs of the products the post lists (frontmatter
    #: ``products:``), and the variant keys of those products. Links to them are
    #: the point of the post, so they are outside the density band and the product
    #: share, and ``suggest`` / ``apply`` never add another one.
    listed: frozenset = frozenset()
    listed_variants: frozenset = frozenset()

    def seed(self, found: list) -> None:
        for f in found:
            self.urls.add(norm_url(f.url))
            if f.row is not None and f.row.get("type") == "product":
                self.variants.add(_variant_key(f.row))
            self.blocks_linked.add(f.block)
            if norm_url(f.url) in self.listed:
                continue
            self.total += 1
            self.products += f.kind == "product"
            self.exact += f.anchor_type == "exact"

    def reject_reason(self, row: dict, block: int, anchor_start: int, atype: str) -> Optional[str]:
        why = row_eligible(row)
        if why:
            return why
        if norm_url(row["url"]) in self.listed or (
                row.get("type") == "product" and _variant_key(row) in self.listed_variants):
            return "sản phẩm này nằm trong danh sách top của bài, đã có liên kết ở phần sản phẩm"
        if is_self(row, self.canonical, self.slug):
            return "đây chính là bài đang viết (liên kết tới chính nó)"
        if norm_url(row["url"]) in self.urls:
            return "URL này đã được liên kết trong bài (mỗi URL một lần)"
        if row.get("type") == "product" and _variant_key(row) in self.variants:
            return "bài đã liên kết một màu/biến thể của sản phẩm này (mỗi sản phẩm một lần)"
        if block in self.blocks_linked:
            return "đoạn này đã có một liên kết (mỗi đoạn tối đa một)"
        if self.total + 1 > self.hi:
            return f"bài đã đủ {self.hi} liên kết, mức tối đa theo độ dài"
        if row.get("type") == "product" and block == self.intro_block and anchor_start < self.intro_end:
            return "không đặt liên kết sản phẩm trong câu đầu của phần mở bài"
        return None

    def take(self, row: dict, block: int, atype: str) -> None:
        self.urls.add(norm_url(row["url"]))
        if row.get("type") == "product":
            self.variants.add(_variant_key(row))
        self.blocks_linked.add(block)
        self.total += 1
        self.products += row.get("type") == "product"
        self.exact += atype == "exact"


def aggregate_violations(total: int, products: int, exact: int, buying_guide: bool) -> list:
    out = []
    if not buying_guide and total and products / total > PRODUCT_SHARE_MAX + 1e-9:
        out.append(f"Sản phẩm chiếm {products}/{total} liên kết, quá {int(PRODUCT_SHARE_MAX * 100)}% "
                   "(chỉ bài hướng dẫn mua hàng mới được nhiều hơn).")
    if exact > max_exact(total):
        out.append(f"Có {exact} neo khớp nguyên văn từ khóa trên {total} liên kết "
                   f"(tối đa {max_exact(total)}, tức 1 trên 10).")
    return out


# ---------------------------------------------------------------------------
# Draft context
# ---------------------------------------------------------------------------

@dataclass
class Draft:
    path: Path
    text: str
    fm: dict
    body_start: int
    blocks: list
    words: int
    canonical: str
    slug: str
    buying_guide: bool
    intro_block: Optional[int]
    intro_end: int
    products: list = field(default_factory=list)


def load_draft(path: Path) -> Draft:
    raw = path.read_text(encoding="utf-8")
    text = normalize(raw)
    fm, off = parse_frontmatter(text)
    blocks = parse_blocks(text, off)
    intro = next((b for b in blocks if b.eligible), None)
    return Draft(path=path, text=text, fm=fm, body_start=off, blocks=blocks,
                 words=body_word_count(blocks), canonical=fm.get("canonical", ""),
                 slug=fm.get("slug", ""), buying_guide=is_buying_guide(fm),
                 intro_block=intro.index if intro else None,
                 intro_end=first_sentence_end(intro.text) if intro else 0,
                 products=listed_products(text, fm))


def pick_site(site_arg: Optional[str], canonical: str = "") -> Site:
    root = sites_root()
    if site_arg:
        return load_site(resolve_site(site_arg, root))
    found = site_for_canonical(canonical, root)
    if found:
        return load_site(found)
    return load_site(resolve_site(None, root))


def _write_atomic(path: Path, text: str) -> None:
    if path.is_symlink():
        raise InventoryError("File bài là liên kết tượng trưng (symlink), không sửa.")
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".il-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


# ---------------------------------------------------------------------------
# candidates
# ---------------------------------------------------------------------------

def _variant_key(row: dict) -> str:
    title = fold(row.get("title", ""))
    return re.sub(r"\s+mau\s+.*$", "", title) if row.get("type") == "product" else title


def _unavailable(row: dict) -> bool:
    return row.get("type") == "product" and (row.get("in_stock") or "").strip().lower() in ("no", "false", "0")


def dup_tokens(text: str, site: Site) -> set:
    toks = set()
    for o in _WORD_RE.findall(normalize(text or "")):
        w = fold(o)
        if (is_stop(o) or o.lower() in DUP_FILLER or w in DUP_FILLER_PLAIN and o == w
                or w in site.brand_tokens or w in ("vn", "com") or re.fullmatch(r"(19|20)\d\d", w)):
            continue
        toks.add(w)
    return toks


def dup_score(topic: set, title: set) -> float:
    """Recall-weighted F-score (beta 2) of content words: precision is the share
    of the title that the topic covers, recall the share of the topic that the
    title covers. Identical word sets score 1.0; two shared words out of a
    four-word topic and a seven-word title score about 0.44."""
    shared = len(topic & title)
    if not shared:
        return 0.0
    precision, recall = shared / len(title), shared / len(topic)
    b2 = DUP_BETA ** 2
    return (1 + b2) * precision * recall / (b2 * precision + recall)


def find_duplicates(site: Site, topic: str, threshold: float = DUP_THRESHOLD,
                    canonical: str = "") -> list:
    """Live posts whose title, h1 or focus keyword overlaps the topic."""
    t = dup_tokens(topic, site)
    out = []
    if len(t) < 2:
        return out
    for row in site.rows:
        if row.get("type") != "post" or is_self(row, canonical):
            continue
        best, via = 0.0, ""
        for fld in ("focus_keyword", "title", "h1"):
            # a title is split into chunks so a brand or category suffix does not dilute it
            texts = [row.get(fld, "")]
            if fld != "focus_keyword":
                texts = [" ".join(w for _, w in c) for c in title_chunks(row.get(fld, ""), site.brand_tokens)]
                texts.append(" ".join(texts))
            for s in texts:
                sim = dup_score(t, dup_tokens(s, site))
                if sim > best:
                    best, via = sim, fld
        if best >= threshold:
            out.append({"url": row["url"], "title": row.get("title", ""),
                        "focus_keyword": row.get("focus_keyword", ""),
                        "similarity": round(best, 2), "matched_on": via})
    out.sort(key=lambda d: (-d["similarity"], d["url"]))
    return out[:5]


# ---------------------------------------------------------------------------
# Query understanding and the product picker (Phase T)
# ---------------------------------------------------------------------------
#
# Head noun rule. A Vietnamese noun phrase puts its head first and its
# modifiers after it ("balo nam đi học", "ví da nam", "máy pha cà phê tốt
# nhất"). To find the head of a query:
#   1. drop every token that holds a digit ("top 10", "2026", "No.10"), and
#      the intent phrases and words ("top", "tốt nhất", "giá rẻ", "nên mua",
#      "so sánh", "review", "cách chọn", "đánh giá", ...);
#   2. skip leading function words and classifiers ("các", "những", "chiếc");
#   3. the head is the run of tokens up to the first boundary, at most 4 tokens:
#      an audience word (nam, nữ, bé, trẻ em), a preposition (cho, để, đi, dành,
#      dùng, với, của, ...), a function word, or a quality adjective (đẹp, rẻ,
#      bền, nhẹ, chống, ...). So "ví da" and "máy pha cà phê" keep their
#      second and later syllables, while "balo nam đi học" gives "balo".
# A word is judged by its own spelling when the query carries diacritics ("đi"
# is a preposition, "di" in "di động" is not, "da" leather is not "đa"), and by
# its folded spelling, with a short safe list, when the query has none.
# A product qualifies only when every head token is in its title or category
# (or its URL slug, when the title carries no diacritics). The audience word is
# a soft filter: "nam" drops products marked "nữ" and not "nam", and the reverse.

INTENT_PHRASES = (
    ("tot", "nhat"), ("re", "nhat"), ("hot", "nhat"), ("moi", "nhat"), ("gia", "re"), ("nen", "mua"),
    ("nen", "chon"), ("so", "sanh"), ("danh", "gia"), ("cach", "chon"), ("huong", "dan", "chon"),
    ("huong", "dan", "mua"), ("huong", "dan"), ("kinh", "nghiem", "mua"), ("chat", "luong"), ("uy", "tin"),
    ("chinh", "hang"), ("cao", "cap"), ("ban", "chay"), ("hang", "dau"), ("dang", "mua"), ("dang", "tien"),
    ("goi", "y"), ("de", "xuat"), ("phai", "co"), ("nhieu", "nguoi", "mua"),
)
INTENT_FOLDED = frozenset("top review best mua chon cach nhat loai".split())
#: Classifiers and quantity words that may precede the head ("10 chiếc kính mát").
LEADING_SKIP = frozenset("chiếc cái loại những các mấy vài".split())
LEADING_SKIP_PLAIN = frozenset("chiec cai loai nhung cac".split())  # not "may": máy
#: Words that end the head, in their own spelling (diacritic queries).
HEAD_BOUNDARY = frozenset(
    "nam nữ bé trẻ em trai gái cho để đi dành dùng với của khi tại ở trong và hay hoặc từ "
    "đẹp rẻ tốt bền nhẹ chống siêu xịn mới hot chính hãng thật".split())
#: The subset that is safe to recognise in a query typed without diacritics: the
#: others collide with nouns ("tai nghe", "tu lanh", "dung cu", "cua cuon", "voi sen").
HEAD_BOUNDARY_PLAIN = frozenset("nam nu cho va hay hoac chong sieu xin hot".split())
MAX_HEAD_TOKENS = 4
AUDIENCE = {"nam": "nam", "nữ": "nu", "nu": "nu"}
_NUM_RE = re.compile(r"\d")
_YEAR_RE = re.compile(r"^(?:19|20)\d\d$")


def _has_marks(text: str) -> bool:
    return normalize(text).lower() != fold(text)


def parse_query(query: str) -> dict:
    """Split a topic or search phrase into its head noun and the rest.

    Returns ``head`` (list of original lowercase tokens), ``terms`` (the other
    content tokens), ``audience`` ("nam", "nu" or ""), ``number`` (the N of "top
    N", else None) and ``marks`` (True when the query carries diacritics)."""
    raw = [t.lower() for t in _WORD_RE.findall(normalize(query or ""))]
    marks = any(_has_marks(t) for t in raw)
    number = None
    for i, t in enumerate(raw):
        if t.isdigit() and not _YEAR_RE.match(t) and 0 < int(t) <= 50:
            if (i > 0 and raw[i - 1] == "top") or number is None:
                number = int(t)
    toks = [(t, fold(t)) for t in raw if not _NUM_RE.search(t)]
    # intent phrases first (folded, diacritics do not matter), then single intent words
    out: list = []
    i = 0
    while i < len(toks):
        hit = next((len(ph) for ph in INTENT_PHRASES
                    if tuple(f for _, f in toks[i:i + len(ph)]) == ph), 0)
        if hit:
            i += hit
            continue
        if toks[i][1] not in INTENT_FOLDED:
            out.append(toks[i])
        i += 1
    boundary = HEAD_BOUNDARY if marks else HEAD_BOUNDARY_PLAIN

    def is_boundary(orig: str, fld: str) -> bool:
        return (orig in boundary if marks else fld in boundary) or is_stop(orig)

    k = 0
    while k < len(out) and (out[k][0] in LEADING_SKIP or out[k][0] in LEADING_SKIP_PLAIN
                            or is_stop(out[k][0])):
        k += 1
    head: list = []
    while k < len(out) and len(head) < MAX_HEAD_TOKENS and not is_boundary(*out[k]):
        head.append(out[k][0])
        k += 1
    terms = [o for o, f in out[k:] if not is_stop(o)]
    audience = next((AUDIENCE[t] for t in terms if t in AUDIENCE), "")
    return {"head": head, "terms": terms, "audience": audience, "number": number, "marks": marks}


def _row_tokens(row: dict) -> tuple:
    """(original tokens of title and category, folded set incl. slug, ascii-only?)"""
    text = " ".join([row.get("title", ""), row.get("category", "")])
    orig = [t.lower() for t in _WORD_RE.findall(normalize(text))]
    ascii_only = not any(_has_marks(t) for t in orig)
    slug = [t for t in _WORD_RE.findall(urllib.parse.urlparse(row.get("url", "")).path.lower().replace("-", " "))]
    folded = {fold(t) for t in orig}
    if ascii_only or not row.get("title"):
        folded |= set(slug)
        orig = orig + slug
    return orig, folded, ascii_only


def head_matches(row: dict, info: dict) -> bool:
    """Every head token is in the title or category of ``row`` (slug when the title
    has no diacritics). With a diacritic query, tokens compare in their own spelling
    unless the row is written without diacritics."""
    head = info["head"]
    if not head:
        return True
    orig, folded, ascii_only = _row_tokens(row)
    have = set(orig)
    for t in head:
        if info["marks"] and not ascii_only:
            if t not in have:
                return False
        elif fold(t) not in folded:
            return False
    return True


def _head_contiguous(row: dict, info: dict) -> bool:
    head = [fold(t) for t in info["head"]]
    title = [fold(t) for t in _WORD_RE.findall(normalize(row.get("title", "")))]
    n = len(head)
    return bool(head) and any(title[i:i + n] == head for i in range(len(title) - n + 1))


def audience_conflict(row: dict, audience: str) -> bool:
    """True when the row is marked for the other audience only."""
    if not audience:
        return False
    toks = {fold(t) for t in _WORD_RE.findall(normalize(" ".join([row.get("title", ""), row.get("category", "")])))}
    other = "nu" if audience == "nam" else "nam"
    return other in toks and audience not in toks


def picker_key(row: dict) -> str:
    """Colour and size variants of one product share a key."""
    title = fold(row.get("title", ""))
    title = re.sub(r"\s+(?:mau|size|kich thuoc|kich co)\s+.*$", "", title)
    return re.sub(r"\s+", " ", title).strip()


def display_name(row: dict) -> str:
    """Product name for a list: the title up to its SEO tail, without the colour or
    size, so one design does not read as "... 016 Màu"."""
    # 20 words, not 12: a model code such as "Tài Lộc 005" sits at the end of a
    # long shop title, and cutting it makes two designs read as one.
    name = short_name(row, max_words=20)
    name = re.sub(r"\s+(?:màu|mầu|size|kích thước)\b.*$", "", name, flags=re.I)
    return name.strip(" ,;:-") or row.get("title", "")


def _price_number(price: str) -> Optional[float]:
    m = re.search(r"\d[\d.,]*", price or "")
    if not m:
        return None
    digits = m.group(0)
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", digits):
        digits = re.sub(r"[.,]", "", digits)
    else:
        digits = digits.replace(",", "")
    try:
        return float(digits)
    except ValueError:
        return None


def pick_products(site: Site, query: str, top: Optional[int] = None, *, in_stock: bool = False,
                  price_min: Optional[float] = None, price_max: Optional[float] = None) -> dict:
    """The products a "top N" post may list: only those whose title or category
    holds the head noun of ``query``. Never padded: when fewer than N qualify the
    answer says how many exist."""
    info = parse_query(query)
    want = top or info["number"] or 5
    head_text = " ".join(info["head"])
    res = {"site": site.name, "query": query, "head": head_text, "audience": info["audience"],
           "requested": want, "qualified": 0, "returned": 0, "items": [], "note": "", "shorter": []}
    if not info["head"]:
        res["note"] = ("Không tách được tên sản phẩm từ yêu cầu này. Hỏi người viết đúng một câu: "
                       "họ muốn top sản phẩm nào (ví dụ balo, ví da)?")
        return res
    pool = [r for r in site.rows if r.get("type") == "product" and not row_eligible(r)
            and head_matches(r, info) and not audience_conflict(r, info["audience"])]

    def kept(r: dict) -> bool:
        price = _price_number(r.get("price", ""))
        if price_min is not None and (price is None or price < price_min):
            return False
        if price_max is not None and (price is None or price > price_max):
            return False
        return not (in_stock and _unavailable(r))

    pool = [r for r in pool if kept(r)]
    terms = " ".join(info["head"] + info["terms"])
    scores = {r["url"]: r["score"] for r in search(pool, terms, type="product", top=len(pool))} if pool else {}
    groups: dict = {}
    for r in pool:
        base = scores.get(r["url"], 0.0) * _priority(r)
        if _head_contiguous(r, info):
            base *= 1.5
        groups.setdefault(picker_key(r), []).append((r, base))
    items = []
    for _, members in groups.items():
        # the in-stock variant with the best score stands for the group
        members.sort(key=lambda m: (_unavailable(m[0]), -m[1], m[0]["url"]))
        rep, score = members[0]
        items.append({
            "url": rep["url"], "name": display_name(rep), "title": rep.get("title", ""),
            "category": rep.get("category", ""), "price": rep.get("price", ""),
            "in_stock": rep.get("in_stock", ""), "variants": len(members),
            "variant_urls": [m[0]["url"] for m in members], "score": round(score, 4),
            "unavailable": all(_unavailable(m[0]) for m in members),
        })
    items.sort(key=lambda d: (d["unavailable"], -d["score"], d["url"]))
    res["qualified"] = len(items)
    res["items"] = items[:want]
    res["returned"] = len(res["items"])
    if len(items) < want:
        res["note"] = (f"Web chỉ có {len(items)} sản phẩm khớp \"{head_text}\""
                       + (f" ({info['audience']})" if info["audience"] else "")
                       + f", ít hơn {want} yêu cầu. Viết top {len(items)}, không thêm sản phẩm khác cho đủ số."
                       if items else
                       f"Web không có sản phẩm nào khớp \"{head_text}\". Không thêm sản phẩm khác cho đủ số; "
                       "hỏi người viết đổi chủ đề hoặc kiểm tra inventory.csv.")
        if len(info["head"]) > 1:
            for n in range(len(info["head"]) - 1, 0, -1):
                sub = dict(info, head=info["head"][:n])
                cnt = len({picker_key(r) for r in site.rows if r.get("type") == "product"
                           and not row_eligible(r) and head_matches(r, sub)
                           and not audience_conflict(r, info["audience"])})
                if cnt and cnt > len(items):
                    res["shorter"].append({"head": " ".join(sub["head"]), "count": cnt})
            if res["shorter"] and not items:
                res["note"] += " Cụm ngắn hơn có sản phẩm: " + "; ".join(
                    f"\"{s['head']}\" ({s['count']})" for s in res["shorter"]) + "."
    return res


def format_price_vnd(price: str) -> str:
    """"222750" -> "222.750đ"; anything that is not a plain number is kept."""
    n = _price_number(price)
    if n is None or n != int(n):
        return price or ""
    return f"{int(n):,}".replace(",", ".") + "đ"


def render_products(res: dict) -> str:
    lines = [f"## Sản phẩm cho bài \"{res['query']}\" ({res['site']})", "",
             f"Cụm tên sản phẩm: {res['head'] or '(không rõ)'}. Cần {res['requested']}, "
             f"web có {res['qualified']} sản phẩm khớp, liệt kê {res['returned']}.", ""]
    if res["items"]:
        lines += ["| # | Sản phẩm | Giá tham khảo | Tồn kho | Biến thể | URL |", "| --- | --- | --- | --- | --- | --- |"]
        for i, it in enumerate(res["items"], 1):
            stock = {"yes": "còn hàng", "no": "hết hàng"}.get(it["in_stock"], "chưa rõ")
            lines.append(f"| {i} | {_cell(it['name'])} | {_cell(format_price_vnd(it['price']))} | {stock} | "
                         f"{it['variants']} | {it['url']} |")
    if res["note"]:
        lines += ["", res["note"]]
    if res["items"]:
        lines += ["", "Cho người viết xem danh sách này trong một tin nhắn, cho họ đổi món nếu muốn, "
                      "rồi chạy: python3 scripts/site_inventory.py details <URL>... để lấy thông số trước khi viết."]
    return "\n".join(lines)


#: Words that say what kind of post it is, not what it is about. Left out of
#: the ranking query so "huong dan" does not pull every how-to page.
INTENT_WORDS = DUP_FILLER | frozenset("chọn mua nên".split())
INTENT_PLAIN = DUP_FILLER_PLAIN | frozenset("chon mua nen".split())
#: A candidate must reach this share of the best score.
CANDIDATE_REL_CUTOFF = 0.2


def candidates(site: Site, topic: str, top: int = 25) -> dict:
    """Related inventory rows, mixed by type, plus duplicates of the topic."""
    # numbers never rank anything: the 10 of "top 10" matched "No.10" in a product name
    words = [fold(o) for o in _WORD_RE.findall(normalize(topic))
             if not is_stop(o) and o.lower() not in INTENT_WORDS and not (o == fold(o) and o in INTENT_PLAIN)
             and not _NUM_RE.search(o)]
    info = parse_query(topic)
    ranked = search(site.rows, " ".join(words) or topic, top=len(site.rows))
    if ranked:
        # strong match (a fifth of the best score), or at least two of the topic's
        # words in the row at a real score: "vi da" finds a leather wallet even
        # when a category named exactly after the topic scores five times higher
        floor = ranked[0]["score"] * CANDIDATE_REL_CUTOFF
        topic_words = {w for w in words}
        keep = []
        for r in ranked:
            doc = site.docs[site.index[norm_url(r["url"])]]
            shared = len(topic_words & set(doc))
            # a product that holds the topic's head noun is on topic whatever its score
            # next to a post that matched more of the other words
            on_head = r.get("type") == "product" and bool(info["head"]) and head_matches(r, info)
            if r["score"] >= floor or on_head or (shared >= 2 and r["score"] >= MIN_PARA_X * site.rare):
                keep.append(r)
        ranked = keep
    quotas = {"product": 5, "category": 3, "page": 2}
    quotas["post"] = max(0, top - sum(quotas.values()))
    taken: dict = {k: [] for k in quotas}
    seen_variants: dict = {}
    for r in ranked:
        t = r.get("type")
        if t not in quotas or row_eligible(r) or _unavailable(r):
            continue
        # a product must hold the head noun of the topic, or it is not about it
        if t == "product" and info["head"] and (not head_matches(r, info) or audience_conflict(r, info["audience"])):
            continue
        vk = (t, _variant_key(r))
        if vk in seen_variants:
            seen_variants[vk]["variants"] = seen_variants[vk].get("variants", 1) + 1
            continue
        if len(taken[t]) >= quotas[t]:
            continue
        r["variants"] = 1
        seen_variants[vk] = r
        taken[t].append(r)
    items = []
    for t in ("post", "category", "product", "page"):
        for r in taken[t]:
            forms = RowForms(r, site)
            boost = striking_boost(r)
            items.append({
                "url": r["url"], "type": t, "title": r.get("title", ""),
                "category": r.get("category", ""), "price": r.get("price", ""),
                "focus_keyword": r.get("focus_keyword", ""), "anchors": r.get("anchors", ""),
                "priority": r.get("priority", ""), "score": round(r["score"] * boost, 4),
                "variants": r["variants"], "anchor_hints": forms.anchor_hints(),
                **({"striking": True} if boost > 1.0 else {}),
            })
    items.sort(key=lambda d: -d["score"])
    items = items[:top]
    return {"site": site.name, "topic": topic,
            "duplicates": find_duplicates(site, topic),
            "candidates": items,
            "counts": dict(Counter(i["type"] for i in items))}


def render_candidates(res: dict) -> str:
    lines = [f"## Liên kết cho chủ đề: {res['topic']} ({res['site']})", ""]
    if res["duplicates"]:
        lines += ["### Web đã có bài gần giống chủ đề này", "",
                  "| Độ giống | Bài đã có | Khớp theo |", "| --- | --- | --- |"]
        for d in res["duplicates"]:
            lines.append(f"| {d['similarity']} | {_cell(d['title'])} ({d['url']}) | {d['matched_on']} |")
        lines += ["", "Hỏi người viết đúng một câu: viết góc nhìn mới khác bài đó, hay viết lại bài cũ "
                      "(dùng blog-rewrite với URL trên)? Chưa soạn bài trước khi có câu trả lời.", ""]
    lines += ["### Đích liên kết được phép (chỉ liên kết tới các URL này)", "",
              "| # | Loại | Tiêu đề | URL | Gợi ý neo |", "| --- | --- | --- | --- | --- |"]
    for i, c in enumerate(res["candidates"], 1):
        extra = f" (+{c['variants'] - 1} màu/biến thể)" if c.get("variants", 1) > 1 else ""
        if c.get("striking"):
            extra += " (sắp lên top: ưu tiên link tới)"
        lines.append(f"| {i} | {c['type']} | {_cell(c['title'])}{extra} | {c['url']} | "
                     f"{_cell('; '.join(c['anchor_hints']))} |")
    if not res["candidates"]:
        lines.append("| | | Không có trang nào liên quan trong danh sách | | |")
    return "\n".join(lines)


def _cell(text: str) -> str:
    return (text or "").replace("|", "/").replace("\n", " ")


# ---------------------------------------------------------------------------
# suggest
# ---------------------------------------------------------------------------

def paragraph_scores(text: str, site: Site, skip: frozenset = frozenset()) -> dict:
    """Row index -> relevance of a paragraph to each inventory row. ``skip`` holds
    tokens (unigrams and bigrams) that do not count."""
    q = set(tokenize(text)) - skip
    out = {}
    for i, doc in enumerate(site.docs):
        s = 0.0
        for tok in q:
            w = doc.get(tok)
            if w:
                s += site.idf.get(tok, 0.0) * w * (1.0 + 0.5 * (len(tok.split()) - 1))
        if s > 0:
            out[i] = s
    return out


def _row_score(text: str, site: Site, i: int, skip: frozenset) -> float:
    doc = site.docs[i]
    return sum(site.idf.get(t, 0.0) * doc[t] * (1.0 + 0.5 * (len(t.split()) - 1))
               for t in set(tokenize(text)) - skip if t in doc)


@dataclass
class Candidate:
    block: int
    row: dict
    span: Span
    anchor_type: str
    score: float
    quality: float


def find_candidates(draft: Draft, site: Site, forms_cache: Optional[dict] = None) -> list:
    forms_cache = {} if forms_cache is None else forms_cache
    cands: list = []
    for b in draft.blocks:
        if not b.eligible:
            continue
        masks = _masked(b.text)
        spans = list(iter_spans(b.text, masks))
        if not spans:
            continue
        para = paragraph_scores(b.text, site)
        for i, ps in para.items():
            row = site.rows[i]
            if row_eligible(row) or _unavailable(row) or row.get("type") in ("tag", "other"):
                continue
            if ps < MIN_PARA_X * site.rare:
                continue
            forms = forms_cache.setdefault(row["url"], RowForms(row, site))
            best_by: dict = {}
            for sp in spans:
                if not _valid_edges(sp.orig):
                    continue
                kind = forms.match(sp.words)
                if kind is None:
                    continue
                if kind == "gsc":
                    # verbatim only: same words, same marks, as Google saw the query
                    if normalize(sp.text).lower() != forms.gsc_text:
                        continue
                    kind = "partial"
                if (row.get("type") == "page" and kind != "exact"
                        and forms.cover.get(sp.words, 1.0) <= 0.5):
                    continue                       # a page is linked by most of its name
                q = anchor_quality(sp.words, site.docs[i], site.idf, sp.orig)
                if kind != "exact" and q < MIN_ANCHOR_X * site.rare:
                    continue
                rank = q - 0.15 * abs(len(sp.words) - 3)
                key = "exact" if kind == "exact" else "other"
                if key not in best_by or rank > best_by[key].quality:
                    best_by[key] = Candidate(b.index, row, sp, kind, 0.0, rank)
            for key, best in best_by.items():
                ctx = _row_score(b.text, site, i, frozenset(tokenize(best.span.text)))
                if key != "exact" and ctx < MIN_CONTEXT_X * site.rare:
                    continue                       # a listed anchor is its own evidence
                # an exact anchor is the last resort: only 1 in 10 links may be one
                best.score = round((ctx + 2 * best.quality) * _priority(row) * striking_boost(row)
                                   * (0.9 if key == "exact" else 1.0), 3)
                cands.append(best)
    cands.sort(key=lambda c: (-c.score, c.row["url"], c.block))
    return cands


def build_policy(draft: Draft, site: Site, found: list) -> Policy:
    lo, hi, target = density_band(draft.words)
    pol = Policy(draft.canonical, draft.slug, draft.buying_guide, lo, hi, target,
                 draft.intro_block, draft.intro_end)
    pol.listed = frozenset(norm_url(u) for u in draft.products)
    pol.listed_variants = frozenset(
        _variant_key(site.by_url[k]) for k in pol.listed
        if k in site.by_url and site.by_url[k].get("type") == "product")
    pol.seed(found)
    return pol


def suggest(draft: Draft, site: Site, target: Optional[int] = None) -> dict:
    found = existing_links(draft.blocks, site)
    pol = build_policy(draft, site, found)
    goal = min(target or pol.target, pol.hi)
    cands = find_candidates(draft, site)
    chosen: list = []
    skipped: Counter = Counter()
    cap_products = goal if draft.buying_guide else int(PRODUCT_SHARE_MAX * goal + 1e-9)
    cap_exact = max_exact(goal)
    for c in cands:
        if pol.total >= goal:
            break
        if c.row.get("type") == "product" and not draft.buying_guide and pol.products >= cap_products:
            skipped["quá 40% sản phẩm"] += 1
            continue
        if c.anchor_type == "exact" and pol.exact >= cap_exact:
            skipped["quá 1 neo nguyên văn trên 10"] += 1
            continue
        why = pol.reject_reason(c.row, c.block, c.span.start, c.anchor_type)
        if why:
            skipped[why] += 1
            continue
        pol.take(c.row, c.block, c.anchor_type)
        chosen.append(c)
    # final aggregate check on the real totals; drop products, then exact anchors
    while True:
        bad = aggregate_violations(pol.total, pol.products, pol.exact, draft.buying_guide)
        if not bad:
            break
        pool = [c for c in chosen if c.row.get("type") == "product"] if "Sản phẩm" in bad[0] else \
               [c for c in chosen if c.anchor_type == "exact"]
        if not pool:
            break
        drop = min(pool, key=lambda c: c.score)
        chosen.remove(drop)
        pol.total -= 1
        pol.products -= drop.row.get("type") == "product"
        pol.exact -= drop.anchor_type == "exact"
        skipped["bỏ để giữ đúng tỉ lệ"] += 1
    chosen.sort(key=lambda c: (c.block, c.span.start))
    links = []
    for c in chosen:
        b = draft.blocks[c.block]
        ctx = b.text[max(0, c.span.start - 40):c.span.end + 40].replace("\n", " ")
        links.append({"paragraph": c.block, "line": b.line + b.text.count("\n", 0, c.span.start),
                      "anchor": c.span.text, "url": c.row["url"], "type": c.row.get("type", ""),
                      "title": c.row.get("title", ""), "anchor_type": c.anchor_type,
                      "score": c.score, "context": ctx})
    ph = []
    used = set(pol.urls) | set(pol.listed)
    for p in placeholders(draft.blocks):
        entry = dict(p)
        entry["proposal"] = None
        hits = [r for r in search(site.rows, f"{p['anchor']} {p['description']}", top=10)
                if not row_eligible(r) and not is_self(r, draft.canonical, draft.slug)
                and norm_url(r["url"]) not in used and r.get("type") in ("post", "product", "category", "page")]
        qbi = {t for t in tokenize(f"{p['anchor']} {p['description']}") if " " in t}
        if hits and hits[0]["score"] >= 2 * MIN_PARA_X * site.rare and \
                qbi & {t for t in row_weights(hits[0]) if " " in t}:
            entry["proposal"] = {"url": hits[0]["url"], "title": hits[0].get("title", ""),
                                 "type": hits[0].get("type", "")}
            used.add(norm_url(hits[0]["url"]))
        ph.append(entry)
    total_after = pol.total
    warnings = []
    if total_after < pol.lo:
        warnings.append(f"Sau khi chèn chỉ có {total_after} liên kết, dưới mức tối thiểu {pol.lo}. "
                        "Thêm liên kết bằng tay tới các URL trong candidates hoặc nới tay các đoạn liên quan.")
    return {"draft": str(draft.path), "site": site.name, "word_count": draft.words,
            "buying_guide": draft.buying_guide,
            "density": {"min": pol.lo, "max": pol.hi, "target": goal},
            "existing": {"count": len([f for f in found if norm_url(f.url) not in pol.listed]),
                         "products": sum(f.kind == "product" for f in found if norm_url(f.url) not in pol.listed),
                         "urls": [f.url for f in found],
                         **({"listed_products": len([f for f in found if norm_url(f.url) in pol.listed])}
                            if pol.listed else {})},
            "links": links, "placeholders": ph,
            "total_after": total_after, "skipped": dict(skipped), "warnings": warnings}


def render_suggest(plan: dict) -> str:
    d = plan["density"]
    lines = [f"## Gợi ý liên kết nội bộ ({plan['site']})", "",
             f"Bài {plan['word_count']} từ, mức {d['min']} đến {d['max']} liên kết, mục tiêu {d['target']}. "
             f"Đã có {plan['existing']['count']}, sau khi chèn: {plan['total_after']}."
             + (" Bài hướng dẫn mua hàng: không giới hạn tỉ lệ sản phẩm." if plan["buying_guide"] else "")
             + (f" Không tính {plan['existing']['listed_products']} liên kết tới sản phẩm trong danh sách top."
                if plan["existing"].get("listed_products") else ""), ""]
    if plan["links"]:
        lines += ["| Đoạn | Dòng | Neo | Trang đích | Loại | Kiểu neo | Điểm |",
                  "| --- | --- | --- | --- | --- | --- | --- |"]
        for l in plan["links"]:
            lines.append(f"| {l['paragraph']} | {l['line']} | {_cell(l['anchor'])} | {l['url']} | "
                         f"{l['type']} | {l['anchor_type']} | {l['score']} |")
    else:
        lines.append("Không tìm được chỗ chèn nào đạt chuẩn.")
    if plan["placeholders"]:
        lines += ["", "### Chỗ giữ chỗ `[INTERNAL-LINK: ...]` cần xử lý", "",
                  "| Dòng | Neo | Đề xuất |", "| --- | --- | --- |"]
        for p in plan["placeholders"]:
            prop = p["proposal"]["url"] if p["proposal"] else "không có trang phù hợp: xóa hoặc viết lại"
            lines.append(f"| {p['line']} | {_cell(p['anchor'])} | {prop} |")
    for w in plan["warnings"]:
        lines += ["", f"Lưu ý: {w}"]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------

def _md_url(url: str) -> str:
    return url.replace(" ", "%20").replace("(", "%28").replace(")", "%29")


def apply_plan(path: Path, site: Site, items: list, dry_run: bool = False) -> dict:
    """Insert the links of ``items``. Returns {applied, refused, left_placeholders, ...}."""
    draft = load_draft(path)
    found = existing_links(draft.blocks, site)
    pol = build_policy(draft, site, found)
    text = draft.text
    applied: list = []
    refused: list = []

    def refuse(item: dict, why: str) -> None:
        refused.append({"anchor": item.get("anchor") or item.get("placeholder", ""),
                        "url": item.get("url", ""), "reason": why})

    for item in items:
        url = (item.get("url") or "").strip()
        row = site.by_url.get(norm_url(url)) if url else None
        if row is None:
            refuse(item, f"URL không có trong danh sách của web: {url or '(trống)'}. "
                         f"Thêm bằng: python3 scripts/site_inventory.py add {url or '<url>'} --site {site.name}")
            continue
        draft = _reparse(text, path)
        blocks = draft.blocks
        if item.get("placeholder"):
            res = _plan_placeholder(item, blocks, row, pol, site)
        else:
            res = _plan_anchor(item, blocks, row, pol, site)
        if isinstance(res, str):
            refuse(item, res)
            continue
        start, end, replacement, block_idx, atype, anchor = res
        text = text[:start] + replacement + text[end:]
        pol.take(row, block_idx, atype)
        applied.append({"anchor": anchor, "url": row["url"], "type": row.get("type", ""),
                        "anchor_type": atype, "paragraph": block_idx})

    # aggregate rules over the real totals: refuse the surplus, latest first
    while True:
        bad = aggregate_violations(pol.total, pol.products, pol.exact, draft.buying_guide)
        if not bad or not applied:
            break
        want = "product" if "Sản phẩm" in bad[0] else "exact"
        victim = next((a for a in reversed(applied)
                       if (a["type"] == "product" if want == "product" else a["anchor_type"] == "exact")), None)
        if victim is None:
            break
        text = _unlink(text, victim)
        applied.remove(victim)
        pol.total -= 1
        pol.products -= victim["type"] == "product"
        pol.exact -= victim["anchor_type"] == "exact"
        refused.append({"anchor": victim["anchor"], "url": victim["url"],
                        "reason": bad[0]})
    final = _reparse(text, path)
    left = placeholders(final.blocks)
    warnings = []
    if pol.total < pol.lo:
        warnings.append(f"Bài có {pol.total} liên kết nội bộ, dưới mức tối thiểu {pol.lo}.")
    warnings.extend(aggregate_violations(pol.total, pol.products, pol.exact, draft.buying_guide))
    if not dry_run and applied:
        _write_atomic(path, text)
    return {"applied": applied, "refused": refused, "left_placeholders": left,
            "total": pol.total, "min": pol.lo, "max": pol.hi, "warnings": warnings,
            "dry_run": dry_run}


def _reparse(text: str, path: Path) -> Draft:
    fm, off = parse_frontmatter(text)
    blocks = parse_blocks(text, off)
    intro = next((b for b in blocks if b.eligible), None)
    return Draft(path=path, text=text, fm=fm, body_start=off, blocks=blocks,
                 words=body_word_count(blocks), canonical=fm.get("canonical", ""),
                 slug=fm.get("slug", ""), buying_guide=is_buying_guide(fm),
                 intro_block=intro.index if intro else None,
                 intro_end=first_sentence_end(intro.text) if intro else 0,
                 products=listed_products(text, fm))


def _atype_for(row: dict, anchor: str, site: Site) -> str:
    forms = RowForms(row, site)
    t = tuple(fold_words(anchor))
    if t in forms.exact:
        return "exact"
    return forms.match(t) or "other"


def _plan_anchor(item: dict, blocks: list, row: dict, pol: Policy, site: Site):
    anchor = (item.get("anchor") or "").strip()
    if not anchor:
        return "Thiếu neo (anchor) trong kế hoạch."
    n_words = len(fold_words(anchor))
    if not MIN_SPAN_WORDS <= n_words <= MAX_SPAN_WORDS:
        return f"Neo \"{anchor}\" có {n_words} từ, cần từ {MIN_SPAN_WORDS} đến {MAX_SPAN_WORDS} từ."
    idx = item.get("paragraph")
    if idx is not None:
        if not isinstance(idx, int) or not 0 <= idx < len(blocks):
            return f"Không có đoạn số {idx}."
        pool = [blocks[idx]]
        if not blocks[idx].eligible:
            return f"Đoạn {idx} là {_kind_vi(blocks[idx].kind)}, không chèn liên kết vào đó."
    else:
        pool = [b for b in blocks if b.eligible and find_occurrences(b.text, anchor)]
        if not pool:
            if any(find_occurrences(b.text, anchor) for b in blocks):
                return f"Neo \"{anchor}\" chỉ có trong tiêu đề, mã, trích dẫn hoặc bảng; không chèn."
            return f"Neo \"{anchor}\" không có trong bài."
        if len(pool) > 1:
            return f"Neo \"{anchor}\" có trong {len(pool)} đoạn; chỉ rõ số đoạn (paragraph)."
    b = pool[0]
    occ = find_occurrences(b.text, anchor)
    if len(occ) != 1:
        return (f"Neo \"{anchor}\" xuất hiện {len(occ)} lần trong đoạn, cần đúng 1 lần."
                if occ else f"Neo \"{anchor}\" không có trong đoạn {b.index}.")
    s, e = occ[0]
    if _overlaps(s, e, _masked(b.text)):
        return f"Neo \"{anchor}\" nằm trong liên kết, ảnh, mã hoặc địa chỉ có sẵn."
    atype = _atype_for(row, b.text[s:e], site)
    why = pol.reject_reason(row, b.index, s, atype)
    if why:
        return why[0].upper() + why[1:] + "."
    original = b.text[s:e]
    return (b.start + s, b.start + e, f"[{original}]({_md_url(row['url'])})", b.index, atype, original)


def _plan_placeholder(item: dict, blocks: list, row: dict, pol: Policy, site: Site):
    key = item["placeholder"].strip()
    hits = []
    for p in placeholders(blocks):
        if key in (p["text"], p["anchor"]) or fold(key) == fold(p["anchor"]):
            hits.append(p)
    if not hits:
        return f"Không thấy chỗ giữ chỗ \"{key}\"."
    if len(hits) > 1:
        return f"Có {len(hits)} chỗ giữ chỗ giống \"{key}\"; chỉ rõ nguyên văn."
    p = hits[0]
    b = blocks[p["block"]]
    if not b.eligible and b.kind != "faq":
        return f"Chỗ giữ chỗ nằm trong {_kind_vi(b.kind)}; sửa tay."
    if not p["anchor"]:
        return "Chỗ giữ chỗ không có neo."
    off = b.text.index(p["text"])
    atype = _atype_for(row, p["anchor"], site)
    why = pol.reject_reason(row, b.index, off, atype)
    if why:
        return why[0].upper() + why[1:] + "."
    return (b.start + off, b.start + off + len(p["text"]),
            f"[{p['anchor']}]({_md_url(row['url'])})", b.index, atype, p["anchor"])


def _unlink(text: str, applied: dict) -> str:
    rx = re.compile(r"\[" + re.escape(applied["anchor"]) + r"\]\(" + re.escape(_md_url(applied["url"])) + r"\)")
    return rx.sub(applied["anchor"], text, count=1)


def _kind_vi(kind: str) -> str:
    return {"heading": "tiêu đề", "code": "khối mã", "quote": "trích dẫn", "table": "bảng",
            "html": "khối HTML", "image": "ảnh", "faq": "câu hỏi FAQ", "other": "phần không phải văn xuôi"
            }.get(kind, kind)


def render_apply(res: dict) -> str:
    lines = [f"Đã chèn {len(res['applied'])} liên kết" + (" (chạy thử, chưa ghi file)" if res["dry_run"] else "") +
             f"; bài có {res['total']} liên kết nội bộ (mức {res['min']} đến {res['max']})."]
    for a in res["applied"]:
        lines.append(f"  + [{a['anchor']}] -> {a['url']} ({a['type']}, {a['anchor_type']})")
    for r in res["refused"]:
        lines.append(f"  - Bỏ qua \"{r['anchor']}\" -> {r['url']}: {r['reason']}")
    for p in res["left_placeholders"]:
        lines.append(f"  ! Còn chỗ giữ chỗ dòng {p['line']}: {p['text']}")
    for w in res["warnings"]:
        lines.append(f"Lưu ý: {w}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# reverse
# ---------------------------------------------------------------------------

def reverse_suggestions(site: Site, post: dict, top: int = 8) -> list:
    """Existing posts that should link TO the new post. ``post`` has title,
    description, focus_keyword, url, headings. The inventory holds no body text,
    so the sentence is a proposal; the marketer picks the paragraph in the CMS."""
    title_pairs = title_chunks(post.get("title", ""), site.brand_tokens)
    orig: dict = {}
    for text in [post.get("title", ""), post.get("focus_keyword", ""), post.get("description", "")] + \
            list(post.get("headings", [])):
        for w in _WORD_RE.findall(normalize(text)):
            orig.setdefault(fold(w), w)
    new_row = {"title": post.get("title", ""), "h1": post.get("title", ""),
               "description": post.get("description", ""),
               "focus_keyword": post.get("focus_keyword", ""), "url": post.get("url", "")}
    new_w = row_weights(new_row)
    for h in post.get("headings", []):
        for tok in set(tokenize(h)):
            new_w.setdefault(tok, 1.0)
    phrases = []
    for fk in (post.get("focus_keyword", ""),):
        if fk.strip():
            phrases.append(fk.strip())
    for pairs in title_pairs:
        words = [w for _, w in pairs]
        phrases.append(" ".join(words[:MAX_SPAN_WORDS]))
    scored = []
    for row, doc in zip(site.rows, site.docs):
        if row.get("type") != "post" or row_eligible(row) or is_self(row, post.get("url", "")):
            continue
        shared = [t for t in new_w if t in doc]
        s = sum(site.idf.get(t, 0.0) * min(new_w[t], doc[t]) * (1.0 + 0.5 * (len(t.split()) - 1)) for t in shared)
        if s > 0:
            scored.append((s * _priority(row) * striking_boost(row), row, shared))
    scored.sort(key=lambda x: (-x[0], x[1]["url"]))
    out = []
    used_anchors: set = set()
    for s, row, shared in scored[:top]:
        if s < MIN_PARA_X * site.rare:
            continue
        row_tokens = set(doc for doc in shared if " " not in doc)
        pick = None
        for ph in phrases:
            n = len(fold_words(ph))
            if fold(ph) in used_anchors or not MIN_SPAN_WORDS <= n <= MAX_SPAN_WORDS:
                continue
            if row_tokens & set(fold_words(ph)):
                pick = ph
                break
        if pick is None:
            pick = next((ph for ph in phrases if fold(ph) not in used_anchors
                         and MIN_SPAN_WORDS <= len(fold_words(ph)) <= MAX_SPAN_WORDS), phrases[0] if phrases else "")
        used_anchors.add(fold(pick))
        best_shared = sorted((t for t in shared if " " in t), key=lambda t: -site.idf.get(t, 0))[:1] or \
            sorted(shared, key=lambda t: -site.idf.get(t, 0))[:1]
        topic = " ".join(orig.get(w, w) for w in best_shared[0].split()) if best_shared else pick
        out.append({"post_url": row["url"], "post_title": row.get("title", ""), "score": round(s, 2),
                    "anchor": pick,
                    "sentence": f"Nếu bạn đang tìm hiểu về {topic}, xem thêm [{pick}]({post.get('url', '')}).",
                    "note": "Chỉ là câu gợi ý. Mở bài này trong CMS, chọn đoạn nói về chủ đề trên rồi dán."})
    return out


def post_info(draft: Draft, url: str = "") -> dict:
    heads = [re.sub(r"^#+\s*", "", b.text.splitlines()[0]) for b in draft.blocks
             if b.kind == "heading" and b.text.lstrip().startswith("##")]
    fm = draft.fm
    return {"title": fm.get("title", ""), "description": fm.get("description", ""),
            "focus_keyword": fm.get("focus_keyword") or fm.get("primary_keyword") or fm.get("keyword", ""),
            "url": url or fm.get("canonical", ""), "headings": heads}


def render_reverse(items: list, url: str) -> str:
    lines = [f"## Bài cũ nên trỏ về bài mới ({url})", "",
             "Tôi không sửa web. Bạn dán thủ công vào CMS.", ""]
    if not items:
        return "\n".join(lines + ["Không có bài cũ nào đủ liên quan."])
    lines += ["| Bài cũ | Neo | Câu gợi ý |", "| --- | --- | --- |"]
    for i in items:
        lines.append(f"| {_cell(i['post_title'])} ({i['post_url']}) | {_cell(i['anchor'])} | {_cell(i['sentence'])} |")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Gate 5 and rubric support
# ---------------------------------------------------------------------------

def check_internal_links(site: Site, md_text: str, html_links: list, canonical: str,
                         html_text: str = "", draft_hint: str = "") -> dict:
    """Gate 5 content check for a post whose canonical host is a configured site.

    Returns {violations, warnings, internal_urls, placeholders}. Violations are
    Vietnamese and name the URL and the command that adds it.
    """
    violations: list = []
    warnings: list = []
    fm, off = parse_frontmatter(normalize(md_text))
    blocks = parse_blocks(normalize(md_text), off)
    seen_ph: set = set()
    for p in placeholders(blocks):
        seen_ph.add(p["text"])
    for m in _PLACEHOLDER_RE.finditer(html_text or ""):
        seen_ph.add(m.group(0))
    for txt in sorted(seen_ph):
        violations.append(
            f"Còn chỗ giữ chỗ liên kết chưa thay bằng liên kết thật: \"{txt}\". "
            f"Chạy: python3 scripts/internal_links.py suggest --draft {draft_hint or '<thư mục bài>'} "
            "rồi apply, hoặc xóa chỗ giữ chỗ.")
    hrefs = [f.href for f in existing_links(blocks, site)] if md_text else []
    for h in html_links or []:
        if h not in hrefs:
            hrefs.append(h)
    urls: list = []
    for href in hrefs:
        url = _resolve(href, site)
        if url is None or is_self(url, canonical):
            continue
        key = norm_url(url)
        if key in [norm_url(u) for u in urls]:
            continue
        urls.append(url)
        row = site.by_url.get(key)
        if row is None:
            violations.append(
                f"Liên kết nội bộ không có trong danh sách của web {site.name}: {url}. "
                f"Nếu trang này có thật, thêm vào danh sách bằng: "
                f"python3 scripts/site_inventory.py add {url} --site {site.name} ; "
                "nếu không, xóa liên kết hoặc đổi sang trang có trong danh sách.")
        elif row.get("type") == "gone":
            violations.append(f"Liên kết nội bộ trỏ tới trang đã gỡ khỏi web (type=gone): {url}. "
                              "Đổi sang trang còn sống.")
        elif row_eligible(row):
            warnings.append(f"Liên kết tới trang đã đánh dấu exclude trong inventory.csv: {url}")
    if is_roundup(fm):
        v, w = check_roundup(site, fm, md_text, urls, canonical)
        violations += v
        warnings += w
    return {"violations": violations, "warnings": warnings, "internal_urls": urls,
            "placeholders": sorted(seen_ph)}


_TOP_N_RE = re.compile(r"\btop\s*(\d+)\b", re.I)


def check_roundup(site: Site, fm: dict, md_text: str, linked_urls: list, canonical: str = "") -> tuple:
    """Gate 5 checks for ``content_type: roundup`` (and only then): every product in
    ``products:`` is in the inventory and not gone, is linked in the body, an
    out-of-stock one is a warning, and "top N" in the title equals the number of
    products. Returns (violations, warnings), Vietnamese."""
    violations: list = []
    warnings: list = []
    products = frontmatter_list(normalize(md_text), "products")
    if not products:
        violations.append(
            "Bài roundup chưa khai báo danh sách sản phẩm. Thêm khóa products: vào phần đầu bài, mỗi dòng một URL "
            "sản phẩm có trong danh sách của web (chạy: python3 scripts/internal_links.py products --query \"...\").")
        return violations, warnings
    linked = {norm_url(u) for u in linked_urls}
    seen: set = set()
    for url in products:
        key = norm_url(url)
        if key in seen:
            violations.append(f"Sản phẩm xuất hiện hai lần trong products: {url}")
            continue
        seen.add(key)
        row = site.by_url.get(key)
        # a product that is also linked in the body was already reported by the link loop
        if row is None and key in linked:
            continue
        if row is not None and row.get("type") == "gone" and key in linked:
            continue
        if row is None:
            violations.append(
                f"Sản phẩm trong products: không có trong danh sách của web {site.name}: {url}. "
                f"Nếu sản phẩm có thật, thêm bằng: python3 scripts/site_inventory.py add {url} --site {site.name} ; "
                "nếu không, thay bằng sản phẩm có thật (python3 scripts/internal_links.py products).")
            continue
        if row.get("type") == "gone":
            violations.append(f"Sản phẩm trong products: đã gỡ khỏi web (type=gone): {url}. Thay bằng sản phẩm còn bán.")
            continue
        if row.get("type") != "product":
            violations.append(f"Địa chỉ trong products: không phải trang sản phẩm ({row.get('type')}): {url}")
            continue
        if key not in linked:
            violations.append(f"Sản phẩm có trong products: nhưng thân bài không liên kết tới nó: {url}. "
                              "Mỗi sản phẩm trong top phải có một liên kết thật tới trang của nó.")
        if _unavailable(row):
            warnings.append(f"Sản phẩm đang hết hàng trên web: {url}. Cân nhắc thay bằng sản phẩm còn hàng.")
    m = _TOP_N_RE.search(fm.get("title", ""))
    if m and int(m.group(1)) != len(products):
        violations.append(f"Tiêu đề nói top {m.group(1)} nhưng products: có {len(products)} sản phẩm. "
                          "Sửa tiêu đề hoặc danh sách cho khớp.")
    return violations, warnings


def link_summary(body_md: str, fm: dict, site: Site, words: Optional[int] = None,
                 raw_md: str = "") -> dict:
    """Numbers the draft rubric scores when a site is configured. In a roundup
    (``raw_md`` carries its frontmatter) the listed products are not counted."""
    text = normalize(body_md)
    blocks = parse_blocks(text, 0)
    found = existing_links(blocks, site)
    canonical = fm.get("canonical", "")
    found = [f for f in found if not is_self(f.url, canonical)]
    listed = {norm_url(u) for u in listed_products(normalize(raw_md), fm)} if raw_md else set()
    if listed:
        found = [f for f in found if norm_url(f.url) not in listed]
    w = words if words is not None else body_word_count(blocks)
    lo, hi, target = density_band(w)
    urls = [norm_url(f.url) for f in found]
    return {
        "count": len(found), "unique": len(set(urls)), "min": lo, "max": hi, "target": target,
        "products": sum(f.kind == "product" for f in found),
        "exact": sum(f.anchor_type == "exact" for f in found),
        "unknown": [f.url for f in found if f.row is None],
        "gone": [f.url for f in found if f.row is not None and f.row.get("type") == "gone"],
        "placeholders": len(placeholders(blocks)),
        "buying_guide": is_buying_guide(fm),
        "repeated_anchors": [a for a, n in Counter(fold(f.anchor) for f in found).items() if n > 1],
        "site": site.name,
    }


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------

def _print_json(obj: Any) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def cmd_candidates(args) -> int:
    site = pick_site(args.site)
    res = candidates(site, args.topic, top=args.top)
    if args.json:
        _print_json(res)
    else:
        print(render_candidates(res))
    return 0


def cmd_products(args) -> int:
    site = pick_site(args.site)
    res = pick_products(site, args.query, top=args.top, in_stock=args.in_stock,
                        price_min=args.price_min, price_max=args.price_max)
    if args.json:
        _print_json(res)
    else:
        print(render_products(res))
    return 0


def cmd_suggest(args) -> int:
    path = find_draft_md(args.draft)
    draft = load_draft(path)
    site = pick_site(args.site, draft.canonical)
    plan = suggest(draft, site, target=args.target)
    out = Path(args.plan_out) if args.plan_out else path.parent / "internal-links-plan.json"
    out.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.json:
        _print_json(plan)
    else:
        print(render_suggest(plan))
        print(f"\nKế hoạch đã lưu: {out}")
    return 0


def cmd_apply(args) -> int:
    path = find_draft_md(args.draft)
    draft = load_draft(path)
    site = pick_site(args.site, draft.canonical)
    plan_path = Path(args.plan) if args.plan else path.parent / "internal-links-plan.json"
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise InventoryError(f"Không đọc được kế hoạch {plan_path}: {exc}. Chạy suggest trước.")
    items = list(plan.get("links", []))
    for p in plan.get("placeholders", []):
        prop = p.get("proposal") or {}
        if p.get("resolve", True) and prop.get("url"):
            items.append({"placeholder": p["text"], "url": prop["url"]})
    res = apply_plan(path, site, items, dry_run=args.dry_run)
    if args.json:
        _print_json(res)
    else:
        print(render_apply(res))
    return 0 if not res["left_placeholders"] else 3


def cmd_reverse(args) -> int:
    path = find_draft_md(args.draft)
    draft = load_draft(path)
    site = pick_site(args.site, draft.canonical)
    info = post_info(draft)
    items = reverse_suggestions(site, info, top=args.top)
    if args.json:
        _print_json({"post": info["url"], "suggestions": items})
    else:
        print(render_reverse(items, info["url"]))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("candidates", help="Đích liên kết cho chủ đề, và bài trùng chủ đề")
    s.add_argument("--topic", required=True)
    s.add_argument("--site")
    s.add_argument("--top", type=int, default=25)
    s.add_argument("--json", action="store_true")
    s = sub.add_parser("products", help="Chọn sản phẩm thật cho bài top N (không đệm sản phẩm không liên quan)")
    s.add_argument("--query", required=True, help='Ví dụ "balo nam" hoặc "top 5 balo nam"')
    s.add_argument("--site")
    s.add_argument("--top", type=int, help="Số sản phẩm cần (mặc định: số trong câu, hoặc 5)")
    s.add_argument("--in-stock", dest="in_stock", action="store_true")
    s.add_argument("--price-min", dest="price_min", type=float)
    s.add_argument("--price-max", dest="price_max", type=float)
    s.add_argument("--json", action="store_true")
    s = sub.add_parser("suggest", help="Gợi ý liên kết cho từng đoạn của bài")
    s.add_argument("--draft", required=True)
    s.add_argument("--site")
    s.add_argument("--target", type=int, help="Số liên kết mong muốn (mặc định giữa khoảng theo độ dài)")
    s.add_argument("--plan-out")
    s.add_argument("--json", action="store_true")
    s = sub.add_parser("apply", help="Chèn liên kết theo kế hoạch")
    s.add_argument("--draft", required=True)
    s.add_argument("--site")
    s.add_argument("--plan")
    s.add_argument("--dry-run", action="store_true")
    s.add_argument("--json", action="store_true")
    s = sub.add_parser("reverse", help="Bài cũ nên trỏ về bài mới (không sửa web)")
    s.add_argument("--draft", required=True)
    s.add_argument("--site")
    s.add_argument("--top", type=int, default=8)
    s.add_argument("--json", action="store_true")
    return p


def main(argv: Optional[list] = None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {"candidates": cmd_candidates, "products": cmd_products, "suggest": cmd_suggest,
                "apply": cmd_apply, "reverse": cmd_reverse}
    try:
        return handlers[args.cmd](args)
    except InventoryError as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
