#!/usr/bin/env python3
"""Generate the claude-seo copy of the Vietnamese tell table.

``vi_profile.py`` (``VI_TELLS``) is the only place Vietnamese lexical tells are
edited. claude-seo's ``content_humanize.py --lang vi`` needs the rewrite half
of that table, and the two repositories are installed separately, so the table
is copied, not imported (the same reason ``env_file.py`` is an identical copy in
each repository). This script writes the copy and checks it:

    python3 scripts/sync_vi_tells.py --write   # regenerate the claude-seo copy
    python3 scripts/sync_vi_tells.py --check   # exit 1 when the copy has drifted

The generated file carries a "do not edit" header and a sha256 of its own body,
so a hand edit is detected on the claude-seo side even when claude-blog is not
checked out next to it. ``tests/test_vi_tells_sync.py`` here and in claude-seo
enforce both checks.

Stdlib only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import vi_profile  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TARGET = REPO_ROOT.parent / 'claude-seo' / 'scripts' / 'vi_tells_generated.py'

BODY_MARKER = '# ---- BEGIN GENERATED BODY (sha256 covers everything below this line) ----\n'
HASH_PREFIX = '# body-sha256: '


def _lit(value: object) -> str:
    """A deterministic Python literal for a str or None."""
    return 'None' if value is None else json.dumps(value, ensure_ascii=False)


def render_body() -> str:
    lines = [
        '"""Vietnamese tell table for content_humanize.py --lang vi. Generated."""',
        '',
        '# (regex, replacement, label): applied in order, case-insensitive.',
        'VI_REWRITES: tuple[tuple[str, str, str], ...] = (',
    ]
    for regex, replacement, label in vi_profile.rewrite_table():
        lines.append(f'    ({_lit(regex)}, {_lit(replacement)}, {_lit(label)}),')
    lines += [
        ')',
        '',
        '# (id, tier, text, regex, label): the full tell list, for reference and',
        '# for detection-only callers. Not used by the rewrite path.',
        'VI_TELLS_DATA: tuple[tuple[str, str, str | None, str | None, str], ...] = (',
    ]
    for t in vi_profile.VI_TELLS:
        lines.append(
            f'    ({_lit(t.id)}, {_lit(t.tier)}, {_lit(t.text)}, {_lit(t.regex)}, {_lit(t.label)}),'
        )
    lines += [')', '']
    return '\n'.join(lines)


def body_sha256(body: str) -> str:
    return hashlib.sha256(body.encode('utf-8')).hexdigest()


def render() -> str:
    body = render_body()
    header = (
        '# GENERATED FILE. DO NOT EDIT.\n'
        '#\n'
        "# Source of truth: claude-blog's vi_profile.py (VI_TELLS).\n"
        '# Regenerate:      run sync_vi_tells.py with --write in the claude-blog repository.\n'
        '# A hand edit here is detected by tests/test_vi_tells_sync.py in both\n'
        '# repositories and is overwritten by the next --write.\n'
        f'{HASH_PREFIX}{body_sha256(body)}\n'
        f'{BODY_MARKER}'
    )
    return header + body


def split_generated(text: str) -> tuple[str, str] | None:
    """Return (recorded_sha, body) from a generated file, or None if malformed."""
    if BODY_MARKER not in text:
        return None
    head, body = text.split(BODY_MARKER, 1)
    for line in head.splitlines():
        if line.startswith(HASH_PREFIX):
            return line[len(HASH_PREFIX):].strip(), body
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--write', action='store_true', help='write the generated copy')
    group.add_argument('--check', action='store_true', help='exit 1 if the copy differs')
    parser.add_argument('--target', type=Path, default=DEFAULT_TARGET,
                        help=f'generated file (default: {DEFAULT_TARGET})')
    args = parser.parse_args(argv)

    expected = render()
    if args.write:
        args.target.parent.mkdir(parents=True, exist_ok=True)
        args.target.write_text(expected, encoding='utf-8')
        print(f'wrote {args.target}')
        return 0
    if not args.target.is_file():
        print(f'missing: {args.target}', file=sys.stderr)
        return 1
    if args.target.read_text(encoding='utf-8') != expected:
        print(f'DRIFT: {args.target} differs from vi_profile.py; run --write', file=sys.stderr)
        return 1
    print('in sync')
    return 0


if __name__ == '__main__':
    sys.exit(main())
