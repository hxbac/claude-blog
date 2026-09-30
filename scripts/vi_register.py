#!/usr/bin/env python3
"""Vietnamese address-register (xưng hô) consistency checker.

This is the ONE register implementation in the repository. ``vi_prose.py`` and
``analyze_blog.py`` import it; nothing else may carry its own marker sets.

Vietnamese has no register-neutral second person pronoun. A writer picks one
of three registers and, in careful prose, holds it for the whole piece:

    peer    bạn, các bạn, mình, chúng mình, tui, tớ
    polite  anh chị, các anh chị (also written anh/chị)
    formal  quý khách, quý vị, quý công ty, quý khách hàng, quý độc giả ...

Mixing registers inside one post is one of the clearest marks of a post
assembled from several passes, so it is a P0 defect, but only when the mix is
real. Review 2026-09-17 (finding A1) showed the previous checker flagging
ordinary human Vietnamese, so four rules now decide what counts:

1. Only reader-facing prose is scanned. Frontmatter (the author "Lan Anh" is
   not the pronoun "anh"), fenced code, inline code, HTML comments, link
   targets, blockquotes and quoted spans ("quý khách" in quotation marks is a
   word being discussed, not an address) are removed first. Line numbers are
   preserved, so a finding still points at the right line of the file.
2. Bare ``anh`` and ``chị`` are NOT markers. In third person they are the
   normal kinship nouns ("anh thợ mộc", "chị khách"). Only the address forms
   ``anh chị`` and ``các anh chị`` count, and ``anh chị em`` (siblings) does not.
3. A register is "in use" only by sentences, not tokens. The dominant register
   is the one with the most marked sentences.
4. Drift is reported only when a minority register holds at least
   ``max(15% of marked sentences, 3 sentences)``. Below that it is recorded as
   ``tolerated`` (a stray quotation or aside) and does not fail the post.

Homograph guards (kept from Phase G): ``bạn`` inside ``bạn đọc``, ``bạn bè``,
``bạn hàng``; ``một mình`` / ``tự mình`` / ``chính mình`` (reflexive, not the
peer pronoun); ``người bạn`` / ``cô bạn`` (a third person friend).

Known miss, documented rather than fixed: ``bạn ấy`` (that friend, third
person) still counts as peer, because it still reads as peer-register prose.

Stdlib only.
"""

from __future__ import annotations

import argparse
import errno
import json
import math
import os
import re
import stat
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import vi_text  # noqa: E402

MAX_INPUT_BYTES = 10 * 1024 * 1024

#: A minority register is drift once it holds this share of marked sentences...
DRIFT_MIN_RATIO = 0.15
#: ...or this many sentences, whichever is larger.
DRIFT_MIN_SENTENCES = 3

# Register -> markers, real Vietnamese with diacritics. Overlap between
# registers is resolved by scanning the longest marker (by token count) first.
_FORMAL_HEADS = (
    'quý khách hàng', 'quý khách', 'quý vị', 'quý công ty', 'quý độc giả',
    'quý bạn đọc', 'quý phụ huynh', 'quý đối tác', 'quý anh chị',
)
REGISTER_MARKERS: dict[str, tuple[str, ...]] = {
    'peer': ('chúng mình', 'các bạn', 'bạn', 'mình', 'tui', 'tớ'),
    'polite': ('các anh chị', 'anh chị'),
    'formal': _FORMAL_HEADS,
}

# Deterministic tie-break when two registers have the same sentence count.
_REGISTER_TIEBREAK = {'peer': 0, 'polite': 1, 'formal': 2}
_REGISTERS = ('peer', 'polite', 'formal')

_ALL_MARKERS: tuple[tuple[str, str], ...] = tuple(
    sorted(
        (
            (marker, register)
            for register, markers in REGISTER_MARKERS.items()
            for marker in markers
        ),
        key=lambda pair: -len(pair[0].split()),
    )
)

# "bạn" followed by one of these forms a compound noun, not the pronoun.
_BAN_NOUN_FOLLOW = frozenset({
    'đọc', 'bè', 'hàng', 'diễn', 'học', 'gái', 'trai', 'thân', 'cùng',
    'nhậu', 'đời', 'tình', 'nghề',
})
# "bạn" preceded by one of these is a third person friend ("người bạn").
_BAN_NOUN_PRECEDE = frozenset({'người', 'cô', 'cậu', 'ông', 'bà', 'những', 'mấy'})
# "mình" that is reflexive or a body noun, not the peer pronoun.
_MINH_NOUN_PRECEDE = frozenset({'một', 'tự', 'chính', 'riêng'})
_MINH_NOUN_FOLLOW = frozenset({'mẩy'})
# "anh chị em" is "siblings", a kinship noun.
_ANH_CHI_NOUN_FOLLOW = frozenset({'em'})


# ---------------------------------------------------------------------------
# Reader-facing prose extraction
# ---------------------------------------------------------------------------


def _blank_keep_newlines(match: 're.Match[str]') -> str:
    return re.sub(r'[^\n]', ' ', match.group(0))


