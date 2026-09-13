#!/usr/bin/env python3
"""Vietnamese address-register consistency checker.

Vietnamese has no register-neutral second person pronoun. A writer picks one
of at least three registers and, in careful prose, holds it for the whole
piece:

    peer    ban, minh, chung minh, tui, to (see REGISTER_MARKERS for the
            real Vietnamese spelling with diacritics)
    polite  anh chi, anh, chi, cac ban
    formal  quy khach, quy vi, quy cong ty, quy khach hang

Mixing registers inside one post is one of the clearest marks of a
post assembled from multiple passes (human draft plus AI pass, or two
different AI passes) rather than written straight through, because a human
writer holding a register in their head does not drift by accident the way
a sentence-by-sentence rewrite can.

This module reports which register is dominant and the line number of every
sentence that uses a different one. It does not resolve a mixed post
automatically; a human decides which register the post should keep.

Known ambiguity and how it is handled
--------------------------------------
Several markers are homographs with an unrelated word once diacritics are
folded away, which is how the ambiguity is usually described. With correct
diacritics most of that ambiguity does not exist (the table is "ban" with a
different tone mark than the pronoun "ban"), but two real collisions remain:

- "ban" is also the ordinary noun for "friend" inside a compound: "ban doc"
  (reader), "ban be" (friends), "ban hang" (business partner), "ban dien"
  (co-star), "ban hoc" (classmate), "ban gai" / "ban trai" (girlfriend or
  boyfriend), "ban than" (close friend), "ban cung" (roommate, classmate).
  The token immediately after "ban" is checked against this list and the
  match is dropped when it hits.
- "anh" is also part of a country or subject name: "tieng Anh" (the English
  language), "nuoc Anh" / "vuong quoc Anh" (England, the United Kingdom),
  "Anh van" / "Anh ngu" (English as a school subject), "anh hung" (hero).
  Both the preceding and the following token are checked.

Known miss, documented rather than fixed: "ban ay" (that friend, third
person) is still counted as a peer marker, because it still reads as
peer-register prose even though it is not literally addressing the reader.
A marker consumed by a longer marker is not counted again ("cac ban"
consumes both tokens, so it is not also counted as a bare "ban"). Anything
not in the exclusion lists above is not modeled; a rarer compound will
still be miscounted, which is why every occurrence is reported with a line
number for a human to confirm, not silently applied as a score deduction.

Stdlib only.
"""

from __future__ import annotations

import argparse
import errno
import json
import os
import re
import stat
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import vi_text  # noqa: E402

MAX_INPUT_BYTES = 10 * 1024 * 1024

# Register -> markers, real Vietnamese with diacritics. Order within a
# register does not matter; cross-register overlap is resolved by scanning
# longest marker (by token count) first, see _ALL_MARKERS below.
REGISTER_MARKERS: dict[str, tuple[str, ...]] = {
    'peer': ('chúng mình', 'bạn', 'mình', 'tui', 'tớ'),
    'polite': ('anh chị', 'các bạn', 'anh', 'chị'),
    'formal': ('quý khách hàng', 'quý khách', 'quý vị', 'quý công ty'),
}

# Deterministic tie-break when two registers have the same sentence count.
# Arbitrary but documented: peer wins ties, then polite, then formal.
_REGISTER_TIEBREAK = {'peer': 0, 'polite': 1, 'formal': 2}

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

# "ban" followed by one of these forms a compound noun, not the pronoun.
_BAN_NOUN_FOLLOW = frozenset({
    'đọc', 'bè', 'hàng', 'diễn', 'học', 'gái', 'trai', 'thân', 'cùng',
})

# "anh" inside a country / language / subject name, not an address pronoun.
_ANH_NOUN_PRECEDE = frozenset({'tiếng', 'nước', 'vương'})
_ANH_NOUN_FOLLOW = frozenset({'quốc', 'văn', 'ngữ', 'hùng'})


def _tokenize(sentence: str) -> list[str]:
    return re.findall(r"[^\W\d_]+", sentence, re.UNICODE)


def _sentence_spans(line: str) -> list[str]:
    return [s for s in re.split(r'(?<=[.!?…])\s+', line) if s.strip()]


def _find_markers(sentence: str) -> list[tuple[str, str]]:
    """Return [(register, marker), ...] for pronoun-reading matches.

    Longer markers are matched first and their token span is marked
    consumed, so "cac ban" is never also counted as a bare "ban", and
    "anh chi" is never also counted as bare "anh" plus bare "chi".
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
            if marker == 'bạn' and next_tok in _BAN_NOUN_FOLLOW:
                continue
            if marker == 'anh' and (
                prev_tok in _ANH_NOUN_PRECEDE or next_tok in _ANH_NOUN_FOLLOW
            ):
                continue
            hits.append((register, marker))
            for j in range(i, i + n):
                consumed[j] = True
    return hits


def analyze_register(text: str) -> dict[str, Any]:
    """Return dominant register, per-register counts, and off-register lines.

    ``off_register`` lists one entry per (line, register) pair actually
    found, each with the line number, the register, the markers matched on
    that line, and a short sentence excerpt. A sentence that wraps across a
    markdown line break is attributed to the physical line the marker
    appears on, not necessarily the line the sentence started on; this is a
    documented simplification, not a crash risk.
    """
    normalized = vi_text.normalize(text)
    lines = normalized.splitlines()

    sentence_hits: list[dict[str, Any]] = []
    marker_counts = {'peer': 0, 'polite': 0, 'formal': 0}

    for line_no, line in enumerate(lines, start=1):
        for sentence in _sentence_spans(line):
            hits = _find_markers(sentence)
            if not hits:
                continue
            by_register: dict[str, list[str]] = {}
            for register, marker in hits:
                marker_counts[register] += 1
                by_register.setdefault(register, []).append(marker)
            for register, markers in by_register.items():
                sentence_hits.append({
                    'line': line_no,
                    'register': register,
                    'markers': markers,
                    'sentence': sentence.strip()[:160],
                })

    sentence_counts = {'peer': 0, 'polite': 0, 'formal': 0}
    for row in sentence_hits:
        sentence_counts[row['register']] += 1

    total = sum(sentence_counts.values())
    dominant = None
    if total > 0:
        dominant = max(
            sentence_counts,
            key=lambda k: (sentence_counts[k], -_REGISTER_TIEBREAK[k]),
        )

    off_register = (
        [row for row in sentence_hits if row['register'] != dominant]
        if dominant is not None else []
    )

    return {
        'marker_counts': marker_counts,
        'sentence_counts': sentence_counts,
        'dominant_register': dominant,
        'total_sentences_with_marker': total,
        'off_register': off_register,
        'consistent': len(off_register) == 0,
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
        lines.append('No register markers (ban/minh, anh/chi, quy khach ...) found.')
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
