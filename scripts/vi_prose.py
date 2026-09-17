#!/usr/bin/env python3
"""Vietnamese prose linter: AI-writing tells and register consistency.

Deterministic, standard library only. Complements scripts/lint_prose.py, which
enforces character hygiene across all languages; this module adds the
Vietnamese-specific checks that a language-agnostic linter cannot express.

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
    from vi_text import count_syllables, normalize
except ImportError:                                   # standalone execution
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from vi_text import count_syllables, normalize

__all__ = ["lint_text", "AI_TELLS", "REGISTER_SETS"]

# ---------------------------------------------------------------------------
# AI-writing tells
#
# Formulaic openers and connectives that appear far more often in
# machine-generated Vietnamese than in prose a person actually wrote.
# Each entry is (pattern, human-readable label, suggested fix).
# ---------------------------------------------------------------------------
AI_TELLS: tuple[tuple[str, str, str], ...] = (
    (r'trong\s+(?:thế\s+giới|thời\s+đại|bối\s+cảnh)\s+(?:ngày\s+nay|hiện\s+nay|'
     r'số\s+hoá|công\s+nghệ\s+số|4\.0)',
     'Mở bài sáo rỗng', 'Vào thẳng vấn đề người đọc đang gặp.'),
    (r'không\s+thể\s+phủ\s+nhận\s+(?:rằng|là)',
     'Khẳng định rỗng', 'Bỏ. Nếu đúng thì không cần nói là không thể phủ nhận.'),
    (r'điều\s+(?:quan\s+trọng|đáng\s+lưu\s+ý)\s+(?:cần\s+)?(?:lưu\s+ý|nhớ|biết)\s+là',
     'Câu đệm', 'Bỏ cụm này và giữ lại nội dung phía sau.'),
    (r'hãy\s+cùng\s+(?:đi\s+sâu|tìm\s+hiểu|khám\s+phá|điểm\s+qua)',
     'Dẫn dắt thừa', 'Bỏ. Người đọc đã bấm vào bài rồi.'),
    (r'(?:tóm\s+lại|nhìn\s+chung)\s*,?\s*(?:có\s+thể\s+thấy|chúng\s+ta\s+có\s+thể\s+thấy)',
     'Kết bài sáo rỗng', 'Kết bằng một hành động cụ thể.'),
    (r'đóng\s+(?:một\s+)?vai\s+trò\s+(?:vô\s+cùng\s+)?quan\s+trọng',
     'Cụm mòn', 'Nói rõ nó làm gì.'),
    (r'ngày\s+càng\s+trở\s+nên\s+(?:phổ\s+biến|quan\s+trọng|cần\s+thiết)',
     'Cụm mòn', 'Đưa số liệu thay vì tính từ.'),
    (r'là\s+một\s+trong\s+những\s+yếu\s+tố\s+(?:then\s+chốt|quan\s+trọng\s+nhất)',
     'Cụm mòn', 'Xếp hạng cụ thể hoặc bỏ.'),
    (r'giúp\s+(?:bạn\s+)?(?:tối\s+ưu\s+hoá|nâng\s+cao|cải\s+thiện)\s+'
     r'(?:một\s+cách\s+)?(?:hiệu\s+quả|đáng\s+kể|tối\s+đa)',
     'Hứa hẹn mơ hồ', 'Nêu con số cải thiện thực tế.'),
    (r'trong\s+bài\s+viết\s+(?:này|dưới\s+đây)\s*,?\s*(?:chúng\s+ta|chúng\s+tôi|tôi)\s+sẽ',
     'Meta thừa', 'Bỏ. Bắt đầu bằng nội dung.'),
    (r'hy\s+vọng\s+(?:rằng\s+)?bài\s+viết\s+(?:này\s+)?(?:sẽ\s+)?(?:hữu\s+ích|giúp\s+ích)',
     'Kết bài sáo rỗng', 'Kết bằng bước tiếp theo cụ thể.'),
    (r'với\s+sự\s+phát\s+triển\s+(?:không\s+ngừng\s+)?của\s+(?:công\s+nghệ|internet)',
     'Mở bài sáo rỗng', 'Vào thẳng vấn đề.'),
)

# ---------------------------------------------------------------------------
# Register (xưng hô). Vietnamese second-person address encodes social distance.
# Mixing sets inside one document reads as careless or machine-assembled.
# ---------------------------------------------------------------------------
REGISTER_SETS: dict[str, tuple[str, ...]] = {
    'than_mat':    (r'bạn', r'các\s+bạn', r'mình'),                     # peer, informal
    'trang_trong': (r'quý\s+khách', r'quý\s+vị', r'quý\s+công\s+ty'),   # formal, commercial
    'lich_su':     (r'anh\s*/\s*chị', r'anh\s+chị', r'các\s+anh\s+chị'),# polite, sales
}


def _strip_markdown(text: str) -> str:
    """Remove code fences, tables, HTML and link targets before linting prose."""
    text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    text = re.sub(r'`[^`]*`', '', text)
    text = re.sub(r'^\s*\|.*\|\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'!\[.*?\]\(.*?\)', '', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    return text


def lint_text(raw: str) -> dict:
    """Return findings for one document. Pure; no IO."""
    text = normalize(_strip_markdown(raw))
    lower = text.lower()
    total_syllables = max(count_syllables(text), 1)

    findings: list[dict] = []
    for pattern, label, fix in AI_TELLS:
        for match in re.finditer(pattern, lower, re.IGNORECASE):
            line = lower.count('\n', 0, match.start()) + 1
            findings.append({
                'type': 'ai_tell', 'severity': 'P1', 'label': label,
                'match': match.group(0), 'line': line, 'fix': fix,
            })

    # Register drift: report only when two or more sets are actually used.
    register_hits: dict[str, int] = {}
    for name, patterns in REGISTER_SETS.items():
        count = sum(len(re.findall(rf'(?<![^\W\d_]){p}(?![^\W\d_])', lower))
                    for p in patterns)
        if count:
            register_hits[name] = count
    if len(register_hits) >= 2:
        dominant = max(register_hits, key=register_hits.get)
        findings.append({
            'type': 'register_drift', 'severity': 'P0',
            'label': 'Xưng hô không nhất quán',
            'match': ', '.join(f'{k}={v}' for k, v in sorted(register_hits.items())),
            'line': 0,
            'fix': f'Chọn một cách xưng hô cho cả bài. Đang dùng nhiều nhất: {dominant}.',
        })

    tells = sum(1 for f in findings if f['type'] == 'ai_tell')
    return {
        'syllables': total_syllables,
        'ai_tell_count': tells,
        'ai_tell_density_per_1000': round(tells / total_syllables * 1000, 2),
        'register_sets_used': register_hits,
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
