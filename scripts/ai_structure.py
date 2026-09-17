#!/usr/bin/env python3
"""
AI Structure: structural AI-writing tell detector, all languages.

This script looks for the MECHANICALLY DETECTABLE structural habits that
current language models default to when nothing in the prompt pushes them
toward a specific human voice: one-line closers, forced triads, repeated
sentence openings, decorative bold, decorative headings (English only),
curly quotation marks, a heading echoed in its own first sentence, and a
short list of literal chatbot-residue phrases.

READ THIS BEFORE ACTING ON THE OUTPUT: a structural tell is a signal, not a
verdict. Every finding below is advisory. This script does not claim to
detect AI authorship, and it must not be used that way. People who judge AI
writing by feel do little better than chance, and human writing keeps
absorbing AI habits, so a single tell proves nothing. The cluster score
(the count of DISTINCT tell types sharing one section) is the number that
actually matters: one tell in a section is noise, four in the same section
is worth a human look. Never treat any of this as an automatic score
deduction.

Dashes are already covered. This script does NOT re-implement the em-dash
(U+2014), en-dash (U+2013), or ASCII space-hyphen-hyphen-space check; that
check lives in `scripts/lint_prose.py`. Run it separately.

Attribution
===========
The pattern catalogue below is adapted from two upstream sources, credited
per their license terms. Prose and code here are original; the patterns are
not copied verbatim from either source.

- `humanizer/SKILL.md` (this repo's gitignored reference clone of
  github.com/blader/humanizer), MIT License, Copyright 2025 Siqi Chen.
  Nothing in that skill file is imported or executed; it is source material
  for pattern selection only.
- Wikipedia's "Signs of AI writing" catalogue
  (en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing), maintained by
  WikiProject AI Cleanup, licensed CC BY-SA. The humanizer skill itself
  cites this as its upstream source.

Usage:
    python3 ai_structure.py <file>                    # text report (default)
    python3 ai_structure.py <file> --format json       # structured JSON
    python3 ai_structure.py <file> --lang vi           # Vietnamese phrase lists
    python3 ai_structure.py -                          # read from stdin

Stdlib only. No network. No score is computed or returned; this is a
findings-and-cluster-score report only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Shared regex fragments
# ---------------------------------------------------------------------------

_WORD_RE = re.compile(r"\w+", re.UNICODE)

# Minimal function-word lists for the internal content-word-overlap heuristics
# used by the one-line-closer and heading-echo checks below. This is NOT the
# scored AI-trigger-word / transition-word vocabulary owned by vi_profile.py
# and analyze_blog.py; it exists only to tell "the writer's real subject
# words" apart from glue words for an overlap ratio, and is intentionally
# small and boring.
_STOPWORDS: dict[str, set[str]] = {
    "en": {
        "the", "a", "an", "and", "or", "but", "of", "in", "on", "at", "for",
        "to", "with", "by", "as", "is", "are", "was", "were", "be", "been",
        "being", "this", "that", "these", "those", "it", "its", "they",
        "them", "their", "we", "you", "he", "she", "i", "not", "no", "so",
        "than", "too", "very", "can", "will", "just", "about", "from",
        "into", "out", "up", "down", "all", "any", "each", "more", "most",
        "some", "such", "there", "here", "what", "which", "who", "when",
    },
    "vi": {
        "và", "của", "là", "cho", "với", "các", "những", "một", "này",
        "đó", "khi", "đã", "sẽ", "có", "không", "cũng", "thì", "mà", "để",
        "trong", "trên", "dưới", "về", "như", "nên", "vì", "nếu", "hay",
        "hoặc", "rất", "rằng", "nhưng", "được", "bị", "từ", "theo", "tại",
        "vào", "ra", "lên", "xuống", "ai", "gì", "sao", "vậy", "thế",
    },
}

# Chatbot-residue phrases (item 22 in the humanizer catalogue): fixed
# leftovers from a chat turn that were never meant for the reader.
_CHATBOT_RESIDUE: dict[str, tuple[str, ...]] = {
    "en": (
        r"\bcertainly!",
        r"\bof course!",
        r"\bgreat question!",
        r"\byou'?re absolutely right\b",
        r"\bi hope this helps\b",
        r"^\s*here is\b",
        r"\blet me know\b",
        r"\bwould you like\b",
        r"\bwant me to\b",
        r"\bshould i continue\b",
    ),
    "vi": (
        r"hy\s+vọng\s+bài\s+viết\s+này",
        r"^\s*dưới\s+đây\s+là\b",
        r"chắc\s+chắn\s+rồi",
        r"rất\s+vui\s+được\s+hỗ\s+trợ\s+bạn",
        r"bạn\s+có\s+muốn\s+(?:tôi|mình)",
        r"hãy\s+cho\s+tôi\s+biết\s+nếu\s+bạn",
    ),
}

# One-line-closer stock phrases (item 2): direct match in addition to the
# word-overlap heuristic below. Kept short on purpose; a long list rots the
# same way the English AI-trigger-word list rotted (see PHASE-G-VIETNAMESE-PARITY.md).
# Optional intensifier slot: "moi", "chinh", "thuc su", "that su", in any
# order and any combination, or nothing at all.
_VI_INTENSIFIER = r"\s+(?:(?:mới|chính|thực\s+sự|thật\s+sự)\s+)*"

_CLOSER_PHRASES: dict[str, tuple[str, ...]] = {
    "en": (
        r"that is the real win",
        r"that'?s the real win",
        r"let that sink in",
        r"read that again",
    ),
    # Vietnamese allows an optional intensifier between the demonstrative and
    # the rest of a stock closer: "do chinh la", "do moi chinh la", "do moi
    # that su la". Matching the bare form misses the inflated variants, which
    # are the ones a model reaches for. _VI_INTENSIFIER absorbs them.
    "vi": (
        r"hãy\s+đọc\s+lại\s+câu\s+trên",
        r"đó" + _VI_INTENSIFIER + r"là\s+mấu\s+chốt",
        r"đó" + _VI_INTENSIFIER + r"là\s+(?:điều|vấn\s+đề)\s+(?:cốt\s+lõi|quan\s+trọng)",
        r"hãy\s+để\s+điều\s+đó\s+thấm",
        r"vấn\s+đề\s+(?:chính\s+)?nằm\s+ở\s+đó",
        r"và\s+đó\s+là\s+lý\s+do",
    ),
}

_TRIAD_CONJUNCTION: dict[str, str] = {"en": "and", "vi": "và"}

_SMALL_WORDS_EN = {
    "a", "an", "the", "and", "or", "but", "of", "in", "on", "at", "for",
    "to", "with", "as", "by", "is",
}

_CURLY_QUOTE_CHARS = "“”‘’"  # left/right double + single

# Thresholds. Each is a documented, adjustable guess, not a derived
# statistic; the cluster score, not any single threshold, is what should
# drive a human decision.
_CLOSER_MAX_WORDS = 12
_CLOSER_OVERLAP_THRESHOLD = 0.5
_CLOSER_MIN_PREV_CONTENT_WORDS = 3
_TRIAD_MIN_COUNT_FOR_FLAG = 3
_REPEAT_MIN_RUN = 3
_BOLD_LIST_LABEL_MIN_RUN = 3
_BOLD_DENSITY_PER_1000_THRESHOLD = 12.0
_BOLD_DENSITY_MIN_SPANS = 4
_DECORATIVE_HEADING_MIN_COUNT = 3
_DECORATIVE_HEADING_RATIO_THRESHOLD = 0.6
_HEADING_ECHO_OVERLAP_THRESHOLD = 0.7
_HEADING_ECHO_MAX_SENTENCE_WORDS = 12


# ---------------------------------------------------------------------------
# Text preparation
# ---------------------------------------------------------------------------


def mask_code(text: str) -> str:
    """Blank out fenced code blocks and inline code spans, preserving line
    count and line length so downstream line-number reporting stays exact.

    This is a fence-tracking approach in the same spirit as
    `lint_prose.py`, applied here for a different purpose (keeping
    structural checks off code samples), not a reimplementation of the
    dash check itself.
    """
    lines = text.split("\n")
    out: list[str] = []
    fence_open: str | None = None
    for line in lines:
        stripped = line.lstrip()
        if fence_open is None:
            m = re.match(r"(`{3,}|~{3,})", stripped)
            if m is not None:
                fence_open = m.group(1)
                out.append(" " * len(line))
                continue
        else:
            m = re.match(r"(`{3,}|~{3,})", stripped)
            if (
                m is not None
                and m.group(1)[0] == fence_open[0]
                and len(m.group(1)) >= len(fence_open)
            ):
                fence_open = None
            out.append(" " * len(line))
            continue
        masked = re.sub(r"`[^`\n]*`", lambda mo: " " * len(mo.group(0)), line)
        out.append(masked)
    return "\n".join(out)


def content_words(text: str, lang: str) -> set[str]:
    stop = _STOPWORDS.get(lang, _STOPWORDS["en"])
    return {
        w.lower()
        for w in _WORD_RE.findall(text)
        if len(w) >= 2 and w.lower() not in stop
    }


def split_sentences(paragraph_text: str) -> list[str]:
    """Approximate sentence splitter. Stdlib-only heuristic: this will
    over-split on abbreviations and under-split on some run-ons. Adequate
    for an advisory structural scan, not a linguistic parser.
    """
    flat = re.sub(r"\s+", " ", paragraph_text).strip()
    if not flat:
        return []
    parts = re.split(r"(?<=[.!?])\s+", flat)
    return [p.strip() for p in parts if p.strip()]


# ---------------------------------------------------------------------------
# Document model: sections and paragraphs
# ---------------------------------------------------------------------------


def parse_sections(masked_lines: list[str]) -> list[dict[str, Any]]:
    """Split a document into heading-delimited sections. The text before
    the first heading (if any) becomes a section with heading == "".
    """
    heading_re = re.compile(r"^(#{1,6})\s+(\S.*)$")
    sections: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for i, line in enumerate(masked_lines, start=1):
        m = heading_re.match(line)
        if m is not None:
            if current is not None:
                sections.append(current)
            current = {
                "heading": m.group(2).strip(),
                "level": len(m.group(1)),
                "start_line": i,
                "lines": [],
            }
        else:
            if current is None:
                current = {"heading": "", "level": 0, "start_line": 1, "lines": []}
            current["lines"].append((i, line))
    if current is not None:
        sections.append(current)
    return sections


def split_paragraphs(lines: list[tuple[int, str]]) -> list[dict[str, Any]]:
    paragraphs: list[dict[str, Any]] = []
    buf: list[tuple[int, str]] = []
    for line_no, text in lines:
        if text.strip() == "":
            if buf:
                paragraphs.append(
                    {"start_line": buf[0][0], "text": "\n".join(t for _, t in buf)}
                )
                buf = []
        else:
            buf.append((line_no, text))
    if buf:
        paragraphs.append({"start_line": buf[0][0], "text": "\n".join(t for _, t in buf)})
    return paragraphs


def _is_prose_paragraph(text: str) -> bool:
    stripped = text.lstrip()
    if stripped.startswith(("-", "*", "+", ">", "#")):
        return False
    if re.match(r"^\d+[.)]\s", stripped):
        return False
    return True


def _line_to_section_index(sections: list[dict[str, Any]], total_lines: int) -> list[int]:
    """1-indexed line -> section index lookup (index 0 unused)."""
    lookup = [0] * (total_lines + 2)
    for idx, sec in enumerate(sections):
        end = sections[idx + 1]["start_line"] if idx + 1 < len(sections) else total_lines + 1
        start = sec["start_line"] if sec["heading"] else 1
        for ln in range(start, end):
            if 0 <= ln < len(lookup):
                lookup[ln] = idx
    return lookup


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------


def _finding(
    check: str,
    line: int,
    detail: str,
    excerpt: str,
    weak_alone: bool = False,
) -> dict[str, Any]:
    return {
        "check": check,
        "line": line,
        "detail": detail,
        "excerpt": excerpt[:160],
        "weak_alone": weak_alone,
    }


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def check_one_line_closer(
    all_paragraphs: list[dict[str, Any]], lang: str
) -> list[dict[str, Any]]:
    """Item 2: a one-sentence paragraph that mostly repeats the content
    words of the paragraph before it, or matches a stock closer phrase.
    """
    findings: list[dict[str, Any]] = []
    phrases = _CLOSER_PHRASES.get(lang, ())
    prev_words: set[str] | None = None
    for para in all_paragraphs:
        text = para["text"]
        is_prose = _is_prose_paragraph(text)
        sentences = split_sentences(text)
        word_count = len(_WORD_RE.findall(text))
        cw = content_words(text, lang) if is_prose else set()

        if is_prose and prev_words is not None and len(prev_words) >= _CLOSER_MIN_PREV_CONTENT_WORDS:
            if len(sentences) == 1 and 1 <= word_count <= _CLOSER_MAX_WORDS:
                overlap = (len(cw & prev_words) / len(cw)) if cw else 0.0
                phrase_hit = any(re.search(p, text, re.IGNORECASE) for p in phrases)
                if overlap >= _CLOSER_OVERLAP_THRESHOLD or phrase_hit:
                    reason = (
                        "matches a stock closer phrase"
                        if phrase_hit
                        else f"{overlap:.0%} content-word overlap with the previous paragraph"
                    )
                    findings.append(
                        _finding(
                            "one_line_closer",
                            para["start_line"],
                            f"One-sentence paragraph restates the point before it ({reason}).",
                            text,
                        )
                    )
        if is_prose and cw:
            prev_words = cw
    return findings


def check_forced_triads(
    section_sentences: list[tuple[int, str]], lang: str
) -> list[tuple[int, str]]:
    """Item 6: three comma/conjunction-joined parallel items in one
    sentence. Returns raw hits (line, matched text); the caller applies the
    document-wide 3-or-more threshold before turning these into findings.
    """
    conj = _TRIAD_CONJUNCTION.get(lang, "and")
    pattern = re.compile(
        rf"\b(\w+(?:\s+\w+){{0,3}}),\s*(\w+(?:\s+\w+){{0,3}}),?\s+{conj}\s+(\w+(?:\s+\w+){{0,3}})\b",
        re.IGNORECASE,
    )
    hits: list[tuple[int, str]] = []
    for line_no, sentence in section_sentences:
        for m in pattern.finditer(sentence):
            hits.append((line_no, m.group(0)))
    return hits


def check_repeated_openings(
    section_sentences: list[tuple[int, str]]
) -> list[dict[str, Any]]:
    """Item 7: three or more consecutive sentences opening with the same
    normalized first token, within one section.
    """
    def first_token(s: str) -> str | None:
        m = re.match(r"[\"'‘“]?(\w+)", s.strip())
        return m.group(1).lower() if m else None

    tokens = [first_token(s) for _, s in section_sentences]
    findings: list[dict[str, Any]] = []
    i = 0
    n = len(tokens)
    while i < n:
        if tokens[i] is None:
            i += 1
            continue
        j = i
        while j < n and tokens[j] == tokens[i]:
            j += 1
        run_len = j - i
        if run_len >= _REPEAT_MIN_RUN:
            line_no = section_sentences[i][0]
            findings.append(
                _finding(
                    "repeated_openings",
                    line_no,
                    f"{run_len} consecutive sentences open with {tokens[i]!r}.",
                    section_sentences[i][1],
                )
            )
        i = j
    return findings


_BOLD_RE = re.compile(r"\*\*[^*\n]+\*\*")
_BOLD_LIST_LABEL_RE = re.compile(r"^[-*+]\s*\*\*[^*\n]+\*\*:?")


def check_bold_density(masked_text: str) -> dict[str, Any] | None:
    """Item 19 (density variant): bold spans per 1,000 words above
    threshold, at document scope."""
    words = len(_WORD_RE.findall(masked_text))
    spans = _BOLD_RE.findall(masked_text)
    if words == 0 or len(spans) < _BOLD_DENSITY_MIN_SPANS:
        return None
    rate = (len(spans) / words) * 1000
    if rate > _BOLD_DENSITY_PER_1000_THRESHOLD:
        return {"rate_per_1000_words": round(rate, 1), "span_count": len(spans)}
    return None


def check_bold_list_labels(section: dict[str, Any]) -> dict[str, Any] | None:
    """Item 19 (list-label variant): a run of list items that each open
    with a bold label and colon, throughout the section."""
    best = 0
    best_line = None
    consecutive = 0
    run_start_line = None
    for line_no, text in section["lines"]:
        stripped = text.strip()
        if _BOLD_LIST_LABEL_RE.match(stripped):
            if consecutive == 0:
                run_start_line = line_no
            consecutive += 1
            if consecutive > best:
                best = consecutive
                best_line = run_start_line
        elif stripped == "":
            continue
        else:
            consecutive = 0
    if best >= _BOLD_LIST_LABEL_MIN_RUN:
        return {"line": best_line, "run_length": best}
    return None


def _heading_content_words(heading: str) -> list[str]:
    return [w for w in re.split(r"\s+", heading.strip()) if w]


def is_title_case_heading(heading: str) -> bool:
    words = _heading_content_words(heading)
    major = [
        w for w in words
        if re.sub(r"\W", "", w).lower() not in _SMALL_WORDS_EN and re.sub(r"\W", "", w)
    ]
    if len(major) < 2:
        return False

    def cap_ok(w: str) -> bool:
        core = re.sub(r"^\W+", "", w)
        return bool(core) and core[0].isupper()

    return all(cap_ok(w) for w in major)


def check_decorative_headings(
    headings: list[tuple[int, str]], lang: str
) -> dict[str, Any] | None:
    """Item 20, English only: the humanizer catalogue's Title Case check
    does not transfer to Vietnamese (Vietnamese has no title-case
    capitalization convention to violate), so this check is a no-op outside
    `en`, matching the plan's table.
    """
    if lang != "en" or len(headings) < _DECORATIVE_HEADING_MIN_COUNT:
        return None
    offending = [(ln, h) for ln, h in headings if is_title_case_heading(h)]
    ratio = len(offending) / len(headings)
    if ratio > _DECORATIVE_HEADING_RATIO_THRESHOLD:
        return {
            "ratio": round(ratio, 2),
            "offending_count": len(offending),
            "total_headings": len(headings),
            "lines": [ln for ln, _ in offending],
        }
    return None


def check_curly_quotes(masked_lines: list[str]) -> list[dict[str, Any]]:
    """Item 21. Most editors auto-curl quotes, so the humanizer skill
    itself marks this *weak alone*; it counts toward the cluster score but
    should not be acted on by itself.
    """
    findings: list[dict[str, Any]] = []
    for line_no, line in enumerate(masked_lines, start=1):
        if any(ch in line for ch in _CURLY_QUOTE_CHARS):
            findings.append(
                _finding(
                    "curly_quotes",
                    line_no,
                    "Curly quotation mark found; weak alone, meaningful only in company.",
                    line,
                    weak_alone=True,
                )
            )
    return findings


def check_heading_echo(sections: list[dict[str, Any]], lang: str) -> list[dict[str, Any]]:
    """Item 24: a heading is immediately followed by a sentence that
    mostly just restates the heading before any real content arrives."""
    findings: list[dict[str, Any]] = []
    for sec in sections:
        heading = sec["heading"]
        if not heading:
            continue
        heading_words = content_words(heading, lang)
        if not heading_words:
            continue
        paragraphs = split_paragraphs(sec["lines"])
        first_prose = next((p for p in paragraphs if _is_prose_paragraph(p["text"])), None)
        if first_prose is None:
            continue
        sentences = split_sentences(first_prose["text"])
        if not sentences:
            continue
        first_sentence = sentences[0]
        sentence_words = content_words(first_sentence, lang)
        if not sentence_words:
            continue
        overlap = len(heading_words & sentence_words) / len(heading_words)
        sentence_len = len(_WORD_RE.findall(first_sentence))
        if overlap >= _HEADING_ECHO_OVERLAP_THRESHOLD and sentence_len <= _HEADING_ECHO_MAX_SENTENCE_WORDS:
            findings.append(
                _finding(
                    "heading_echoed",
                    first_prose["start_line"],
                    f"First sentence restates the heading {heading!r} "
                    f"({overlap:.0%} content-word overlap) before adding anything.",
                    first_sentence,
                )
            )
    return findings


def check_chatbot_residue(masked_lines: list[str], lang: str) -> list[dict[str, Any]]:
    patterns = [re.compile(p, re.IGNORECASE) for p in _CHATBOT_RESIDUE.get(lang, ())]
    findings: list[dict[str, Any]] = []
    for line_no, line in enumerate(masked_lines, start=1):
        for pat in patterns:
            if pat.search(line):
                findings.append(
                    _finding(
                        "chatbot_residue",
                        line_no,
                        "Chatbot-turn leftover phrase found; it was never meant for the reader.",
                        line,
                    )
                )
                break
    return findings


#: Humanizer item 1, "not X but Y". That skill leaves the pattern to human
#: judgement because English expresses it a dozen ways. Vietnamese does not:
#: it uses a small set of FIXED correlative frames, which makes the same
#: pattern mechanically detectable in this language and not in English. The
#: frame is legitimate prose on its own, so this is weak alone and only
#: reports once two or more appear in the same post.
_NOT_X_BUT_Y: dict[str, tuple[str, ...]] = {
    "vi": (
        r"không\s+chỉ\b[^.!?]{0,80}?\bmà\s+còn\b",
        r"không\s+những\b[^.!?]{0,80}?\bmà\s+còn\b",
        r"không\s+phải\s+là\b[^.!?]{0,80}?\bmà\s+là\b",
        r"đây\s+không\s+chỉ\s+là\b[^.!?]{0,80}?\bmà\s+còn\s+là\b",
    ),
}

_NOT_X_BUT_Y_MIN = 2


def check_not_x_but_y(masked_lines: list[str], lang: str) -> list[dict[str, Any]]:
    """Correlative framing that adds weight without adding a claim.

    The negative half names something nobody claimed, so the positive half
    sounds larger. One is ordinary Vietnamese. Several in one post is the
    model reaching for emphasis it has not earned.
    """
    patterns = [re.compile(p, re.IGNORECASE) for p in _NOT_X_BUT_Y.get(lang, ())]
    if not patterns:
        return []
    hits: list[tuple[int, str]] = []
    for line_no, line in enumerate(masked_lines, start=1):
        for pat in patterns:
            match = pat.search(line)
            if match:
                hits.append((line_no, match.group(0)))
                break
    if len(hits) < _NOT_X_BUT_Y_MIN:
        return []
    return [
        _finding(
            "not_x_but_y",
            line_no,
            "Correlative framing adds weight rather than a claim "
            f"({len(hits)} found in the post; {_NOT_X_BUT_Y_MIN}+ triggers this check).",
            excerpt,
            weak_alone=True,
        )
        for line_no, excerpt in hits
    ]


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def analyze(text: str, lang: str = "en") -> dict[str, Any]:
    masked = mask_code(text)
    masked_lines = masked.split("\n")
    sections = parse_sections(masked_lines)
    line_to_section = _line_to_section_index(sections, len(masked_lines))

    all_paragraphs: list[dict[str, Any]] = []
    for sec in sections:
        all_paragraphs.extend(split_paragraphs(sec["lines"]))

    headings = [(sec["start_line"], sec["heading"]) for sec in sections if sec["heading"]]

    findings: list[dict[str, Any]] = []

    # Item 2: one-line closers (global paragraph order, so a closer right
    # after a heading boundary is still caught).
    findings.extend(check_one_line_closer(all_paragraphs, lang))

    # Item 6: forced triads, gathered per section then thresholded doc-wide.
    triad_hits: list[tuple[int, str]] = []
    for sec in sections:
        sentences: list[tuple[int, str]] = []
        for para in split_paragraphs(sec["lines"]):
            for s in split_sentences(para["text"]):
                sentences.append((para["start_line"], s))
        triad_hits.extend(check_forced_triads(sentences, lang))
    if len(triad_hits) >= _TRIAD_MIN_COUNT_FOR_FLAG:
        for line_no, matched in triad_hits:
            findings.append(
                _finding(
                    "forced_triad",
                    line_no,
                    f"Forced triad ({len(triad_hits)} found in the post; "
                    f"3+ triggers this check).",
                    matched,
                )
            )

    # Item 7: repeated openings, scoped per section.
    for sec in sections:
        sentences = []
        for para in split_paragraphs(sec["lines"]):
            for s in split_sentences(para["text"]):
                sentences.append((para["start_line"], s))
        findings.extend(check_repeated_openings(sentences))

    # Item 19: bold as decoration, both variants.
    bold_density = check_bold_density(masked)
    if bold_density is not None:
        # Attribute to every section that actually contains a bold span, so
        # the cluster score reflects where the decoration concentrates.
        for sec in sections:
            sec_text = "\n".join(t for _, t in sec["lines"])
            spans_here = _BOLD_RE.findall(sec_text)
            if spans_here:
                findings.append(
                    _finding(
                        "bold_decoration",
                        sec["start_line"] if sec["heading"] else (sec["lines"][0][0] if sec["lines"] else 1),
                        f"Bold used {len(spans_here)} times in this section "
                        f"(post-wide rate {bold_density['rate_per_1000_words']}/1000 words).",
                        sec_text[:160],
                    )
                )
    for sec in sections:
        label_run = check_bold_list_labels(sec)
        if label_run is not None:
            findings.append(
                _finding(
                    "bold_decoration",
                    label_run["line"],
                    f"{label_run['run_length']} consecutive list items open with a "
                    f"bold label, the same shape every time.",
                    sec["heading"] or "(preamble)",
                )
            )

    # Item 20: decorative headings, en only.
    decorative = check_decorative_headings(headings, lang)
    if decorative is not None:
        for ln in decorative["lines"]:
            findings.append(
                _finding(
                    "decorative_headings",
                    ln,
                    f"{decorative['offending_count']}/{decorative['total_headings']} "
                    f"headings are Title Case ({decorative['ratio']:.0%}).",
                    "",
                )
            )

    # Item 21: curly quotes.
    findings.extend(check_curly_quotes(masked_lines))

    # Item 24: heading echoed in its own first sentence.
    findings.extend(check_heading_echo(sections, lang))

    # Item 22: chatbot residue.
    findings.extend(check_chatbot_residue(masked_lines, lang))
    findings.extend(check_not_x_but_y(masked_lines, lang))

    # ---- cluster scoring ----
    section_names = [sec["heading"] or "(preamble)" for sec in sections]
    tell_types_per_section: list[set[str]] = [set() for _ in sections]
    for f in findings:
        idx = line_to_section[f["line"]] if 0 <= f["line"] < len(line_to_section) else 0
        idx = min(idx, len(tell_types_per_section) - 1) if tell_types_per_section else 0
        f["section"] = section_names[idx] if section_names else "(document)"
        if tell_types_per_section:
            tell_types_per_section[idx].add(f["check"])

    section_reports = []
    for idx, sec_name in enumerate(section_names):
        types = sorted(tell_types_per_section[idx])
        section_reports.append(
            {"section": sec_name, "cluster_score": len(types), "tells": types}
        )
    section_reports.sort(key=lambda r: -r["cluster_score"])
    cluster_score = section_reports[0]["cluster_score"] if section_reports else 0

    checks_summary: dict[str, int] = {}
    for f in findings:
        checks_summary[f["check"]] = checks_summary.get(f["check"], 0) + 1

    return {
        "ok": True,
        "note": (
            "Structural pattern signals, not a verdict of AI authorship. "
            "Act on a weak-alone tell only when several tells share a "
            "section; see the cluster_score below."
        ),
        "lang": lang,
        "word_count": len(_WORD_RE.findall(masked)),
        "finding_count": len(findings),
        "checks_summary": checks_summary,
        "findings": findings,
        "sections": section_reports,
        "cluster_score": cluster_score,
        "cluster_sections": [r for r in section_reports if r["cluster_score"] >= 2],
        "dash_check": (
            "Not implemented here by design; scripts/lint_prose.py already "
            "forbids U+2014, U+2013, and the ASCII space-hyphen-hyphen-space "
            "sequence. Run it separately."
        ),
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def render_text(report: dict[str, Any]) -> str:
    lines = [
        f"AI structure scan (lang={report['lang']}, {report['word_count']} words)",
        report["note"],
        "",
    ]
    if not report["findings"]:
        lines.append("No structural tells found.")
    else:
        lines.append(f"{report['finding_count']} finding(s) across {len(report['sections'])} section(s):")
        lines.append("")
        for f in report["findings"]:
            weak = " [weak alone]" if f["weak_alone"] else ""
            lines.append(f"  line {f['line']} [{f['check']}]{weak} ({f['section']}): {f['detail']}")
            if f["excerpt"].strip():
                lines.append(f"      > {f['excerpt'].strip()}")
        lines.append("")
        lines.append("Cluster score by section (distinct tell types sharing one section):")
        for r in report["sections"]:
            if r["cluster_score"] > 0:
                lines.append(f"  {r['cluster_score']}  {r['section']}  [{', '.join(r['tells'])}]")
        lines.append("")
        lines.append(f"Top cluster score: {report['cluster_score']}")
        if report["cluster_score"] >= 3:
            lines.append(
                "3+ distinct tells share one section. That is worth a human look; "
                "one tell alone would not be."
            )
    lines.append("")
    lines.append(report["dash_check"])
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("input", help="Path to a markdown/text file, or '-' for stdin")
    parser.add_argument("--lang", choices=["en", "vi"], default="en", help="Language profile (default en)")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    args = parser.parse_args()

    if args.input == "-":
        text = sys.stdin.read()
    else:
        path = Path(args.input)
        if not path.is_file():
            print(f"Error: not a file: {path}", file=sys.stderr)
            return 2
        text = path.read_text(encoding="utf-8", errors="replace")

    report = analyze(text, args.lang)

    if args.format == "json":
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(render_text(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
