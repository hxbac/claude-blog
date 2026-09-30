#!/usr/bin/env python3
"""Vietnamese prose linter: AI-writing tells and register consistency.

Deterministic, standard library only. Complements scripts/lint_prose.py, which
enforces character hygiene across all languages; this module adds the
Vietnamese-specific checks that a language-agnostic linter cannot express.

It owns no word list and no register rule of its own (Phase J):

* lexical tells come from ``vi_profile.py`` (``scan_tells``), the one list;
* register drift comes from ``vi_register.py``, the one implementation, with
  its frontmatter/quote stripping and its 15% / 3-sentence rule.

Usage:
    python3 vi_prose.py <file.md> [--json] [--max-density 2.0]

Exit codes:
    0  clean, or findings below threshold
    1  density threshold exceeded, or a P0 finding
    2  usage / IO error
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import vi_profile
    import vi_register
    from vi_text import count_syllables, normalize
except ImportError:                                   # standalone execution
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import vi_profile
    import vi_register
    from vi_text import count_syllables, normalize

__all__ = ["lint_text", "AI_TELLS"]

#: (regex, label, fix) rows for formulaic openers and sign-offs, read from the
#: single list in vi_profile.py. Kept as a name so external callers still work.
AI_TELLS: tuple[tuple[str, str, str], ...] = vi_profile.FORMULA_TELLS


def _strip_markdown(text: str) -> str:
    """Remove frontmatter, code, tables, HTML and link targets before linting.

    Line count is preserved so a finding's line number is the file's line.
    """
    text = normalize(text).replace('\r\n', '\n')
    text = re.sub(r'\A---[ \t]*\n.*?\n---[ \t]*(?:\n|\Z)',
                  lambda m: re.sub(r'[^\n]', '', m.group(0)), text, count=1, flags=re.DOTALL)
    text = re.sub(r'```.*?```', lambda m: re.sub(r'[^\n]', '', m.group(0)), text, flags=re.DOTALL)
    text = re.sub(r'`[^`]*`', '', text)
    text = re.sub(r'^\s*\|.*\|\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'!\[.*?\]\(.*?\)', '', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    return text


def lint_text(raw: str) -> dict:
    """Return findings for one document. Pure; no IO."""
    text = _strip_markdown(raw)
    total_syllables = max(count_syllables(text), 1)

    findings: list[dict] = []
    for hit in vi_profile.scan_tells(text):
        findings.append({
            'type': 'ai_tell', 'severity': 'P1', 'label': hit['label'],
            'match': hit['match'], 'line': hit['line'], 'fix': hit['fix'],
        })

    register = vi_register.analyze_register(raw)
    if not register['consistent']:
        dominant = register['dominant_register']
        used = ', '.join(
            f'{k}={v}' for k, v in sorted(register['sentence_counts'].items()) if v
        )
        lines = sorted({row['line'] for row in register['off_register']})
        findings.append({
            'type': 'register_drift', 'severity': 'P0',
            'label': 'Xưng hô không nhất quán',
            'match': used,
            'line': lines[0] if lines else 0,
            'lines': lines,
            'fix': (f'Chọn một cách xưng hô cho cả bài. Đang dùng nhiều nhất: {dominant}. '
                    f'Sửa các dòng: {", ".join(str(n) for n in lines[:10])}.'),
        })

    tells = sum(1 for f in findings if f['type'] == 'ai_tell')
    return {
        'syllables': total_syllables,
        'ai_tell_count': tells,
        'ai_tell_density_per_1000': round(tells / total_syllables * 1000, 2),
        'register_sets_used': {k: v for k, v in register['sentence_counts'].items() if v},
        'register': {
            'dominant': register['dominant_register'],
            'drift_threshold': register['drift_threshold'],
            'tolerated': len(register['tolerated']),
            'consistent': register['consistent'],
        },
        'findings': findings,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('path', type=Path)
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--max-density', type=float, default=2.0,
                    help='Max AI tells per 1000 syllables before failing (default: 2.0)')
    args = ap.parse_args()

    try:
        raw = args.path.read_text(encoding='utf-8')
    except OSError as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2

    report = lint_text(raw)
    report['max_density'] = args.max_density
    has_p0 = any(f['severity'] == 'P0' for f in report['findings'])
    failed = report['ai_tell_density_per_1000'] > args.max_density or has_p0
    report['passed'] = not failed

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"{args.path}: {report['ai_tell_count']} dấu hiệu AI "
              f"/ {report['syllables']} âm tiết "
              f"(mật độ {report['ai_tell_density_per_1000']}/1000, "
              f"ngưỡng {args.max_density})")
        for f in report['findings']:
            loc = f"dòng {f['line']}" if f['line'] else 'toàn bài'
            print(f"  [{f['severity']}] {loc}: {f['label']} - {f['match']!r}")
            print(f"          -> {f['fix']}")
        print('PASS' if report['passed'] else 'FAIL')

    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