_QUOTE_SPAN_RES = (
    re.compile(r'"[^"\n]{1,300}"'),
    re.compile(r'\u201c[^\u201d\n]{1,300}\u201d'),
    re.compile(r'\u00ab[^\u00bb\n]{1,300}\u00bb'),
)


def strip_non_prose(text: str) -> str:
    """Remove everything that is not the author speaking to the reader.

    The result has exactly the same number of lines as the input, so a line
    number found in the stripped text is the line number in the file.
    """
    text = vi_text.normalize(text).replace('\r\n', '\n')
    # Frontmatter, only when the file opens with it.
    text = re.sub(r'\A---[ \t]*\n.*?\n---[ \t]*(?:\n|\Z)',
                  _blank_keep_newlines, text, count=1, flags=re.DOTALL)
    # Fenced code (``` or ~~~), then HTML comments, both spanning lines.
    text = re.sub(r'(?ms)^[ \t]*(`{3,}|~{3,}).*?^[ \t]*\1[ \t]*$',
                  _blank_keep_newlines, text)
    text = re.sub(r'<!--.*?-->', _blank_keep_newlines, text, flags=re.DOTALL)
    text = re.sub(r'`[^`\n]*`', lambda m: ' ' * len(m.group(0)), text)
    text = re.sub(r'!\[[^\]\n]*\]\([^)\n]*\)', ' ', text)
    text = re.sub(r'\[([^\]\n]+)\]\([^)\n]*\)', r'\1', text)
    text = re.sub(r'<[^>\n]+>', ' ', text)
    # Blockquotes are quotations, whole lines of them.
    text = re.sub(r'(?m)^[ \t]*>.*$', '', text)
    for pattern in _QUOTE_SPAN_RES:
        text = pattern.sub(' ', text)
    return text


def _tokenize(sentence: str) -> list[str]:
    return re.findall(r"[^\W\d_]+", sentence, re.UNICODE)


def _sentences_with_lines(clean: str) -> list[tuple[int, str]]:
    """Return (start_line, sentence) pairs. Soft-wrapped lines of one
    paragraph are joined first, so one sentence is never counted twice."""
    lines = clean.split('\n')
    blocks: list[list[tuple[int, str]]] = []
    current: list[tuple[int, str]] = []
    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()
        starts_new = bool(re.match(r'(?:#{1,6}\s|[-*+]\s|\d+[.)]\s|\|)', stripped))
        if not stripped:
            if current:
                blocks.append(current)
                current = []
            continue
        if starts_new and current:
            blocks.append(current)
            current = []
        current.append((idx, stripped))
        if starts_new and re.match(r'#{1,6}\s', stripped):
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)

    out: list[tuple[int, str]] = []
    for block in blocks:
        joined = ''
        offsets: list[tuple[int, int]] = []
        for line_no, content in block:
            if joined:
                joined += ' '
            offsets.append((len(joined), line_no))
            joined += content
        pos = 0
        for part in re.split(r'(?<=[.!?\u2026])\s+', joined):
            if not part.strip():
                continue
            start = joined.find(part, pos)
            pos = start + len(part)
            line_no = block[0][0]
            for off, ln in offsets:
                if off <= start:
                    line_no = ln
            out.append((line_no, part.strip()))
    return out


def _find_markers(sentence: str) -> list[tuple[str, str]]:
    """Return [(register, marker), ...] for pronoun-reading matches.

    Longer markers are matched first and their token span is consumed, so
    "các bạn" is never also counted as a bare "bạn".
    """
    tokens = _tokenize(sentence.lower())
    hits: list[tuple[str, str]] = []
    consumed = [False] * len(tokens)
    for marker, register in _ALL_MARKERS:
        marker_tokens = marker.split()
        n = len(marker_tokens)
        for i in range(len(tokens) - n + 1):
            if any(consumed[i:i + n]):
                continue
            if tokens[i:i + n] != marker_tokens:
                continue
            prev_tok = tokens[i - 1] if i > 0 else None
            next_tok = tokens[i + n] if i + n < len(tokens) else None
            if marker == 'bạn' and (
                next_tok in _BAN_NOUN_FOLLOW or prev_tok in _BAN_NOUN_PRECEDE
            ):
                continue
            if marker == 'mình' and (
                prev_tok in _MINH_NOUN_PRECEDE or next_tok in _MINH_NOUN_FOLLOW
            ):
                continue
            if marker == 'anh chị' and next_tok in _ANH_CHI_NOUN_FOLLOW:
                continue
            hits.append((register, marker))
            for j in range(i, i + n):
                consumed[j] = True
    return hits


def drift_threshold(marked_sentences: int) -> int:
    """Sentences a minority register needs before it counts as drift."""
    return max(DRIFT_MIN_SENTENCES, math.ceil(DRIFT_MIN_RATIO * marked_sentences))


def analyze_register(text: str) -> dict[str, Any]:
    """Return dominant register, per-register counts, and off-register lines.

    ``off_register`` lists one row per sentence of every register that reached
    the drift threshold. ``tolerated`` lists the rows of minority registers
    that stayed below it (informational, never fails). ``consistent`` is False
    only when ``off_register`` is non-empty.
    """
    clean = strip_non_prose(text)

    sentence_hits: list[dict[str, Any]] = []
    marker_counts = {reg: 0 for reg in _REGISTERS}
    marked_sentences = 0

    for line_no, sentence in _sentences_with_lines(clean):
        hits = _find_markers(sentence)
        if not hits:
            continue
        marked_sentences += 1
        by_register: dict[str, list[str]] = {}
        for register, marker in hits:
            marker_counts[register] += 1
            by_register.setdefault(register, []).append(marker)
        for register, markers in by_register.items():
            sentence_hits.append({
                'line': line_no,
                'register': register,
                'markers': markers,
                'sentence': sentence[:160],
            })

    sentence_counts = {reg: 0 for reg in _REGISTERS}
    for row in sentence_hits:
        sentence_counts[row['register']] += 1

    dominant = None
    if any(sentence_counts.values()):
        dominant = max(
            sentence_counts,
            key=lambda k: (sentence_counts[k], -_REGISTER_TIEBREAK[k]),
        )

    threshold = drift_threshold(marked_sentences)
    drifting = [
        reg for reg in _REGISTERS
        if reg != dominant and sentence_counts[reg] >= threshold
    ]
    off_register = [row for row in sentence_hits if row['register'] in drifting]
    tolerated = [
        row for row in sentence_hits
        if dominant is not None
        and row['register'] != dominant
        and row['register'] not in drifting
    ]

    return {
        'marker_counts': marker_counts,
        'sentence_counts': sentence_counts,
        'dominant_register': dominant,
        'total_sentences_with_marker': sum(sentence_counts.values()),
        'marked_sentences': marked_sentences,
        'drift_threshold': threshold,
        'drift_registers': drifting,
        'off_register': off_register,
        'tolerated': tolerated,
        'consistent': not off_register,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _read_safely(path: Path, max_bytes: int = MAX_INPUT_BYTES) -> str:
    """Read a regular non-symlink file with a size cap. Mirrors the same
    helper in analyze_blog.py and cognitive_load.py."""
    flags = os.O_RDONLY
    if hasattr(os, 'O_NOFOLLOW'):
        flags |= os.O_NOFOLLOW
    elif path.is_symlink():
        raise ValueError(f'refusing to follow symlink: {path}')
    try:
        fd = os.open(str(path), flags)
    except FileNotFoundError as exc:
        raise ValueError(f'file not found: {path}') from exc
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise ValueError(f'refusing to follow symlink: {path}') from exc
        raise ValueError(f'could not open safely: {path} ({exc})') from exc
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise ValueError(f'not a regular file: {path}')
        if st.st_size > max_bytes:
            raise ValueError(f'exceeds size cap ({st.st_size} bytes): {path}')
        with os.fdopen(fd, 'r', encoding='utf-8') as f:
            fd = -1
            data = f.read(max_bytes + 1)
    finally:
        if fd != -1:
            try:
                os.close(fd)
            except OSError:
                pass
    if len(data.encode('utf-8')) > max_bytes:
        raise ValueError(f'exceeds size cap after read: {path}')
    return data


def _format_markdown(result: dict[str, Any], filename: str) -> str:
    lines = [f'## Vietnamese Register Check: {filename}', '']
    dominant = result['dominant_register']
    if dominant is None:
        lines.append('No register markers (bạn/mình, anh chị, quý khách ...) found.')
        return '\n'.join(lines)
    lines.append(f"Dominant register: **{dominant}**")
    counts = result['sentence_counts']
    lines.append(
        f"Sentences by register: peer {counts['peer']}, polite {counts['polite']}, "
        f"formal {counts['formal']}"
    )
    lines.append('')
    if result['consistent']:
        lines.append('No register drift detected.')
        if result.get('tolerated'):
            lines.append(
                f"Tolerated (below the drift threshold of {result['drift_threshold']} "
                f"sentences): {len(result['tolerated'])} off-register sentence(s)."
            )
    else:
        lines.append('### Off-register sentences')
        for row in result['off_register']:
            markers = ', '.join(row['markers'])
            lines.append(
                f"- Line {row['line']} ({row['register']}, marker: {markers}): "
                f"{row['sentence']}"
            )
    return '\n'.join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Detect Vietnamese address-register drift (peer/polite/formal).'
    )
    parser.add_argument('file', help='Path to a markdown / text file')
    parser.add_argument(
        '--format', choices=['json', 'markdown'], default='json',
        help='Output format (default: json)',
    )
    args = parser.parse_args(argv)

    path = Path(args.file)
    try:
        text = _read_safely(path)
    except ValueError as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 2

    result = analyze_register(text)
    if args.format == 'markdown':
        print(_format_markdown(result, path.name))
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
